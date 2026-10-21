# -*- coding: utf-8 -*-
import pandas as pd
import numpy as np

CONFIG = {
    "IMPULSE_MIN_PCT": 0.025,      
    "IMPULSE_MAX_LOOKBACK": 40,    
    "BOX_MIN_CANDLES": 10,         
    "BOX_MAX_HEIGHT_PCT": 0.05,    
    "MAX_RETRACEMENT_PCT": 0.50,   
    "BREAKOUT_MIN_BODY_PCT": 0.004, 
    "REQUIRE_RETEST": True,        
    "RETEST_MAX_CANDLES": 8,       
    "RETEST_TOLERANCE": 0.003,     
    "RETEST_STRONG_CLOSE_RATIO": 0.5, 
    "LIVE_MAX_BREAKOUT_CANDLES": 10, 
    
    # ⬇️ تعديل الهدف ليكون ضعف الوقف 1:2 (مستويات التريلينج تتناسب مع ذلك) ⬇️
    "TRAILING_LEVELS_HEAD": [(0.50, 0.0), (0.75, 0.5), (1.00, 0.8)],
    
    "SAFE_SL_MARGIN": 0.05,        
    "USE_SAFE_SL": True,
    "VOLUME_MA_PERIOD": 20,
    "TREND_EMA_PERIOD": 200,
    
    # ⬇️ فلتر الدعوم والمقاومات التاريخية ⬇️
    "USE_SR_FILTER": True,
    "SR_LOOKBACK": 150,
    "SR_WINDOW": 5,
    
    # ⬇️ منع تداخل الصفقات ⬇️
    "MIN_GAP_BETWEEN_TRADES": 5
}

REASON_MAP = {
    "immediate_rejection": {"reason": "السعر رفض الصندوق فورًا."},
    "early_reversal": {"reason": "انعكاس مبكر قبل 30%."},
    "mid_reversal": {"reason": "انعكاس متوسط."},
    "late_reversal": {"reason": "وصل 70%+ ثم عاد."},
    "breakeven": {"reason": "تعادل."},
    "success": {"reason": "وصل الهدف."},
    "trailing_win": {"reason": "خرج بـ Trailing."},
    "open": {"reason": "مفتوحة."},
}

def get_symbol_config(symbol): return CONFIG.copy()

def calculate_indicators(df, cfg=None):
    df = df.copy()
    if "Volume" in df.columns:
        v = pd.to_numeric(df["Volume"], errors="coerce").fillna(0.0)
        df["Volume"] = v
        df["Volume_MA"] = v.rolling(CONFIG.get("VOLUME_MA_PERIOD", 20)).mean().fillna(0.0)
    else:
        df["Volume"] = 0.0
        df["Volume_MA"] = 0.0
    df["EMA50"] = df["Close"].ewm(span=50, adjust=False).mean()
    df["EMA200"] = df["Close"].ewm(span=CONFIG["TREND_EMA_PERIOD"], adjust=False).mean()
    return df

def get_major_levels(df, current_idx, lookback=150, window=5):
    """اكتشاف القمم والقيعان التاريخية الكبيرة (الدعوم والمقاومات)"""
    start_idx = max(0, current_idx - lookback)
    df_sub = df.iloc[start_idx:current_idx]
    if len(df_sub) < window * 2: return []
    
    highs = df_sub['High'].values
    lows = df_sub['Low'].values
    levels = []
    
    for i in range(window, len(df_sub) - window):
        if highs[i] == max(highs[i-window:i+window+1]):
            levels.append(highs[i])
        if lows[i] == min(lows[i-window:i+window+1]):
            levels.append(lows[i])
            
    if not levels: return []
    
    levels = sorted(list(set(levels)))
    clustered = []
    current_cluster = [levels[0]]
    for l in levels[1:]:
        if (l - current_cluster[0]) / current_cluster[0] < 0.005:
            current_cluster.append(l)
        else:
            clustered.append(sum(current_cluster)/len(current_cluster))
            current_cluster = [l]
    clustered.append(sum(current_cluster)/len(current_cluster))
    
    return clustered

def compute_safe_sl_and_tp(bias, entry, structural_sl, wave_height, cfg=None):
    structural_risk = abs(entry - structural_sl)
    if structural_risk == 0: structural_risk = 1e-5
    
    if bias == "Bullish": safe_sl = structural_sl - (structural_risk * CONFIG["SAFE_SL_MARGIN"])
    else: safe_sl = structural_sl + (structural_risk * CONFIG["SAFE_SL_MARGIN"])
    
    final_sl = safe_sl if CONFIG["USE_SAFE_SL"] else structural_sl
    
    # ⬇️ الهدف ضعف الوقف 1:2 ⬇️
    risk_distance = abs(entry - final_sl)
    if risk_distance == 0: risk_distance = 1e-5
    target = risk_distance * 1.5.0
    tp = entry + target if bias == "Bullish" else entry - target
    
    return final_sl, tp, safe_sl, structural_sl

