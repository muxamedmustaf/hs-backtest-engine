# -*- coding: utf-8 -*-
"""
ENGINE.PY — Box Hunter Pro (3-Phase Logic)
===================================================
المرحلة 1: موجة حافزة قوية (Impulse) تسبق التجميع.
المرحلة 2: منطقة متعرجة أفقية (Box) بقمم متساوية وقيعان متساوية (لمستان على الأقل لكل منهما).
المرحلة 3: كسر حقيقي وقوي بإغلاق شمعة خارج الصندوق.
"""
import pandas as pd
import numpy as np

CONFIG = {
    "IMPULSE_MIN_ATR": 3.0,        # شرط 1: الموجة يجب أن تكون 3 أضعاف التقلب (ATR)
    "IMPULSE_LOOKBACK": 20,        # نبحث عن الموجة في آخر 20 شمعة قبل الصندوق
    
    "BOX_MIN_CANDLES": 15,         # شرط 2: الصندوق لا يقل عن 15 شمعة
    "BOX_MAX_CANDLES": 80,         # الصندوق لا يزيد عن 80 شمعة
    "BOX_MAX_HEIGHT_PCT": 0.05,    # ارتفاع الصندوق لا يتجاوز 5% من السعر (تجميع أفقي)
    "MIN_TOUCHES": 2,              # يجب لمس القمة مرتين والقاع مرتين
    "TOUCH_TOLERANCE": 0.003,      # نسبة التسامح لاعتبار اللمسة "متساوية" (0.3%)
    
    "BREAKOUT_MIN_BODY_ATR": 1.2,  # شرط 3: جسم شمعة الكسر يجب أن يكون قوياً (1.2x ATR)
    
    "TP_REACH_FACTOR": 1.5,        # الهدف 1.5x ارتفاع الصندوق
    "TRAILING_LEVELS_HEAD": [(1.00, 0.30), (1.50, 0.80), (2.00, 1.20)],
    "SAFE_SL_MARGIN": 0.10,
    "USE_SAFE_SL": True,
}

def calculate_indicators(df):
    df = df.copy()
    hl = df["High"] - df["Low"]
    hc = np.abs(df["High"] - df["Close"].shift())
    lc = np.abs(df["Low"] - df["Close"].shift())
    tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    df["ATR"] = tr.rolling(14).mean()
    return df

def compute_safe_sl_and_tp(bias, entry, structural_sl, box_height):
    structural_risk = abs(entry - structural_sl)
    if bias == "Bullish":
        safe_sl = structural_sl - (structural_risk * CONFIG["SAFE_SL_MARGIN"])
    else:
        safe_sl = structural_sl + (structural_risk * CONFIG["SAFE_SL_MARGIN"])
    final_sl = safe_sl if CONFIG["USE_SAFE_SL"] else structural_sl
    
    target = box_height * CONFIG["TP_REACH_FACTOR"]
    tp = entry + target if bias == "Bullish" else entry - target
    return final_sl, tp

def simulate_trade(pattern, df):
    bias = pattern["bias"]
    entry = float(pattern["entry"])
    sl = float(pattern["sl"])
    tp = float(pattern["tp"])
    end_idx = pattern["neckline_end_idx"]
    
    if end_idx not in df.index: return {"Result": "OPEN"}
    post_df = df.loc[end_idx:]
    if len(post_df) <= 1: return {"Result": "OPEN"}

    stats = {
        "Result": "OPEN", "Head Result": "OPEN", "Max Reach %": 0.0, "SL Safety %": 0.0, 
        "Max Extension %": 0.0, "TP Hit At Candle": None, "Entry Date": str(end_idx), 
        "Exit Date": None, "candles_to_exit": 0, "progress_ratio": 0.0, 
        "Trailing Stage": 0, "Initial SL": sl, "Final SL": sl, "Loss Category": None, "exit_price": None
    }
    
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
    if stats["Result"] == "WIN": stats["progress_ratio"] = 100.0
    return stats

