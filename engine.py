# -*- coding: utf-8 -*-
"""
ENGINE.PY — Box Hunter Pro (Pure Price Action)
===================================================
- استراتيجية برايس أكشن 100% (بدون أي مؤشرات).
- المرحلة 1: موجة حافزة قوية (نسبة مئوية من السعر).
- المرحلة 2: تجميع (Box) بقمم وقيعان متساوية.
- المرحلة 3: كسر حقيقي (إغلاق شمعة قوية خارج الصندوق).
- المرحلة 4: إعادة اختبار (Retest) قوية ثم الدخول.
- إدارة مخاطر: وقف خسارة هيكلي (تحت شمعة الاختبار).
"""
import pandas as pd
import numpy as np

CONFIG = {
    # إعدادات الموجة الحافزة (بدون مؤشرات - نسبة مئوية فقط)
    "IMPULSE_MIN_PCT": 0.04,       # الموجة يجب أن تتحرك 4% على الأقل (للكريبتو والفوركس)
    "IMPULSE_MAX_LOOKBACK": 60,    # نبحث عن بداية الموجة في آخر 60 شمعة
    "MAX_RETRACEMENT_PCT": 0.38,   # التصحيح (الصندوق) لا يتجاوز 38.2% من الموجة
    
    # إعدادات الصندوق (تجميع)
    "BOX_MIN_CANDLES": 15,         
    "BOX_MAX_CANDLES": 80,         
    "BOX_MAX_HEIGHT_PCT": 0.03,    # ارتفاع الصندوق لا يتجاوز 3% من السعر (تجميع ضيق)
    "MIN_TOUCHES": 2,              # لمسة للقمة ولمسة للقاع على الأقل
    "TOUCH_TOLERANCE": 0.002,      # تسامح 0.2% لاعتبار اللمسات متساوية
    
    # إعدادات الكسر (Breakout)
    "BREAKOUT_MIN_BODY_PCT": 0.005, # جسم شمعة الكسر يجب أن يكون 0.5% من السعر (قوة)
    
    # إعدادات الاختبار (Retest)
    "REQUIRE_RETEST": True,        
    "RETEST_MAX_CANDLES": 8,       
    "RETEST_TOLERANCE": 0.002,     
    "RETEST_STRONG_CLOSE_RATIO": 0.6, # الإغلاق في الـ 60% العلوية (شراء) أو السفلية (بيع)
    
    # إدارة الصفقة
    "TP_REACH_FACTOR": 1.5,        # الهدف 1.5x ارتفاع الصندوق
    "TRAILING_LEVELS_HEAD": [(1.00, 0.30), (1.50, 0.80), (2.00, 1.20)],
    "SAFE_SL_MARGIN": 0.05,        # هامش أمان صغير جداً لأن SL هيكلي
    "USE_SAFE_SL": True,
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

def calculate_indicators(df, cfg=None):
    # 🚀 تم إلغاء جميع المؤشرات. نرجع الداتا كما هي (برايس أكشن خالص)
    return df.copy()

def compute_safe_sl_and_tp(bias, entry, structural_sl, box_height, cfg=None):
    structural_risk = abs(entry - structural_sl)
    if bias == "Bullish":
        safe_sl = structural_sl - (structural_risk * CONFIG["SAFE_SL_MARGIN"])
    else:
        safe_sl = structural_sl + (structural_risk * CONFIG["SAFE_SL_MARGIN"])
    final_sl = safe_sl if CONFIG["USE_SAFE_SL"] else structural_sl
    
    target = box_height * CONFIG["TP_REACH_FACTOR"]
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

def detect_box_breakouts(df, symbol=None, is_backtest=True):
    patterns = []
    n = len(df)
    if n < 100: return patterns

    # برايس أكشن خالص: فقط السعر
    highs, lows, closes, opens = df["High"].values, df["Low"].values, df["Close"].values, df["Open"].values
    
    for i in range(60, n):
        # 1. فحص شمعة الكسر (قوة الجسم بنسبة مئوية من السعر)
        candle_body = abs(closes[i] - opens[i])
        if candle_body < (closes[i] * CONFIG["BREAKOUT_MIN_BODY_PCT"]): continue
        
        is_bull_breakout = closes[i] > opens[i]
        is_bear_breakout = closes[i] < opens[i]

        for box_len in range(CONFIG["BOX_MAX_CANDLES"], CONFIG["BOX_MIN_CANDLES"] - 1, -1):
            start_idx = i - box_len
            if start_idx < CONFIG["IMPULSE_MAX_LOOKBACK"]: continue
            
            box_highs = highs[start_idx:i]
            box_lows = lows[start_idx:i]
            box_top = np.max(box_highs)
            box_bottom = np.min(box_lows)
            box_height = box_top - box_bottom
            box_mid = (box_top + box_bottom) / 2
            
            # الصندوق يجب أن يكون ضيقاً (نسبة من السعر)
            if box_height == 0 or (box_height / box_mid) > CONFIG["BOX_MAX_HEIGHT_PCT"]: continue

            tol = box_mid * CONFIG["TOUCH_TOLERANCE"]
            touches_top = sum(1 for h in box_highs if h >= box_top - tol)
            touches_bottom = sum(1 for l in box_lows if l <= box_bottom + tol)

            if touches_top < CONFIG["MIN_TOUCHES"] or touches_bottom < CONFIG["MIN_TOUCHES"]: continue

            # 2. فحص الموجة الحافزة (نسبة مئوية)
            lookback_start = max(0, start_idx - CONFIG["IMPULSE_MAX_LOOKBACK"])
            if is_bull_breakout:
                trend_idx = lookback_start + np.argmin(lows[lookback_start:start_idx])
                impulse_move_pct = (box_top - lows[trend_idx]) / lows[trend_idx]
            else:
                trend_idx = lookback_start + np.argmax(highs[lookback_start:start_idx])
                impulse_move_pct = (highs[trend_idx] - box_bottom) / highs[trend_idx]

            # شرط قوة الموجة: 4% (أو ما تحدده)
            if impulse_move_pct < CONFIG["IMPULSE_MIN_PCT"]: continue
            
            # شرط الارتداد: الصندوق لا يمحو أكثر من 38.2%
            impulse_move_abs = abs(closes[start_idx] - closes[trend_idx])
            if impulse_move_abs > 0 and (box_height / impulse_move_abs) > CONFIG["MAX_RETRACEMENT_PCT"]: continue

            # 3. فحص الاختبار (Retest) البرايس أكشن
            actual_entry_idx = i
            actual_entry_price = closes[i]
            retest_low = lows[i]
            retest_high = highs[i]

            if CONFIG.get("REQUIRE_RETEST", False):
                retest_found = False
                for j in range(i + 1, min(n, i + 1 + CONFIG["RETEST_MAX_CANDLES"])):
                    if is_bull_breakout:
                        if lows[j] <= box_top * (1 + CONFIG["RETEST_TOLERANCE"]) and closes[j] > box_top:
                            candle_range = highs[j] - lows[j]
                            if candle_range > 0 and (closes[j] - lows[j]) / candle_range >= CONFIG["RETEST_STRONG_CLOSE_RATIO"]:
                                retest_found = True
                                actual_entry_idx = j
                                actual_entry_price = closes[j]
                                retest_low = lows[j]
                                break
                    elif is_bear_breakout:
                        if highs[j] >= box_bottom * (1 - CONFIG["RETEST_TOLERANCE"]) and closes[j] < box_bottom:
                            candle_range = highs[j] - lows[j]
                            if candle_range > 0 and (highs[j] - closes[j]) / candle_range >= CONFIG["RETEST_STRONG_CLOSE_RATIO"]:
                                retest_found = True
                                actual_entry_idx = j
                                actual_entry_price = closes[j]
                                retest_high = highs[j]
                                break
                
                if not retest_found: continue

            box_nodes = [
                (df.index[start_idx], box_top), (df.index[actual_entry_idx], box_top),
                (df.index[start_idx], box_bottom), (df.index[actual_entry_idx], box_bottom)
            ]
            trend_nodes = [
                (df.index[trend_idx], lows[trend_idx] if is_bull_breakout else highs[trend_idx]), 
                (df.index[start_idx], box_bottom if is_bull_breakout else box_top), 
                (df.index[actual_entry_idx], actual_entry_price)
            ]

            # 4. إدارة الصفقة (هيكلية)
            if is_bull_breakout and actual_entry_price > box_top:
                structural_sl = min(retest_low, box_bottom) 
                final_sl, tp, safe_sl, struct_sl = compute_safe_sl_and_tp("Bullish", actual_entry_price, structural_sl, box_height)
                pattern = {
                    "name": "Impulse + Box + Retest", "pattern": "Box Breakout", "pattern_type": "Continuation",
                    "bias": "Bullish", "match": 100.0, "nodes": trend_nodes,
                    "entry": float(round(actual_entry_price, 5)), "sl": float(round(final_sl, 5)), "tp": float(round(tp, 5)),
                    "structural_sl": float(round(struct_sl, 5)), "safe_sl": float(round(safe_sl, 5)),
                    "neckline_nodes": box_nodes, "end_pos": actual_entry_idx, "neckline_end_idx": df.index[actual_entry_idx],
                    "Entry": float(round(actual_entry_price, 5)), "Pattern": "Box Breakout (Bullish)"
                }
                pattern.update(simulate_trade(pattern, df))
                pattern["Trade Recommendation"] = f"🟢 Box Breakout + Retest:\n- الدخول: {pattern['entry']}\n- SL: {pattern['sl']}\n- TP: {pattern['tp']}"
                patterns.append(pattern)
                break

            elif is_bear_breakout and actual_entry_price < box_bottom:
                structural_sl = max(retest_high, box_top) 
                final_sl, tp, safe_sl, struct_sl = compute_safe_sl_and_tp("Bearish", actual_entry_price, structural_sl, box_height)
                pattern = {
                    "name": "Impulse + Box + Retest", "pattern": "Box Breakout", "pattern_type": "Continuation",
                    "bias": "Bearish", "match": 100.0, "nodes": trend_nodes,
                    "entry": float(round(actual_entry_price, 5)), "sl": float(round(final_sl, 5)), "tp": float(round(tp, 5)),
                    "structural_sl": float(round(struct_sl, 5)), "safe_sl": float(round(safe_sl, 5)),
                    "neckline_nodes": box_nodes, "end_pos": actual_entry_idx, "neckline_end_idx": df.index[actual_entry_idx],
                    "Entry": float(round(actual_entry_price, 5)), "Pattern": "Box Breakout (Bearish)"
                }
                pattern.update(simulate_trade(pattern, df))
                pattern["Trade Recommendation"] = f"🔴 Box Breakout + Retest:\n- الدخول: {pattern['entry']}\n- SL: {pattern['sl']}\n- TP: {pattern['tp']}"
                patterns.append(pattern)
                break

    return patterns

# دوال التوافق مع الواجهة
def run_full_analysis(df, interval="1h", symbol=None):
    cfg = get_symbol_config(symbol)
    df = calculate_indicators(df, cfg)
    patterns = detect_box_breakouts(df, symbol, is_backtest=False)
    if not patterns: return {"signal": "WAITING", "pattern": "NO PATTERN", "bias": "Neutral", "df": df}
    latest = patterns[-1]
    return {
        "df": df, "signal": "STRONG BUY" if latest["bias"]=="Bullish" else "STRONG SELL", 
        "pattern": latest["pattern"], "bias": latest["bias"], "entry": latest["entry"], 
        "sl": latest["sl"], "tp": latest["tp"], "nodes": latest["nodes"], 
        "neckline_nodes": latest["neckline_nodes"], "Trade Recommendation": latest["Trade Recommendation"]
    }

def backtest_strategy(df, interval="1h", symbol=None):
    cfg = get_symbol_config(symbol)
    df = calculate_indicators(df, cfg)
    patterns = detect_box_breakouts(df, symbol, is_backtest=True)
    trades = []
    for p in patterns:
        p["Symbol"] = symbol; p["Entry Price"] = p["entry"]; p["Stop Loss"] = p["sl"]; p["Take Profit"] = p["tp"]
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
