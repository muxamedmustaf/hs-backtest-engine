# -*- coding: utf-8 -*-
"""
ENGINE.PY — Box Breakout Hunter
===================================================
- يبحث عن حركة دافعة (Trend).
- يبحث عن تجميع (Box) بقمم وقيعان متساوية (لمستان على الأقل).
- كسر حقيقي بإغلاق شمعة خارج الصندوق.
- الهدف = القمة أو القاع السابق (Prior Swing High/Low).
"""
import pandas as pd
import numpy as np

CONFIG = {
    "MIN_BOX_CANDLES": 8, "MAX_BOX_CANDLES": 40, "BOX_MAX_HEIGHT_PCT": 0.03,            
    "MIN_TOUCHES": 2, "BOX_EQUALITY_TOLERANCE": 0.002,       
    "TREND_MIN_ATR_MULTIPLIER": 2.5, "TREND_LOOKBACK_CANDLES": 20,          
    "REQUIRE_TRUE_BREAKOUT": True, "TRUE_BREAKOUT_MIN_PCT": 0.0005,       
    "BREAKOUT_ATR_MULTIPLIER": 1.2, "REQUIRE_VOLUME_BREAKOUT": True,
    "VOLUME_BREAKOUT_FACTOR": 1.2, "VOLUME_MA_PERIOD": 20,
    "LIVE_MAX_BREAKOUT_CANDLES": 15,
    "TP_REACH_FACTOR": 1.0, "USE_SAFE_SL": True, "SAFE_SL_MARGIN": 0.15,
    "TRAILING_LEVELS_HEAD": [(1.00, 0.50), (1.50, 1.00), (2.00, 1.50)],
    "MEASURE_FULL_EXTENSION": True,
}

REASON_MAP = {
    "immediate_rejection": {"reason": "السعر رفض الصندوق فورًا.", "action": "انتظر.", "prevention": "لا تدخل بأول لمسة."},
    "early_reversal": {"reason": "انعكاس مبكر قبل 30%.", "action": "نقل SL للتعادل.", "prevention": "Trailing مبكر."},
    "mid_reversal": {"reason": "انعكاس متوسط.", "action": "خروج جزئي.", "prevention": "TP جزئي."},
    "late_reversal": {"reason": "وصل 70%+ ثم عاد.", "action": "Trailing.", "prevention": "راقب الأخبار."},
    "breakeven": {"reason": "تعادل — حماية رأس المال.", "action": "لا شيء.", "prevention": "استمر."},
    "success": {"reason": "وصل الهدف.", "action": "كرر الإعداد.", "prevention": "—"},
    "trailing_win": {"reason": "خرج بـ Trailing.", "action": "لا شيء.", "prevention": "—"},
    "open": {"reason": "ما زالت مفتوحة.", "action": "راقب.", "prevention": "—"},
}

def get_symbol_config(symbol):
    return CONFIG.copy()

def calculate_indicators(df, cfg):
    df = df.copy()
    hl = df["High"] - df["Low"]
    hc = np.abs(df["High"] - df["Close"].shift())
    lc = np.abs(df["Low"] - df["Close"].shift())
    tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    df["ATR"] = tr.rolling(14).mean()
    if "Volume" in df.columns:
        v = pd.to_numeric(df["Volume"], errors="coerce").fillna(0.0)
        df["Volume"] = v
        df["Volume_MA"] = v.rolling(cfg.get("VOLUME_MA_PERIOD", 20)).mean().fillna(0.0)
    else:
        df["Volume"] = 0.0
        df["Volume_MA"] = 0.0
    return df

def compute_safe_sl_and_tp(bias, entry, structural_sl, target_price, box_height, cfg):
    structural_risk = abs(entry - structural_sl)
    if bias == "Bullish":
        safe_sl = structural_sl - (structural_risk * cfg["SAFE_SL_MARGIN"])
    else:
        safe_sl = structural_sl + (structural_risk * cfg["SAFE_SL_MARGIN"])
    final_sl = safe_sl if cfg["USE_SAFE_SL"] else structural_sl
    
    if target_price is not None and target_price > 0:
        tp = target_price
    else:
        target = box_height * cfg["TP_REACH_FACTOR"]
        tp = entry + target if bias == "Bullish" else entry - target
    return final_sl, tp, safe_sl, structural_sl