def detect_box_breakouts(df, symbol=None):
    patterns = []
    n = len(df)
    if n < 100: return patterns

    highs, lows, closes, opens = df["High"].values, df["Low"].values, df["Close"].values, df["Open"].values
    atr = df["ATR"].values
    
    for i in range(60, n):
        # 🎯 المرحلة 3: فحص الكسر (Breakout Candle)
        candle_body = abs(closes[i] - opens[i])
        if candle_body < (atr[i] * CONFIG["BREAKOUT_MIN_BODY_ATR"]): continue
        
        is_bull_breakout = closes[i] > opens[i]
        is_bear_breakout = closes[i] < opens[i]

        # نبحث عن الصندوق بالبحث العكسي (من الأكبر للأصغر)
        for box_len in range(CONFIG["BOX_MAX_CANDLES"], CONFIG["BOX_MIN_CANDLES"] - 1, -1):
            start_idx = i - box_len
            if start_idx < CONFIG["IMPULSE_LOOKBACK"]: continue
            
            # 🎯 المرحلة 1: فحص الموجة الحافزة (Impulse)
            trend_idx = start_idx - CONFIG["IMPULSE_LOOKBACK"]
            impulse_move = abs(closes[start_idx] - closes[trend_idx])
            
            if impulse_move < (atr[trend_idx] * CONFIG["IMPULSE_MIN_ATR"]): continue
            
            # التأكد من اتجاه الموجة (صاعدة للكسر الصاعد، هابطة للكسر الهابط)
            if is_bull_breakout and closes[start_idx] <= closes[trend_idx]: continue
            if is_bear_breakout and closes[start_idx] >= closes[trend_idx]: continue

            # 🎯 المرحلة 2: فحص التجميع (Consolidation Box)
            box_highs = highs[start_idx:i]
            box_lows = lows[start_idx:i]
            box_top = np.max(box_highs)
            box_bottom = np.min(box_lows)
            box_height = box_top - box_bottom
            box_mid = (box_top + box_bottom) / 2
            
            # شرط العرض: الصندوق يجب أن يكون أفقياً وضيقاً
            if box_height == 0 or (box_height / box_mid) > CONFIG["BOX_MAX_HEIGHT_PCT"]: continue

            # شرط اللمسات المتساوية:
            tol = box_mid * CONFIG["TOUCH_TOLERANCE"]
            
            # كم مرة لمس السعر القمة؟
            touches_top = sum(1 for h in box_highs if h >= box_top - tol)
            # كم مرة لمس السعر القاع؟
            touches_bottom = sum(1 for l in box_lows if l <= box_bottom + tol)

            if touches_top < CONFIG["MIN_TOUCHES"] or touches_bottom < CONFIG["MIN_TOUCHES"]: continue

            # إذا وصلنا هنا، فهذا صندوق مثالي متوافق مع كل شروطك
            box_nodes = [
                (df.index[start_idx], box_top), (df.index[i], box_top),
                (df.index[start_idx], box_bottom), (df.index[i], box_bottom)
            ]
            trend_nodes = [(df.index[trend_idx], closes[trend_idx]), (df.index[start_idx], box_bottom if is_bull_breakout else box_top), (df.index[i], closes[i])]

            # كسر صاعد
            if is_bull_breakout and closes[i] > box_top:
                final_sl, tp = compute_safe_sl_and_tp("Bullish", closes[i], box_mid, box_height)
                pattern = {
                    "name": "Impulse + Box", "pattern": "Box Breakout", "pattern_type": "Continuation",
                    "bias": "Bullish", "match": 100.0, "nodes": trend_nodes,
                    "entry": float(round(closes[i], 5)), "sl": float(round(final_sl, 5)), "tp": float(round(tp, 5)),
                    "neckline_nodes": box_nodes, "end_pos": i, "neckline_end_idx": df.index[i]
                }
                pattern.update(simulate_trade(pattern, df))
                patterns.append(pattern)
                break # وجدنا الصندوق الأكبر المثالي، ننتقل لشمعة الكسر التالية

            # كسر هابط
            elif is_bear_breakout and closes[i] < box_bottom:
                final_sl, tp = compute_safe_sl_and_tp("Bearish", closes[i], box_mid, box_height)
                pattern = {
                    "name": "Impulse + Box", "pattern": "Box Breakout", "pattern_type": "Continuation",
                    "bias": "Bearish", "match": 100.0, "nodes": trend_nodes,
                    "entry": float(round(closes[i], 5)), "sl": float(round(final_sl, 5)), "tp": float(round(tp, 5)),
                    "neckline_nodes": box_nodes, "end_pos": i, "neckline_end_idx": df.index[i]
                }
                pattern.update(simulate_trade(pattern, df))
                patterns.append(pattern)
                break

    return patterns

# دوال التوافق مع الواجهة
def calculate_indicators_for_df(df, cfg=None): return calculate_indicators(df)
def get_symbol_config(symbol): return CONFIG

def run_full_analysis(df, interval="1h", symbol=None):
    df = calculate_indicators(df)
    patterns = detect_box_breakouts(df, symbol)
    if not patterns: return {"signal": "WAITING", "pattern": "NO PATTERN", "bias": "Neutral", "df": df}
    latest = patterns[-1]
    return {
        "df": df, "signal": "STRONG BUY" if latest["bias"]=="Bullish" else "STRONG SELL", 
        "pattern": latest["pattern"], "bias": latest["bias"], "entry": latest["entry"], 
        "sl": latest["sl"], "tp": latest["tp"], "nodes": latest["nodes"], 
        "neckline_nodes": latest["neckline_nodes"], "Trade Recommendation": f"إشارة {latest['bias']} من صندوق تجميع قوي."
    }

def backtest_strategy(df, interval="1h", symbol=None):
    df = calculate_indicators(df)
    patterns = detect_box_breakouts(df, symbol)
    trades = []
    for p in patterns:
        p["Symbol"] = symbol; p["Entry Price"] = p["entry"]; p["Stop Loss"] = p["sl"]; p["Take Profit"] = p["tp"]
        trades.append(p)
    return trades

def diagnose_no_signals(df, interval="1h", symbol=None, is_backtest=True): return {}
def diagnose_filters(df, interval="1h", symbol=None): return {"smart_diagnosis": {"verdict": "نظام الصندوق الثلاثي"}}
