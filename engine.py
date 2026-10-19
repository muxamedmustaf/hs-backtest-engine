# -*- coding: utf-8 -*-
"""
ENGINE.PY — Box Breakout Hunter (Trend + Range + Breakout)
===================================================
- حركة سابقة قوية (Trend).
- تجميع (Box) بقمم وقيعان متساوية (لمستان على الأقل).
- كسر حقيقي بإغلاق شمعة خارج الصندوق.
- الهدف = القمة أو القاع السابق (Prior Swing High/Low).
- إلغاء البريك إيفن (Breakeven).
"""
import pandas as pd
import numpy as np

CONFIG = {
    "ZIGZAG_DEPTH": 7,                     
    "ZIGZAG_BACKSTEP": 4,                  
    "MIN_WAVE_CANDLES": 4,                 
    
    # ═══════════════════════════════════════════════════════════════════════
    # 🎯 إعدادات "صندوق التجميع" (Box Consolidation)
    # ═══════════════════════════════════════════════════════════════════════
    "MIN_BOX_CANDLES": 8,                  
    "MAX_BOX_CANDLES": 40,                 
    "BOX_MAX_HEIGHT_PCT": 0.03,            
    "MIN_TOUCHES": 2,                      
    "BOX_EQUALITY_TOLERANCE": 0.002,       
    
    # ═══════════════════════════════════════════════════════════════════════
    # 🎯 إعدادات الحركة السابقة والاختراق
    # ═══════════════════════════════════════════════════════════════════════
    "TREND_MIN_ATR_MULTIPLIER": 2.5,       
    "TREND_LOOKBACK_CANDLES": 20,          
    "REQUIRE_TRUE_BREAKOUT": True,         
    "TRUE_BREAKOUT_MIN_PCT": 0.0005,       
    "BREAKOUT_ATR_MULTIPLIER": 1.2,        
    "REQUIRE_VOLUME_BREAKOUT": True,
    "VOLUME_BREAKOUT_FACTOR": 1.2,
    "VOLUME_MA_PERIOD": 20,
    "LIVE_MAX_BREAKOUT_CANDLES": 15,

    # ═══════════════════════════════════════════════════════════════════════
    # 💰 إدارة الصفقة
    # ═══════════════════════════════════════════════════════════════════════
    "TP_REACH_FACTOR": 1.0,                
    "USE_SAFE_SL": True,
    "SAFE_SL_MARGIN": 0.15,
    "TRAILING_LEVELS_HEAD": [
        (1.00, 0.50),   
        (1.50, 1.00),
        (2.00, 1.50),
    ],
    "MEASURE_FULL_EXTENSION": True,
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
        vol_period = cfg.get("VOLUME_MA_PERIOD", 20)
        df["Volume_MA"] = v.rolling(vol_period).mean().fillna(0.0)
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

def detect_box_breakouts(df, is_backtest=False, cfg=None):
    patterns = []
    if cfg is None: cfg = CONFIG
    n = len(df)
    if n < 50: return patterns

    highs = df["High"].values
    lows = df["Low"].values
    closes = df["Close"].values
    opens = df["Open"].values
    atr = df["ATR"].values
    vols = df["Volume"].values
    vol_ma = df["Volume_MA"].values
    
    for i in range(30, n):
        breakout_close = closes[i]
        breakout_open = opens[i]
        
        candle_body = abs(breakout_close - breakout_open)
        if candle_body < (atr[i] * cfg["BREAKOUT_ATR_MULTIPLIER"]): continue
        if cfg["REQUIRE_VOLUME_BREAKOUT"] and vols[i] < (vol_ma[i] * cfg["VOLUME_BREAKOUT_FACTOR"]): continue

        for box_len in range(cfg["MIN_BOX_CANDLES"], cfg["MAX_BOX_CANDLES"] + 1):
            start_idx = i - box_len
            if start_idx < cfg["TREND_LOOKBACK_CANDLES"]: continue
            
            box_highs = highs[start_idx:i]
            box_lows = lows[start_idx:i]
            
            box_top = np.max(box_highs)
            box_bottom = np.min(box_lows)
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
            
            is_uptrend_before = trend_move_up > (atr[start_idx] * cfg["TREND_MIN_ATR_MULTIPLIER"])
            is_downtrend_before = trend_move_down > (atr[start_idx] * cfg["TREND_MIN_ATR_MULTIPLIER"])

            if breakout_close > box_top * (1 + cfg["TRUE_BREAKOUT_MIN_PCT"]):
                if not is_uptrend_before: continue
                
                entry = breakout_close
                structural_sl = box_bottom
                prior_high = np.max(highs[trend_idx:start_idx])
                target_price = prior_high if prior_high > entry else None
                
                final_sl, tp, safe_sl, _ = compute_safe_sl_and_tp("Bullish", entry, structural_sl, target_price, box_height, cfg)

                nodes = [(df.index[trend_idx], closes[trend_idx]), (df.index[start_idx], box_bottom), (df.index[i], entry)]
                
                pattern = {
                    "name": "Box Breakout", "pattern": "Box Breakout", "pattern_type": "Continuation",
                    "bias": "Bullish", "match": 100.0, "nodes": nodes,
                    "entry": float(round(entry, 5)), "sl": float(round(final_sl, 5)), "tp": float(round(tp, 5)),
                    "structural_sl": float(round(structural_sl, 5)),
                    "neckline_start_idx": df.index[start_idx], "neckline_end_idx": df.index[i],
                    "neckline_nodes": [(df.index[start_idx], box_top), (df.index[i], box_top), (df.index[start_idx], box_bottom), (df.index[i], box_bottom)], # Box corners
                    "target_nodes": [(df.index[i], float(round(entry, 5))), (df.index[i], float(round(tp, 5)))],
                    "end_pos": i, "Entry": float(round(entry, 5)),
                    "Pattern": "Box Breakout (Bullish)", "Entry Conditions": "Trend + Box + Breakout",
                }
                patterns.append(pattern)
                break

            elif breakout_close < box_bottom * (1 - cfg["TRUE_BREAKOUT_MIN_PCT"]):
                if not is_downtrend_before: continue
                
                entry = breakout_close
                structural_sl = box_top
                prior_low = np.min(lows[trend_idx:start_idx])
                target_price = prior_low if prior_low < entry else None
                
                final_sl, tp, safe_sl, _ = compute_safe_sl_and_tp("Bearish", entry, structural_sl, target_price, box_height, cfg)

                nodes = [(df.index[trend_idx], closes[trend_idx]), (df.index[start_idx], box_top), (df.index[i], entry)]
                
                pattern = {
                    "name": "Box Breakout", "pattern": "Box Breakout", "pattern_type": "Continuation",
                    "bias": "Bearish", "match": 100.0, "nodes": nodes,
                    "entry": float(round(entry, 5)), "sl": float(round(final_sl, 5)), "tp": float(round(tp, 5)),
                    "structural_sl": float(round(structural_sl, 5)),
                    "neckline_start_idx": df.index[start_idx], "neckline_end_idx": df.index[i],
                    "neckline_nodes": [(df.index[start_idx], box_top), (df.index[i], box_top), (df.index[start_idx], box_bottom), (df.index[i], box_bottom)],
                    "target_nodes": [(df.index[i], float(round(entry, 5))), (df.index[i], float(round(tp, 5)))],
                    "end_pos": i, "Entry": float(round(entry, 5)),
                    "Pattern": "Box Breakout (Bearish)", "Entry Conditions": "Trend + Box + Breakout",
                }
                patterns.append(pattern)
                break

    patterns.sort(key=lambda x: x["end_pos"])
    for p in patterns:
        p.update(simulate_trade_outcome(p, df, cfg))
        
    return patterns

def simulate_trade_outcome(pattern, df, cfg):
    bias = pattern["bias"]
    entry = float(pattern["entry"])
    initial_sl = float(pattern["sl"])
    sl = initial_sl
    tp = float(pattern["tp"])
    end_idx = pattern["neckline_end_idx"]

    head_size = abs(tp - entry) / cfg["TP_REACH_FACTOR"] if cfg["TP_REACH_FACTOR"] > 0 else abs(tp-entry)
    
    if end_idx not in df.index: return {"Result": "OPEN"}
    post_df = df.loc[end_idx:]
    if len(post_df) <= 1: return {"Result": "OPEN"}

    stats = {
        "Result": "OPEN", "Head Result": "OPEN", "Max Reach %": 0.0, "SL Safety %": 0.0,
        "Max Extension %": 0.0, "Extension Beyond TP %": 0.0, "TP Hit At Candle": None,
        "Extension Duration Candles": 0, "Entry Date": str(end_idx), "Exit Date": None,
        "candles_to_exit": 0, "progress_ratio": 0.0, "Breakeven Activated": False, "Breakeven Exit": False,
        "Trailing Stage": 0, "Initial SL": initial_sl, "Final SL": initial_sl,
        "Loss Category": None, "Pattern Duration": 0, "Timeout Used": 0,
    }

    total_tp_dist = abs(tp - entry)
    total_sl_dist = abs(initial_sl - entry)
    max_favorable = 0.0; max_adverse = 0.0; full_window_max = 0.0
    tp_hit_candle = None; max_ext_candle = 0; exited = False

    highs = post_df["High"].values
    lows = post_df["Low"].values
    closes = post_df["Close"].values
    indices = post_df.index

    for candle_count in range(1, len(highs)):
        high = highs[candle_count]
        low = lows[candle_count]
        close = closes[candle_count]
        idx = indices[candle_count]

        if bias == "Bearish":
            favorable = max(0.0, entry - low); adverse = max(0.0, high - entry)
        else:
            favorable = max(0.0, high - entry); adverse = max(0.0, entry - low)
        progress = (favorable / total_tp_dist) if total_tp_dist > 0 else 0.0
        progress_head = (favorable / head_size) if head_size > 0 else 0.0

        if cfg.get("MEASURE_FULL_EXTENSION", True) and total_tp_dist > 0:
            if progress * 100 > full_window_max:
                full_window_max = progress * 100; max_ext_candle = candle_count

        if not exited:
            if total_tp_dist > 0: max_favorable = max(max_favorable, progress * 100)
            if total_sl_dist > 0: max_adverse = max(max_adverse, adverse / total_sl_dist * 100)
        if exited: continue

        for stage_idx, (th, ph) in enumerate(cfg["TRAILING_LEVELS_HEAD"]):
            if progress_head < th: break
            new_sl = entry - ph * head_size if bias == "Bearish" else entry + ph * head_size
            if bias == "Bearish":
                if new_sl < sl: sl = new_sl; stats["Trailing Stage"] = stage_idx + 1
            else:
                if new_sl > sl: sl = new_sl; stats["Trailing Stage"] = stage_idx + 1

        stats["Final SL"] = sl

        if bias == "Bearish":
            hit_sl = high >= sl; hit_tp = low <= tp
        else:
            hit_sl = low <= sl; hit_tp = high >= tp

        if hit_sl and not hit_tp:
            is_profit = sl < entry if bias == "Bearish" else sl > entry
            if is_profit:
                stats["Result"] = "WIN"; stats["Loss Category"] = "trailing_win"
            else:
                stats["Result"] = "LOSS"
                r = max_favorable
                if r < 5: stats["Loss Category"] = "immediate_rejection"
                elif r < 30: stats["Loss Category"] = "early_reversal"
                elif r < 70: stats["Loss Category"] = "mid_reversal"
                else: stats["Loss Category"] = "late_reversal"
            stats["exit_price"] = sl; stats["candles_to_exit"] = candle_count
            stats["Exit Date"] = str(idx); exited = True; continue

        elif hit_tp:
            stats["Result"] = "WIN"; stats["Loss Category"] = "success"
            stats["exit_price"] = tp; stats["candles_to_exit"] = candle_count
            stats["Exit Date"] = str(idx); tp_hit_candle = candle_count; exited = True; continue

    stats["Max Reach %"] = round(max_favorable, 1)
    stats["SL Safety %"] = round(100 - max_adverse, 1) if max_adverse <= 100 else 0.0
    stats["Max Extension %"] = round(full_window_max, 1)
    stats["Extension Beyond TP %"] = round(max(0.0, full_window_max - 100.0), 1)
    stats["TP Hit At Candle"] = tp_hit_candle
    stats["Extension Duration Candles"] = max(0, max_ext_candle - tp_hit_candle) if tp_hit_candle else 0

    if stats["Result"] == "WIN": stats["progress_ratio"] = 100.0
    return stats

# الواجهات المتوافقة
def run_full_analysis(df, interval="1h", symbol=None):
    cfg = get_symbol_config(symbol)
    if df is None or df.empty: return {"error": "No data"}
    df = calculate_indicators(df, cfg)
    patterns = detect_box_breakouts(df, is_backtest=False, cfg=cfg)
    if not patterns: return {"signal": "WAITING", "pattern": "NO PATTERN", "bias": "Neutral", "df": df}
    latest = patterns[-1]
    return {
        "df": df, "signal": "STRONG BUY" if latest["bias"]=="Bullish" else "STRONG SELL",
        "pattern": latest["pattern"], "bias": latest["bias"], "entry": latest["entry"],
        "sl": latest["sl"], "tp": latest["tp"], "nodes": latest["nodes"],
        "neckline_nodes": latest.get("neckline_nodes", []), "target_nodes": latest.get("target_nodes", []),
    }

def backtest_strategy(df, interval="1h", symbol=None):
    cfg = get_symbol_config(symbol)
    if df is None or df.empty: return []
    df = calculate_indicators(df, cfg)
    patterns = detect_box_breakouts(df, is_backtest=True, cfg=cfg)
    trades = []
    for p in patterns:
        trades.append({
            "Symbol": symbol, "Pattern": p["pattern"], "Bias": p["bias"], 
            "Result": p.get("Result", "OPEN"), "Entry Price": p["entry"],
            "Stop Loss": p["sl"], "Take Profit": p["tp"], "Entry Date": p.get("Entry Date"),
            "Exit Date": p.get("Exit Date"), "Max Reach %": p.get("Max Reach %", 0), "nodes": p["nodes"]
        })
    return trades

def diagnose_filters(df, interval="1h", symbol=None):
    cfg = get_symbol_config(symbol)
    return {"error": None, "smart_diagnosis": {"verdict": "جاري التطوير"}}

def diagnose_no_signals(df, interval="1h", symbol=None, is_backtest=True):
    cfg = get_symbol_config(symbol)
    if df is None or df.empty: return {"error": "بيانات غير كافية"}
    # (تبسيط دالة التشخيص للصناديق)
    return {
        "total_pivots": 0, "raw_candidates": 0,
        "rejected_trend": 0, "rejected_box_height": 0, "rejected_touches": 0,
        "rejected_breakout_strength": 0, "rejected_volume": 0, "passed": 0
    }