def simulate_trade(pattern, df, cfg=None):
    bias = pattern["bias"]
    entry = float(pattern["entry"])
    sl = float(pattern["sl"])
    tp = float(pattern["tp"])
    end_idx = pattern["neckline_end_idx"]
    
    if end_idx not in df.index: return {"Result": "OPEN"}
    post_df = df.loc[end_idx:]
    if len(post_df) <= 1: return {"Result": "OPEN"}

    stats = {"Result": "OPEN", "Max Reach %": 0.0, "SL Safety %": 0.0, "Entry Date": str(end_idx), "Exit Date": None, "candles_to_exit": 0, "Trailing Stage": 0, "Initial SL": sl, "Final SL": sl, "Loss Category": None, "exit_price": None}
    total_tp_dist = abs(tp - entry)
    head_size = total_tp_dist
    max_fav, max_adv = 0.0, 0.0
    exited = False

    for c, (idx, row) in enumerate(post_df.iloc[1:].iterrows(), start=1):
        h, l = float(row["High"]), float(row["Low"])
        fav = max(0.0, entry - l) if bias == "Bearish" else max(0.0, h - entry)
        adv = max(0.0, h - entry) if bias == "Bearish" else max(0.0, entry - l)
        
        prog = (fav / total_tp_dist) if total_tp_dist > 0 else 0.0
        prog_h = (fav / head_size) if head_size > 0 else 0.0

        if not exited:
            max_fav = max(max_fav, prog * 100)
            max_adv = max(max_adv, (adv / abs(entry - stats["Initial SL"]) * 100) if abs(entry - stats["Initial SL"]) > 0 else 0.0)
        if exited: continue

        for st_idx, (th, ph) in enumerate(CONFIG["TRAILING_LEVELS_HEAD"]):
            if prog_h < th: break
            new_sl = entry - ph * head_size if bias == "Bearish" else entry + ph * head_size
            if bias == "Bearish" and new_sl < sl: sl = new_sl; stats["Trailing Stage"] = st_idx + 1
            elif bias == "Bullish" and new_sl > sl: sl = new_sl; stats["Trailing Stage"] = st_idx + 1
        stats["Final SL"] = sl

        hit_sl = (h >= sl) if bias == "Bearish" else (l <= sl)
        hit_tp = (l <= tp) if bias == "Bearish" else (h >= tp)

        if hit_sl and not hit_tp:
            is_prof = (sl < entry) if bias == "Bearish" else (sl > entry)
            if is_prof: stats["Result"] = "WIN"; stats["Loss Category"] = "trailing_win"
            else:
                stats["Result"] = "LOSS"
                if max_fav < 30: stats["Loss Category"] = "early_reversal"
                elif max_fav < 70: stats["Loss Category"] = "mid_reversal"
                else: stats["Loss Category"] = "late_reversal"
            stats["exit_price"] = sl; stats["candles_to_exit"] = c; stats["Exit Date"] = str(idx); exited = True; continue

        elif hit_tp:
            stats["Result"] = "WIN"; stats["Loss Category"] = "success"
            stats["exit_price"] = tp; stats["candles_to_exit"] = c; stats["Exit Date"] = str(idx); exited = True; continue

    stats["Max Reach %"] = round(max_fav, 1)
    stats["SL Safety %"] = round(100 - max_adv, 1) if max_adv <= 100 else 0.0
    return stats