def generate_trade_recommendation(bias, entry, sl, tp, pattern_name):
    risk = abs(entry - sl)
    reward = abs(tp - entry)
    rr = round(reward / risk, 2) if risk > 0 else 0.0
    if bias == "Bullish":
        return f"🟢 {pattern_name}:\n- الدخول: اختراق ({round(entry, 5)}).\n- SL: ({round(sl, 5)}).\n- TP: ({round(tp, 5)}).\n- R:R = 1 : {rr}."
    else:
        return f"🔴 {pattern_name}:\n- الدخول: كسر ({round(entry, 5)}).\n- SL: ({round(sl, 5)}).\n- TP: ({round(tp, 5)}).\n- R:R = 1 : {rr}."

def simulate_trade_outcome(pattern, df, cfg):
    bias, entry, initial_sl, tp = pattern["bias"], float(pattern["entry"]), float(pattern["sl"]), float(pattern["tp"])
    sl = initial_sl
    end_idx = pattern["neckline_end_idx"] if "neckline_end_idx" in pattern else pattern["nodes"][-1][0]
    
    if end_idx not in df.index: return {"Result": "OPEN"}
    post_df = df.loc[end_idx:]
    if len(post_df) <= 1: return {"Result": "OPEN"}

    stats = {
        "Result": "OPEN", "Head Result": "OPEN", "Max Reach %": 0.0, "SL Safety %": 0.0, 
        "Max Extension %": 0.0, "Extension Beyond TP %": 0.0, "TP Hit At Candle": None, 
        "Extension Duration Candles": 0, "Entry Date": str(end_idx), "Exit Date": None, 
        "candles_to_exit": 0, "progress_ratio": 0.0, "Breakeven Activated": False, 
        "Breakeven Exit": False, "Trailing Stage": 0, "Initial SL": initial_sl, 
        "Final SL": initial_sl, "Loss Category": None, "exit_price": None
    }
    
    total_tp_dist = abs(tp - entry)
    total_sl_dist = abs(initial_sl - entry)
    head_size = total_tp_dist
    max_fav, max_adv, max_ext = 0.0, 0.0, 0.0
    tp_candle, max_ext_candle, exited = None, 0, False

    for c, (idx, row) in enumerate(post_df.iloc[1:].iterrows(), start=1):
        h, l = float(row["High"]), float(row["Low"])
        fav = max(0.0, entry - l) if bias == "Bearish" else max(0.0, h - entry)
        adv = max(0.0, h - entry) if bias == "Bearish" else max(0.0, entry - l)
        
        prog = (fav / total_tp_dist) if total_tp_dist > 0 else 0.0
        prog_h = (fav / head_size) if head_size > 0 else 0.0

        if prog * 100 > max_ext: max_ext = prog * 100; max_ext_candle = c
        if not exited:
            max_fav = max(max_fav, prog * 100)
            max_adv = max(max_adv, (adv / total_sl_dist * 100) if total_sl_dist > 0 else 0.0)
        if exited: continue

        for st_idx, (th, ph) in enumerate(cfg["TRAILING_LEVELS_HEAD"]):
            if prog_h < th: break
            new_sl = entry - ph * head_size if bias == "Bearish" else entry + ph * head_size
            if bias == "Bearish" and new_sl < sl: sl = new_sl; stats["Trailing Stage"] = st_idx + 1
            elif bias == "Bullish" and new_sl > sl: sl = new_sl; stats["Trailing Stage"] = st_idx + 1
        stats["Final SL"] = sl

        hit_sl = (h >= sl) if bias == "Bearish" else (l <= sl)
        hit_tp = (l <= tp) if bias == "Bearish" else (h >= tp)

        if hit_sl and not hit_tp:
            is_prof = (sl < entry) if bias == "Bearish" else (sl > entry)
            if is_prof: 
                stats["Result"] = "WIN"; stats["Loss Category"] = "trailing_win"
            else:
                stats["Result"] = "LOSS"
                if max_fav < 30: stats["Loss Category"] = "early_reversal"
                elif max_fav < 70: stats["Loss Category"] = "mid_reversal"
                else: stats["Loss Category"] = "late_reversal"
            stats["exit_price"] = sl; stats["candles_to_exit"] = c; stats["Exit Date"] = str(idx); exited = True; continue

        elif hit_tp:
            stats["Result"] = "WIN"; stats["Loss Category"] = "success"
            stats["exit_price"] = tp; stats["candles_to_exit"] = c; stats["Exit Date"] = str(idx); tp_candle = c; exited = True; continue

    stats["Max Reach %"] = round(max_fav, 1)
    stats["SL Safety %"] = round(100 - max_adv, 1) if max_adv <= 100 else 0.0
    stats["Max Extension %"] = round(max_ext, 1)
    stats["Extension Beyond TP %"] = round(max(0.0, max_ext - 100.0), 1)
    stats["TP Hit At Candle"] = tp_candle
    stats["Extension Duration Candles"] = max(0, max_ext_candle - tp_candle) if tp_candle else 0
    if stats["Result"] == "WIN": stats["progress_ratio"] = 100.0
    return stats