def detect_box_breakouts(df, symbol=None, is_backtest=True):
    patterns = []
    n = len(df)
    if n < 100: return patterns

    highs, lows, closes, opens = df["High"].values, df["Low"].values, df["Close"].values, df["Open"].values
    
    # ⬇️ متغير لتتبع آخر صفقة ومنع التداخل ⬇️
    last_entry_idx = -1000
    
    for i in range(60, n):
        # منع فتح صفقة جديدة إذا كانت الصفقة السابقة قريبة جداً
        if i <= last_entry_idx + CONFIG["MIN_GAP_BETWEEN_TRADES"]:
            continue
            
        candle_body = abs(closes[i] - opens[i])
        if candle_body < (closes[i] * CONFIG["BREAKOUT_MIN_BODY_PCT"]): continue
        
        is_bull_breakout = closes[i] > opens[i]
        is_bear_breakout = closes[i] < opens[i]
        lookback_start = max(0, i - CONFIG["IMPULSE_MAX_LOOKBACK"])
        
        if is_bull_breakout:
            impulse_start_idx = lookback_start + np.argmin(lows[lookback_start:i])
            impulse_start_price = lows[impulse_start_idx]
            impulse_move = closes[i] - impulse_start_price
            if (impulse_move / impulse_start_price) < CONFIG["IMPULSE_MIN_PCT"]: continue
        else:
            impulse_start_idx = lookback_start + np.argmax(highs[lookback_start:i])
            impulse_start_price = highs[impulse_start_idx]
            impulse_move = impulse_start_price - closes[i]
            if (impulse_move / impulse_start_price) < CONFIG["IMPULSE_MIN_PCT"]: continue

        if is_bull_breakout: box_start_idx = impulse_start_idx + np.argmax(highs[impulse_start_idx:i])
        else: box_start_idx = impulse_start_idx + np.argmin(lows[impulse_start_idx:i])

        if box_start_idx >= i or (i - box_start_idx) < CONFIG["BOX_MIN_CANDLES"]: continue

        box_highs = highs[box_start_idx:i]
        box_lows = lows[box_start_idx:i]
        box_top = np.max(box_highs)
        box_bottom = np.min(box_lows)
        box_height = box_top - box_bottom
        box_mid = (box_top + box_bottom) / 2
        
        if box_height == 0 or (box_height / box_mid) > CONFIG["BOX_MAX_HEIGHT_PCT"]: continue
        if (box_height / impulse_move) > CONFIG["MAX_RETRACEMENT_PCT"]: continue

        actual_entry_idx = i
        actual_entry_price = closes[i]
        structural_sl = lows[i] if is_bull_breakout else highs[i]

        if CONFIG.get("REQUIRE_RETEST", False):
            retest_found = False
            for j in range(i + 1, min(n, i + 1 + CONFIG["RETEST_MAX_CANDLES"])):
                if is_bull_breakout:
                    if lows[j] <= box_top * (1 + CONFIG["RETEST_TOLERANCE"]) and closes[j] > box_top:
                        candle_range = highs[j] - lows[j]
                        if candle_range > 0 and (closes[j] - lows[j]) / candle_range >= CONFIG["RETEST_STRONG_CLOSE_RATIO"]:
                            retest_found = True; actual_entry_idx = j; actual_entry_price = closes[j]; structural_sl = lows[j]; break
                elif is_bear_breakout:
                    if highs[j] >= box_bottom * (1 - CONFIG["RETEST_TOLERANCE"]) and closes[j] < box_bottom:
                        candle_range = highs[j] - lows[j]
                        if candle_range > 0 and (highs[j] - closes[j]) / candle_range >= CONFIG["RETEST_STRONG_CLOSE_RATIO"]:
                            retest_found = True; actual_entry_idx = j; actual_entry_price = closes[j]; structural_sl = highs[j]; break
            if not retest_found: continue

        box_nodes = [(df.index[box_start_idx], box_top), (df.index[actual_entry_idx], box_top), (df.index[box_start_idx], box_bottom), (df.index[actual_entry_idx], box_bottom)]
        trend_nodes = [(df.index[impulse_start_idx], impulse_start_price), (df.index[box_start_idx], box_bottom if is_bull_breakout else box_top), (df.index[actual_entry_idx], actual_entry_price)]

        if is_bull_breakout and actual_entry_price > box_top:
            final_sl, tp, safe_sl, struct_sl = compute_safe_sl_and_tp("Bullish", actual_entry_price, structural_sl, impulse_move)
            
            # فلتر الدعوم والمقاومات التاريخية (Bullish)
            if CONFIG.get("USE_SR_FILTER", True):
                major_levels = get_major_levels(df, actual_entry_idx, CONFIG["SR_LOOKBACK"], CONFIG["SR_WINDOW"])
                sr_blocked = False
                for lvl in major_levels:
                    if actual_entry_price * 1.0005 < lvl < tp * 0.9995:
                        sr_blocked = True
                        break
                if sr_blocked:
                    continue

            pattern = {"name": "Macro Box Breakout", "pattern": "Box Breakout", "pattern_type": "Continuation", "bias": "Bullish", "match": 100.0, "nodes": trend_nodes, "entry": float(round(actual_entry_price, 5)), "sl": float(round(final_sl, 5)), "tp": float(round(tp, 5)), "structural_sl": float(round(struct_sl, 5)), "safe_sl": float(round(safe_sl, 5)), "neckline_nodes": box_nodes, "end_pos": actual_entry_idx, "neckline_end_idx": df.index[actual_entry_idx], "Entry": float(round(actual_entry_price, 5)), "Pattern": "Box Breakout (Bullish)"}
            pattern.update(simulate_trade(pattern, df))
            pattern["Trade Recommendation"] = f"🟢 Box Breakout + Retest:\n- الدخول: {pattern['entry']}\n- SL: {pattern['sl']}\n- TP: {pattern['tp']}"
            patterns.append(pattern)
            
            # تحديث آخر صفقة (تم إزالة break)
            last_entry_idx = actual_entry_idx
            
        elif is_bear_breakout and actual_entry_price < box_bottom:
            final_sl, tp, safe_sl, struct_sl = compute_safe_sl_and_tp("Bearish", actual_entry_price, structural_sl, impulse_move)
            
            # فلتر الدعوم والمقاومات التاريخية (Bearish)
            if CONFIG.get("USE_SR_FILTER", True):
                major_levels = get_major_levels(df, actual_entry_idx, CONFIG["SR_LOOKBACK"], CONFIG["SR_WINDOW"])
                sr_blocked = False
                for lvl in major_levels:
                    if tp * 1.0005 < lvl < actual_entry_price * 0.9995:
                        sr_blocked = True
                        break
                if sr_blocked:
                    continue

            pattern = {"name": "Macro Box Breakout", "pattern": "Box Breakout", "pattern_type": "Continuation", "bias": "Bearish", "match": 100.0, "nodes": trend_nodes, "entry": float(round(actual_entry_price, 5)), "sl": float(round(final_sl, 5)), "tp": float(round(tp, 5)), "structural_sl": float(round(struct_sl, 5)), "safe_sl": float(round(safe_sl, 5)), "neckline_nodes": box_nodes, "end_pos": actual_entry_idx, "neckline_end_idx": df.index[actual_entry_idx], "Entry": float(round(actual_entry_price, 5)), "Pattern": "Box Breakout (Bearish)"}
            pattern.update(simulate_trade(pattern, df))
            pattern["Trade Recommendation"] = f"🔴 Box Breakout + Retest:\n- الدخول: {pattern['entry']}\n- SL: {pattern['sl']}\n- TP: {pattern['tp']}"
            patterns.append(pattern)
            
            # تحديث آخر صفقة (تم إزالة break)
            last_entry_idx = actual_entry_idx
            
    return patterns