def detect_box_breakouts(df, is_backtest=False, cfg=None):
    patterns = []
    if cfg is None: cfg = CONFIG
    n = len(df)
    if n < 50: return patterns

    highs, lows, closes, opens = df["High"].values, df["Low"].values, df["Close"].values, df["Open"].values
    atr, vols, vol_ma = df["ATR"].values, df["Volume"].values, df["Volume_MA"].values
    
    for i in range(30, n):
        breakout_close, breakout_open = closes[i], opens[i]
        candle_body = abs(breakout_close - breakout_open)
        if candle_body < (atr[i] * cfg["BREAKOUT_ATR_MULTIPLIER"]): continue
        if cfg["REQUIRE_VOLUME_BREAKOUT"] and vols[i] < (vol_ma[i] * cfg["VOLUME_BREAKOUT_FACTOR"]): continue

        for box_len in range(cfg["MIN_BOX_CANDLES"], cfg["MAX_BOX_CANDLES"] + 1):
            start_idx = i - box_len
            if start_idx < cfg["TREND_LOOKBACK_CANDLES"]: continue
            
            box_highs, box_lows = highs[start_idx:i], lows[start_idx:i]
            box_top, box_bottom = np.max(box_highs), np.min(box_lows)
            box_height = box_top - box_bottom
            box_mid = (box_top + box_bottom) / 2
            
            if box_height / box_mid > cfg["BOX_MAX_HEIGHT_PCT"]: continue
            if box_height == 0: continue

            price_tol = box_top * cfg["BOX_EQUALITY_TOLERANCE"]
            touches_top = sum(1 for h in box_highs if h >= box_top - price_tol)
            touches_bottom = sum(1 for l in box_lows if l <= box_bottom + price_tol)
                
            if touches_top < cfg["MIN_TOUCHES"] or touches_bottom < cfg["MIN_TOUCHES"]: continue

            trend_idx = start_idx - cfg["TREND_LOOKBACK_CANDLES"]
            if trend_idx < 0: continue
            
            trend_move_up = closes[start_idx] - closes[trend_idx]
            trend_move_down = closes[trend_idx] - closes[start_idx]
            is_uptrend = trend_move_up > (atr[start_idx] * cfg["TREND_MIN_ATR_MULTIPLIER"])
            is_downtrend = trend_move_down > (atr[start_idx] * cfg["TREND_MIN_ATR_MULTIPLIER"])

            # [يسار-علوي, يمين-علوي, يسار-سفلي, يمين-سفلي]
            box_nodes = [
                (df.index[start_idx], box_top), (df.index[i], box_top),
                (df.index[start_idx], box_bottom), (df.index[i], box_bottom)
            ]

            if breakout_close > box_top * (1 + cfg["TRUE_BREAKOUT_MIN_PCT"]) and is_uptrend:
                entry = breakout_close
                prior_high = np.max(highs[trend_idx:start_idx])
                target_price = prior_high if prior_high > entry else None
                final_sl, tp, safe_sl, _ = compute_safe_sl_and_tp("Bullish", entry, box_bottom, target_price, box_height, cfg)
                pattern = {
                    "name": "Box Breakout", "pattern": "Box Breakout", "pattern_type": "Continuation",
                    "bias": "Bullish", "match": 100.0, "nodes": [(df.index[trend_idx], closes[trend_idx]), (df.index[start_idx], box_bottom), (df.index[i], entry)],
                    "entry": float(round(entry, 5)), "sl": float(round(final_sl, 5)), "tp": float(round(tp, 5)),
                    "structural_sl": float(round(box_bottom, 5)), "safe_sl": float(round(safe_sl, 5)),
                    "neckline_nodes": box_nodes, "target_nodes": [(df.index[i], float(round(entry, 5))), (df.index[i], float(round(tp, 5)))],
                    "end_pos": i, "neckline_end_idx": df.index[i], "Entry": float(round(entry, 5)), "Pattern": "Box Breakout (Bullish)",
                }
                pattern.update(simulate_trade_outcome(pattern, df, cfg))
                pattern["Trade Recommendation"] = generate_trade_recommendation("Bullish", entry, final_sl, tp, "Box Breakout")
                patterns.append(pattern)
                break

            elif breakout_close < box_bottom * (1 - cfg["TRUE_BREAKOUT_MIN_PCT"]) and is_downtrend:
                entry = breakout_close
                prior_low = np.min(lows[trend_idx:start_idx])
                target_price = prior_low if prior_low < entry else None
                final_sl, tp, safe_sl, _ = compute_safe_sl_and_tp("Bearish", entry, box_top, target_price, box_height, cfg)
                pattern = {
                    "name": "Box Breakout", "pattern": "Box Breakout", "pattern_type": "Continuation",
                    "bias": "Bearish", "match": 100.0, "nodes": [(df.index[trend_idx], closes[trend_idx]), (df.index[start_idx], box_top), (df.index[i], entry)],
                    "entry": float(round(entry, 5)), "sl": float(round(final_sl, 5)), "tp": float(round(tp, 5)),
                    "structural_sl": float(round(box_top, 5)), "safe_sl": float(round(safe_sl, 5)),
                    "neckline_nodes": box_nodes, "target_nodes": [(df.index[i], float(round(entry, 5))), (df.index[i], float(round(tp, 5)))],
                    "end_pos": i, "neckline_end_idx": df.index[i], "Entry": float(round(entry, 5)), "Pattern": "Box Breakout (Bearish)",
                }
                pattern.update(simulate_trade_outcome(pattern, df, cfg))
                pattern["Trade Recommendation"] = generate_trade_recommendation("Bearish", entry, final_sl, tp, "Box Breakout")
                patterns.append(pattern)
                break
    return patterns