def run_full_analysis(df, interval="1h", symbol=None):
    df = calculate_indicators(df)
    patterns = detect_box_breakouts(df, symbol, is_backtest=False)
    if not patterns: return {"signal": "WAITING", "pattern": "NO PATTERN", "bias": "Neutral", "df": df}
    
    recent_patterns = []
    last_idx_pos = len(df) - 1
    for p in patterns:
        try:
            p_pos = df.index.get_loc(p["neckline_end_idx"])
            if (last_idx_pos - p_pos) <= CONFIG["LIVE_MAX_BREAKOUT_CANDLES"]: recent_patterns.append(p)
        except KeyError: continue

    if not recent_patterns: return {"signal": "WAITING", "pattern": "NO RECENT PATTERN", "bias": "Neutral", "df": df}

    latest = recent_patterns[-1]
    return {"df": df, "signal": "STRONG BUY" if latest["bias"]=="Bullish" else "STRONG SELL", "pattern": latest["pattern"], "bias": latest["bias"], "entry": latest["entry"], "sl": latest["sl"], "tp": latest["tp"], "nodes": latest["nodes"], "neckline_nodes": latest["neckline_nodes"], "Trade Recommendation": latest["Trade Recommendation"]}

def backtest_strategy(df, interval="1h", symbol=None):
    df = calculate_indicators(df)
    patterns = detect_box_breakouts(df, symbol, is_backtest=True)
    trades = []
    for p in patterns:
        p["Symbol"] = symbol; p["Entry Price"] = p["entry"]; p["Stop Loss"] = p["sl"]; p["Take Profit"] = p["tp"]
        trades.append(p)
    return trades

def diagnose_no_signals(df, interval="1h", symbol=None, is_backtest=True): return {}

def diagnose_filters(df, interval="1h", symbol=None):
    trades = backtest_strategy(df, interval, symbol)
    wins = [t for t in trades if "WIN" in str(t.get("Result","")).upper()]
    losses = [t for t in trades if "LOSS" in str(t.get("Result","")).upper()]
    total = len(wins) + len(losses)
    wr = round(len(wins)/total*100, 1) if total > 0 else 0
    verdict = "لا توجد صفقات كافية" if total == 0 else f"معدل الربح: {wr}%"
    return {"smart_diagnosis": {"verdict": verdict, "win_breakdown": {}, "loss_breakdown": {}, "action_plan": []}}