def run_full_analysis(df, interval="1h", symbol=None):
    cfg = get_symbol_config(symbol)
    df = calculate_indicators(df, cfg)
    patterns = detect_box_breakouts(df, is_backtest=False, cfg=cfg)
    if not patterns: return {"signal": "WAITING", "pattern": "NO PATTERN", "bias": "Neutral", "df": df}
    latest = patterns[-1]
    return {"df": df, "signal": "STRONG BUY" if latest["bias"]=="Bullish" else "STRONG SELL", "pattern": latest["pattern"], "bias": latest["bias"], "entry": latest["entry"], "sl": latest["sl"], "tp": latest["tp"], "nodes": latest["nodes"], "neckline_nodes": latest["neckline_nodes"], "target_nodes": latest["target_nodes"], "Trade Recommendation": latest["Trade Recommendation"]}

def backtest_strategy(df, interval="1h", symbol=None):
    cfg = get_symbol_config(symbol)
    df = calculate_indicators(df, cfg)
    patterns = detect_box_breakouts(df, is_backtest=True, cfg=cfg)
    trades = []
    for p in patterns:
        p["Symbol"] = symbol; p["symbol"] = symbol; p["Entry Price"] = p["entry"]; p["Stop Loss"] = p["sl"]; p["Take Profit"] = p["tp"]
        p["Bias"] = p["bias"]
        trades.append(p)
    return trades

def diagnose_no_signals(df, interval="1h", symbol=None, is_backtest=True):
    return {"total_pivots": 0, "raw_candidates": 0, "rejected_trend": 0, "rejected_box_height": 0, "rejected_touches": 0, "rejected_breakout_strength": 0, "rejected_volume": 0, "passed": 0}

def diagnose_filters(df, interval="1h", symbol=None):
    trades = backtest_strategy(df, interval, symbol)
    wins = [t for t in trades if "WIN" in str(t.get("Result","")).upper()]
    losses = [t for t in trades if "LOSS" in str(t.get("Result","")).upper()]
    total = len(wins) + len(losses)
    wr = round(len(wins)/total*100, 1) if total > 0 else 0
    verdict = "لا توجد صفقات كافية" if total == 0 else f"معدل الربح: {wr}%"
    return {"smart_diagnosis": {"verdict": verdict, "win_breakdown": {}, "loss_breakdown": {}, "action_plan": []}}
