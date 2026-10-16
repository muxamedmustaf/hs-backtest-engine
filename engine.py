# -*- coding: utf-8 -*-
"""
ENGINE.PY — H&S Detector (Reversal + Continuation)
===================================================
- كشف H&S الانعكاسي والاستمراري
- فلتر الاتجاه السابق لكلا النوعين
- وقف آمن 15% + TP = 1× الرأس + Trailing بوحدات الرأس
- قياس الامتداد الكامل
- [تحديث]: فلتر الكتف الأيمن (يجب أن يكون أعلى/أدنى نقطة بعد الرأس مباشرة)
"""
import pandas as pd
import numpy as np

CONFIG = {
    "ZIGZAG_DEPTH": 12,
    "ZIGZAG_BACKSTEP": 7,
    "MIN_WAVE_CANDLES": 5,
    "SHOULDER_DIFF_MAX_RATIO": 0.35,
    "HEAD_PROPORTION_MIN_RATIO": 0.15,
    "NECKLINE_DIFF_MAX_RATIO": 0.10,
    "LIVE_MAX_BREAKOUT_CANDLES": 10,
    "BREAKOUT_MIN_PCT": 0.0001,
    "REQUIRE_VOLUME_BREAKOUT": False,
    "VOLUME_FACTOR": 1.2,
    "VOLUME_MA_PERIOD": 20,
    "TP_REACH_FACTOR": 1.0,  # الهدف = 1× طول الرأس فقط
    "USE_SAFE_SL": True,
    "SAFE_SL_MARGIN": 0.15,
    "TRAILING_LEVELS_HEAD": [
        (1.00, 0.00),
        (1.40, 0.60),
        (1.70, 1.00),
        (1.90, 1.50),
    ],
    "MEASURE_FULL_EXTENSION": True,
    "ENABLE_REVERSAL": True,
    "ENABLE_CONTINUATION": True,
}

TIMEOUT_STATISTICAL_FLOOR = 200
TIMEOUT_DURATION_MULTIPLIER = 3

REASON_MAP = {
    "immediate_rejection": {"reason": "السعر رفض خط العنق فورًا.", "action": "انتظر إعادة اختبار.", "prevention": "لا تدخل بأول لمسة."},
    "early_reversal": {"reason": "انعكاس مبكر قبل 30%.", "action": "نقل SL للتعادل.", "prevention": "Trailing مبكر."},
    "mid_reversal": {"reason": "انعكاس متوسط.", "action": "خروج جزئي 50%.", "prevention": "TP جزئي."},
    "late_reversal": {"reason": "وصل 70%+ ثم عاد.", "action": "Trailing 30%.", "prevention": "راقب الأخبار."},
    "timeout": {"reason": "انتهت المدة دون TP/SL.", "action": "أغلق يدويًا.", "prevention": "فلتر ADX."},
    "breakeven": {"reason": "تعادل — حماية رأس المال.", "action": "لا شيء.", "prevention": "استمر."},
    "success": {"reason": "وصل الهدف.", "action": "كرر الإعداد.", "prevention": "—"},
    "trailing_win": {"reason": "خرج بـ Trailing.", "action": "لا شيء.", "prevention": "—"},
    "open": {"reason": "ما زالت مفتوحة.", "action": "راقب.", "prevention": "—"},
}


def _get_max_gap(interval):
    return {"1m": 120, "5m": 50, "15m": 30, "30m": 25, "1h": 20,
            "4h": 15, "1d": 10, "1wk": 5}.get(interval, 50)


def _get_max_pattern_duration(interval):
    return {"1m": 600, "5m": 200, "15m": 150, "30m": 120, "1h": 100,
            "4h": 80, "1d": 60, "1wk": 30}.get(interval, 200)


def compute_safe_sl_and_tp(bias, entry, structural_sl, head_size):
    structural_risk = abs(entry - structural_sl)
    if bias == "Bullish":
        safe_sl = structural_sl - (structural_risk * CONFIG["SAFE_SL_MARGIN"])
    else:
        safe_sl = structural_sl + (structural_risk * CONFIG["SAFE_SL_MARGIN"])
    final_sl = safe_sl if CONFIG["USE_SAFE_SL"] else structural_sl
    target = head_size * CONFIG["TP_REACH_FACTOR"]
    tp = entry + target if bias == "Bullish" else entry - target
    return final_sl, tp, safe_sl, structural_sl


def generate_trade_recommendation(bias, entry, sl, tp, structural_sl, head_size, pattern_name):
    risk = abs(entry - sl)
    reward = abs(tp - entry)
    rr = round(reward / risk, 2) if risk > 0 else 0.0
    factor = CONFIG["TP_REACH_FACTOR"]
    margin = round(CONFIG["SAFE_SL_MARGIN"] * 100, 0)
    if bias == "Bullish":
        return (
            f"🟢 {pattern_name}:\n"
            f"- الدخول: اختراق ({entry}).\n"
            f"- SL: ({round(sl, 5)}) = القاع ({round(structural_sl, 5)}) + {margin}%.\n"
            f"- TP: ({round(tp, 5)}) = {factor}× الرأس.\n"
            f"- R:R = 1 : {rr}."
        )
    else:
        return (
            f"🔴 {pattern_name}:\n"
            f"- الدخول: كسر ({entry}).\n"
            f"- SL: ({round(sl, 5)}) = القمة ({round(structural_sl, 5)}) + {margin}%.\n"
            f"- TP: ({round(tp, 5)}) = {factor}× الرأس.\n"
            f"- R:R = 1 : {rr}."
        )


def calculate_indicators(df):
    df = df.copy()
    hl = df["High"] - df["Low"]
    hc = np.abs(df["High"] - df["Close"].shift())
    lc = np.abs(df["Low"] - df["Close"].shift())
    tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    df["ATR"] = tr.rolling(14).mean()
    df["Dynamic_Swing"] = (df["ATR"] / df["Close"]) * 0.5
    df["Dynamic_Swing"] = df["Dynamic_Swing"].fillna(0.001)
    if "Volume" in df.columns:
        v = pd.to_numeric(df["Volume"], errors="coerce").fillna(0.0)
        df["Volume"] = v
        df["Volume_MA"] = v.rolling(CONFIG["VOLUME_MA_PERIOD"]).mean().fillna(0.0)
    else:
        df["Volume"] = 0.0
        df["Volume_MA"] = 0.0
    return df


def calculate_zigzag(df, depth=12, backstep=6):
    df = df.copy()
    df["Pivot_H"] = np.nan
    df["Pivot_L"] = np.nan
    highs = df["High"].astype(float).values
    lows = df["Low"].astype(float).values
    n = len(df)
    if n < depth + backstep + 1:
        return df
    for i in range(depth, n - backstep):
        hw = highs[i - depth:i + backstep + 1]
        lw = lows[i - depth:i + backstep + 1]
        ch, cl = highs[i], lows[i]
        is_h = (ch == np.max(hw) and np.sum(hw == ch) == 1)
        is_l = (cl == np.min(lw) and np.sum(lw == cl) == 1)
        if is_h and not is_l:
            df.iloc[i, df.columns.get_loc("Pivot_H")] = ch
        elif is_l and not is_h:
            df.iloc[i, df.columns.get_loc("Pivot_L")] = cl
    return df


def get_chronological_pivots(df):
    raw = []
    for pos, (idx, row) in enumerate(df.iterrows()):
        if not pd.isna(row["Pivot_H"]):
            raw.append({"idx": idx, "pos": pos, "val": float(row["Pivot_H"]),
                        "type": "H", "dynamic_swing": float(row.get("Dynamic_Swing", 0.001))})
        elif not pd.isna(row["Pivot_L"]):
            raw.append({"idx": idx, "pos": pos, "val": float(row["Pivot_L"]),
                        "type": "L", "dynamic_swing": float(row.get("Dynamic_Swing", 0.001))})
    if not raw:
        return []
    clean = []
    for p in raw:
        if not clean:
            clean.append(p); continue
        last = clean[-1]
        ms = p["dynamic_swing"]
        if last["type"] != p["type"]:
            mv = abs(p["val"] - last["val"]) / max(abs(last["val"]), 1e-9)
            if mv >= ms:
                clean.append(p)
            else:
                if last["type"] == "H" and p["val"] > last["val"]: clean[-1] = p
                elif last["type"] == "L" and p["val"] < last["val"]: clean[-1] = p
        else:
            if p["type"] == "H" and p["val"] > last["val"]: clean[-1] = p
            elif p["type"] == "L" and p["val"] < last["val"]: clean[-1] = p
    final = []
    for p in clean:
        if not final:
            final.append(p)
        else:
            if final[-1]["type"] != p["type"]:
                final.append(p)
            else:
                if p["type"] == "H" and p["val"] > final[-1]["val"]: final[-1] = p
                elif p["type"] == "L" and p["val"] < final[-1]["val"]: final[-1] = p
    return final


def simulate_trade_outcome(pattern, df):
    bias = pattern["bias"]
    entry = float(pattern["entry"])
    initial_sl = float(pattern["sl"])
    sl = initial_sl
    tp = float(pattern["tp"])
    end_idx = pattern["neckline_end_idx"]

    head_size = abs(tp - entry) / CONFIG["TP_REACH_FACTOR"]
    head_pct = (head_size / entry * 100) if entry > 0 else 0
    MIN_HEAD_PCT = 0.10
    MAX_HEAD_PCT = 10.00

    if head_pct < MIN_HEAD_PCT:
        return {"Result": "SKIPPED", "Head Result": "SKIPPED", "Loss Category": "too_small",
                "Skip Reason": f"Head small ({head_pct:.3f}%)",
                "Max Reach %": 0, "Max Extension %": 0, "Extension Beyond TP %": 0,
                "SL Safety %": 0, "Entry Date": str(end_idx), "Exit Date": None,
                "candles_to_exit": 0, "progress_ratio": 0}
    if head_pct > MAX_HEAD_PCT:
        return {"Result": "SKIPPED", "Head Result": "SKIPPED", "Loss Category": "too_large",
                "Skip Reason": f"Head large ({head_pct:.3f}%)",
                "Max Reach %": 0, "Max Extension %": 0, "Extension Beyond TP %": 0,
                "SL Safety %": 0, "Entry Date": str(end_idx), "Exit Date": None,
                "candles_to_exit": 0, "progress_ratio": 0}

    nodes = pattern.get("nodes", [])
    if len(nodes) >= 6:
        try:
            fp = df.index.get_loc(nodes[0][0])
            hp = df.index.get_loc(nodes[-2][0])
            pattern_duration = max(1, hp - fp)
        except KeyError:
            pattern_duration = 50
    else:
        pattern_duration = 50

    TIMEOUT_CANDLES = max(TIMEOUT_STATISTICAL_FLOOR,
                          pattern_duration * TIMEOUT_DURATION_MULTIPLIER)
    TRAILING = CONFIG["TRAILING_LEVELS_HEAD"]

    breakeven_activated = False
    trailing_stage = 0
    stats = {
        "Result": "OPEN", "Head Result": "OPEN",
        "progress_ratio": 0.0, "candles_to_exit": 0,
        "exit_idx": None, "exit_price": None,
        "Entry Date": None, "Exit Date": None,
        "Max Reach %": 0.0, "SL Safety %": 0.0,
        "Max Extension %": 0.0, "Extension Beyond TP %": 0.0,
        "TP Hit At Candle": None, "Extension Duration Candles": 0,
        "Pattern Duration": pattern_duration, "Timeout Used": TIMEOUT_CANDLES,
        "Breakeven Activated": False, "Breakeven Exit": False,
        "Trailing Stage": 0, "Initial SL": initial_sl, "Final SL": initial_sl,
        "Loss Category": None,
    }

    if end_idx not in df.index: return stats
    post_df = df.loc[end_idx:]
    if len(post_df) <= 1: return stats

    stats["Entry Date"] = str(end_idx)
    total_tp_dist = abs(tp - entry)
    total_sl_dist = abs(initial_sl - entry)
    max_favorable = 0.0; max_adverse = 0.0; full_window_max = 0.0
    tp_hit_candle = None; max_ext_candle = 0; exited = False

    for candle_count, (idx, row) in enumerate(post_df.iloc[1:].iterrows(), start=1):
        high = float(row["High"]); low = float(row["Low"]); close = float(row["Close"])
        if bias == "Bearish":
            favorable = max(0.0, entry - low); adverse = max(0.0, high - entry)
        else:
            favorable = max(0.0, high - entry); adverse = max(0.0, entry - low)
        progress = (favorable / total_tp_dist) if total_tp_dist > 0 else 0.0
        progress_head = (favorable / head_size) if head_size > 0 else 0.0

        if CONFIG.get("MEASURE_FULL_EXTENSION", True) and total_tp_dist > 0:
            if progress * 100 > full_window_max:
                full_window_max = progress * 100; max_ext_candle = candle_count

        if not exited:
            if total_tp_dist > 0: max_favorable = max(max_favorable, progress * 100)
            if total_sl_dist > 0: max_adverse = max(max_adverse, adverse / total_sl_dist * 100)
        if exited:
            if candle_count >= TIMEOUT_CANDLES: break
            continue

        for stage_idx, (th, ph) in enumerate(TRAILING):
            if stage_idx < trailing_stage: continue
            if progress_head < th: break
            if ph == 0.0:
                new_sl = entry
            else:
                new_sl = entry - ph * head_size if bias == "Bearish" else entry + ph * head_size
            if bias == "Bearish":
                if new_sl < sl:
                    sl = new_sl; trailing_stage = stage_idx + 1
                    if ph == 0.0: breakeven_activated = True; stats["Breakeven Activated"] = True
            else:
                if new_sl > sl:
                    sl = new_sl; trailing_stage = stage_idx + 1
                    if ph == 0.0: breakeven_activated = True; stats["Breakeven Activated"] = True

        stats["Trailing Stage"] = trailing_stage; stats["Final SL"] = sl

        if bias == "Bearish":
            hit_sl = high >= sl; hit_tp = low <= tp
        else:
            hit_sl = low <= sl; hit_tp = high >= tp

        if hit_sl and not hit_tp:
            if bias == "Bearish":
                is_profit = sl < entry - 1e-9; is_be = abs(sl - entry) < 1e-9
            else:
                is_profit = sl > entry + 1e-9; is_be = abs(sl - entry) < 1e-9
            if is_be:
                stats["Result"] = "BREAKEVEN"; stats["Head Result"] = "BREAKEVEN"
                stats["Breakeven Exit"] = True; stats["Loss Category"] = "breakeven"
            elif is_profit:
                stats["Result"] = "WIN"; stats["Head Result"] = "WIN"
                stats["Loss Category"] = "trailing_win"
            else:
                stats["Result"] = "LOSS"; stats["Head Result"] = "LOSS"
                r = max_favorable
                if r < 5: stats["Loss Category"] = "immediate_rejection"
                elif r < 30: stats["Loss Category"] = "early_reversal"
                elif r < 70: stats["Loss Category"] = "mid_reversal"
                else: stats["Loss Category"] = "late_reversal"
            stats["exit_idx"] = idx; stats["exit_price"] = sl
            stats["candles_to_exit"] = candle_count; stats["Exit Date"] = str(idx)
            exited = True; continue

        elif hit_tp:
            stats["Result"] = "WIN"; stats["Head Result"] = "WIN"
            stats["Loss Category"] = "success"
            stats["exit_idx"] = idx; stats["exit_price"] = tp
            stats["candles_to_exit"] = candle_count; stats["Exit Date"] = str(idx)
            tp_hit_candle = candle_count; exited = True; continue

        if candle_count >= TIMEOUT_CANDLES:
            if breakeven_activated:
                stats["Result"] = "BREAKEVEN"; stats["Head Result"] = "BREAKEVEN"
                stats["Breakeven Exit"] = True; stats["Loss Category"] = "breakeven"
                stats["exit_price"] = entry
            else:
                stats["Result"] = "TIMEOUT"; stats["Head Result"] = "TIMEOUT"
                stats["Loss Category"] = "timeout"; stats["exit_price"] = close
            stats["exit_idx"] = idx; stats["candles_to_exit"] = candle_count
            stats["Exit Date"] = str(idx)
            moved = max(0.0, entry - close) if bias == "Bearish" else max(0.0, close - entry)
            if total_tp_dist > 0:
                stats["progress_ratio"] = round(moved / total_tp_dist * 100, 2)
            exited = True; break
    else:
        stats["candles_to_exit"] = max(0, len(post_df) - 1)
        stats["Exit Date"] = str(df.index[-1]); stats["Loss Category"] = "open"

    stats["Max Reach %"] = round(max_favorable, 1)
    stats["SL Safety %"] = round(100 - max_adverse, 1) if max_adverse <= 100 else 0.0
    stats["Max Extension %"] = round(full_window_max, 1)
    stats["Extension Beyond TP %"] = round(max(0.0, full_window_max - 100.0), 1)
    stats["TP Hit At Candle"] = tp_hit_candle
    stats["Extension Duration Candles"] = max(0, max_ext_candle - tp_hit_candle) if tp_hit_candle else 0

    if stats["Result"] == "WIN":
        stats["progress_ratio"] = 100.0
    elif stats["Result"] in ["LOSS", "BREAKEVEN"]:
        stats["progress_ratio"] = 0.0
    return stats


class PatternValidatorPipeline:
    def __init__(self, df):
        self.df = df

    def time_filter(self, p):
        positions = [x["pos"] for x in p]
        for j in range(len(positions) - 1):
            if positions[j + 1] - positions[j] < CONFIG["MIN_WAVE_CANDLES"]:
                return False
        return True

    def breakout_filter(self, p, is_bearish, neckline):
        idx_h3 = p[-1]["idx"]
        post = self.df.loc[idx_h3:]
        if is_bearish:
            br = post[post["Close"] < neckline]
        else:
            br = post[post["Close"] > neckline]
        if br.empty: return None
        return br.index[0], float(br["Close"].iloc[0])

    def breakout_confirm_filter(self, is_bearish, neckline, price):
        mp = CONFIG["BREAKOUT_MIN_PCT"]
        if is_bearish:
            return price <= neckline * (1 - mp)
        return price >= neckline * (1 + mp)


def detect_head_shoulders(pivots, df, is_backtest=False,
                           max_gap=50, max_pattern_duration=200):
    patterns = []
    if len(pivots) < 6: return patterns
    validator = PatternValidatorPipeline(df)
    total_candles = len(df)

    for i in range(len(pivots) - 5):
        p = pivots[i:i + 6]
        if [x["type"] for x in p] != ["L", "H", "L", "H", "L", "H"]:
            continue
        l0, h1, l1, h2, l2, h3 = [x["val"] for x in p]
        if h1 <= l0 or l1 <= l0: continue
        if h2 <= h1 or h2 <= h3: continue
        neckline_min = min(l1, l2)
        head_height = h2 - neckline_min
        if head_height <= 0: continue

        if i >= 2:
            prev_l = pivots[i - 2]["val"]
            prev_h = pivots[i - 1]["val"]
            prior_trend = prev_h - prev_l
        else:
            prior_trend = h1 - l0

        is_reversal = prior_trend >= head_height
        is_continuation = (-prior_trend) >= head_height

        if is_reversal and CONFIG["ENABLE_REVERSAL"]:
            pattern_type = "Reversal"
        elif is_continuation and CONFIG["ENABLE_CONTINUATION"]:
            pattern_type = "Continuation"
        else:
            continue

        if abs(h1 - h3) > (head_height * CONFIG["SHOULDER_DIFF_MAX_RATIO"]): continue
        max_sh = max(h1, h3)
        if (h2 - max_sh) < (head_height * CONFIG["HEAD_PROPORTION_MIN_RATIO"]): continue
        if abs(l1 - l2) > (head_height * CONFIG["NECKLINE_DIFF_MAX_RATIO"]): continue

        l0_pos, h3_pos = p[0]["pos"], p[5]["pos"]
        if (h3_pos - l0_pos) > max_pattern_duration: continue

        neckline = (l1 + l2) / 2.0
        br = validator.breakout_filter(p, is_bearish=True, neckline=neckline)
        if br is None: continue
        end_idx, end_val = br
        if not validator.breakout_confirm_filter(True, neckline, end_val): continue
        if end_idx not in df.index: continue
        end_pos = df.index.get_loc(end_idx)
        if (end_pos - h3_pos) > max_gap: continue
        if not is_backtest and (total_candles - end_pos) > CONFIG["LIVE_MAX_BREAKOUT_CANDLES"]:
            continue

        # =====================================================================
        # [تعديل جديد]: التأكد من أن الكتف الأيمن (h3) هو أعلى نقطة بعد الرأس (h2)
        # =====================================================================
        h2_idx = p[3]["idx"]  # موقع الرأس
        if h2_idx in df.index and end_idx in df.index:
            # نافذة البحث من الرأس إلى نقطة الاختراق
            post_head_window = df.loc[h2_idx:end_idx]
            if not post_head_window.empty:
                if post_head_window["High"].max() > h3 + 1e-9:
                    # توجد شمعة أعلى من الكتف الأيمن بعد الرأس -> النموذج غير صالح
                    continue
        # =====================================================================

        l1_idx, l2_idx = p[2]["idx"], p[4]["idx"]
        actual_head = h2 - neckline
        entry = neckline
        structural_sl = h2
        final_sl, tp, safe_sl, _ = compute_safe_sl_and_tp(
            "Bearish", entry, structural_sl, actual_head)

        nodes = [(x["idx"], x["val"]) for x in p] + [(end_idx, float(end_val))]
        pattern = {
            "name": "Head and Shoulders", "pattern": "Head and Shoulders",
            "pattern_type": pattern_type,
            "bias": "Bearish", "match": 100.0, "nodes": nodes,
            "entry": float(round(entry, 5)), "entry_trigger": float(round(entry, 5)),
            "sl": float(round(final_sl, 5)), "tp": float(round(tp, 5)),
            "structural_sl": float(round(structural_sl, 5)),
            "safe_sl": float(round(safe_sl, 5)),
            "neckline_start_idx": l1_idx, "neckline_end_idx": end_idx,
            "neckline_nodes": [(l1_idx, l1), (l2_idx, l2)],
            "target_nodes": [(end_idx, float(round(entry, 5))), (end_idx, float(round(tp, 5)))],
            "end_pos": p[5]["pos"],
            "SL": float(round(final_sl, 5)), "TP": float(round(tp, 5)),
            "Entry": float(round(entry, 5)),
            "Pattern": f"Head and Shoulders ({pattern_type})",
            "Entry Conditions": "Breakout Only",
        }
        pattern.update(simulate_trade_outcome(pattern, df))
        pattern["Trade Recommendation"] = generate_trade_recommendation(
            "Bearish", entry, final_sl, tp, structural_sl, actual_head,
            f"H&S {pattern_type}")
        patterns.append(pattern)
    return patterns


def detect_inverse_head_shoulders(pivots, df, is_backtest=False,
                                   max_gap=50, max_pattern_duration=200):
    patterns = []
    if len(pivots) < 6: return patterns
    validator = PatternValidatorPipeline(df)
    total_candles = len(df)

    for i in range(len(pivots) - 5):
        p = pivots[i:i + 6]
        if [x["type"] for x in p] != ["H", "L", "H", "L", "H", "L"]:
            continue
        h0, l1, h1, l2, h2, l3 = [x["val"] for x in p]
        if l2 >= l1 or l2 >= l3: continue
        neckline_max = max(h1, h2)
        head_depth = neckline_max - l2
        if head_depth <= 0: continue

        if i >= 2:
            prev_h = pivots[i - 2]["val"]
            prev_l = pivots[i - 1]["val"]
            prior_trend = prev_h - prev_l
        else:
            prior_trend = h0 - l1

        is_reversal = (-prior_trend) >= head_depth
        is_continuation = prior_trend >= head_depth

        if is_reversal and CONFIG["ENABLE_REVERSAL"]:
            pattern_type = "Reversal"
        elif is_continuation and CONFIG["ENABLE_CONTINUATION"]:
            pattern_type = "Continuation"
        else:
            continue

        if abs(l1 - l3) > (head_depth * CONFIG["SHOULDER_DIFF_MAX_RATIO"]): continue
        min_sh = min(l1, l3)
        if (min_sh - l2) < (head_depth * CONFIG["HEAD_PROPORTION_MIN_RATIO"]): continue
        if abs(h1 - h2) > (head_depth * CONFIG["NECKLINE_DIFF_MAX_RATIO"]): continue

        positions = [x["pos"] for x in p]
        if any((positions[j+1] - positions[j]) < CONFIG["MIN_WAVE_CANDLES"] for j in range(len(positions)-1)):
            continue
        h0_pos, l3_pos = p[0]["pos"], p[5]["pos"]
        if (l3_pos - h0_pos) > max_pattern_duration: continue

        idx_l2 = p[3]["idx"]
        post_l2 = df.loc[idx_l2:]
        if not post_l2.empty and post_l2["Low"].min() < l2: continue

        neckline = (h1 + h2) / 2.0
        br = validator.breakout_filter(p, is_bearish=False, neckline=neckline)
        if br is None: continue
        end_idx, end_val = br
        if not validator.breakout_confirm_filter(False, neckline, end_val): continue
        if end_idx not in df.index: continue
        end_pos = df.index.get_loc(end_idx)
        if (end_pos - l3_pos) > max_gap: continue
        if not is_backtest and (total_candles - end_pos) > CONFIG["LIVE_MAX_BREAKOUT_CANDLES"]:
            continue

        # =====================================================================
        # [تعديل جديد]: التأكد من أن الكتف الأيمن (l3) هو أدنى نقطة بعد الرأس (l2)
        # =====================================================================
        l2_idx = p[3]["idx"]  # موقع الرأس (القاع)
        if l2_idx in df.index and end_idx in df.index:
            # نافذة البحث من الرأس إلى نقطة الاختراق
            post_head_window = df.loc[l2_idx:end_idx]
            if not post_head_window.empty:
                if post_head_window["Low"].min() < l3 - 1e-9:
                    # توجد شمعة أدنى من الكتف الأيمن بعد الرأس -> النموذج غير صالح
                    continue
        # =====================================================================

        h1_idx, h2_idx = p[2]["idx"], p[4]["idx"]
        actual_head = neckline - l2
        entry = neckline
        structural_sl = l2
        final_sl, tp, safe_sl, _ = compute_safe_sl_and_tp(
            "Bullish", entry, structural_sl, actual_head)

        nodes = [(x["idx"], x["val"]) for x in p] + [(end_idx, end_val)]
        pattern = {
            "name": "Inverse Head and Shoulders", "pattern": "Inverse Head and Shoulders",
            "pattern_type": pattern_type,
            "bias": "Bullish", "match": 100.0, "nodes": nodes,
            "entry": float(round(entry, 5)), "entry_trigger": float(round(entry, 5)),
            "sl": float(round(final_sl, 5)), "tp": float(round(tp, 5)),
            "structural_sl": float(round(structural_sl, 5)),
            "safe_sl": float(round(safe_sl, 5)),
            "neckline_start_idx": h1_idx, "neckline_end_idx": end_idx,
            "neckline_nodes": [(h1_idx, h1), (h2_idx, h2)],
            "target_nodes": [(end_idx, float(round(entry, 5))), (end_idx, float(round(tp, 5)))],
            "end_pos": p[5]["pos"],
            "SL": float(round(final_sl, 5)), "TP": float(round(tp, 5)),
            "Entry": float(round(entry, 5)),
            "Pattern": f"Inverse Head and Shoulders ({pattern_type})",
            "Entry Conditions": "Breakout Only",
        }
        pattern.update(simulate_trade_outcome(pattern, df))
        pattern["Trade Recommendation"] = generate_trade_recommendation(
            "Bullish", entry, final_sl, tp, structural_sl, actual_head,
            f"نموذج معكوس {pattern_type}")
        patterns.append(pattern)
    return patterns


def detect_all_head_shoulders(pivots, df, is_backtest=False,
                               max_gap=50, max_pattern_duration=200):
    a = detect_head_shoulders(pivots, df, is_backtest, max_gap, max_pattern_duration)
    b = detect_inverse_head_shoulders(pivots, df, is_backtest, max_gap, max_pattern_duration)
    all_p = a + b
    all_p.sort(key=lambda x: x.get("end_pos", -1))
    return all_p


# ==============================================================================
# 🔄 run_full_analysis
# ==============================================================================
def run_full_analysis(df, interval="1h", symbol=None):
    default_empty = {
        "df": df, "symbol": symbol or "N/A",
        "signal": "WAITING", "pattern": "NO PATTERN DETECTED",
        "bias": "Neutral", "entry": None, "sl": None, "tp": None,
        "nodes": [], "pattern_nodes": [], "all_patterns": [], "error": None,
    }
    if df is None or df.empty:
        return default_empty
    df = df.copy()
    required = ["Open", "High", "Low", "Close"]
    for col in required:
        if col not in df.columns:
            default_empty["error"] = f"Missing column: {col}"
            return default_empty
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=required)
    if len(df) < 30:
        default_empty["error"] = f"Insufficient data: {len(df)}"
        return default_empty

    df_active = df.tail(200).copy()
    df_active = calculate_indicators(df_active)
    df_active = calculate_zigzag(df_active, CONFIG["ZIGZAG_DEPTH"], CONFIG["ZIGZAG_BACKSTEP"])
    pivots = get_chronological_pivots(df_active)
    max_gap = _get_max_gap(interval)
    max_pattern_dur = _get_max_pattern_duration(interval)
    all_patterns = detect_all_head_shoulders(
        pivots, df_active, is_backtest=False,
        max_gap=max_gap, max_pattern_duration=max_pattern_dur)
    if not all_patterns:
        default_empty["df"] = df_active
        return default_empty

    latest = all_patterns[-1]
    signal = "STRONG BUY" if latest["bias"] == "Bullish" else "STRONG SELL"

    return {
        "df": df_active, "symbol": symbol or "N/A",
        "signal": signal, "pattern": latest["pattern"], "bias": latest["bias"],
        "entry": latest["entry"], "entry_trigger": latest["entry_trigger"],
        "sl": latest["sl"], "tp": latest["tp"],
        "nodes": latest["nodes"], "pattern_nodes": latest["nodes"],
        "neckline_nodes": latest.get("neckline_nodes", []),
        "target_nodes": latest.get("target_nodes", []),
        "all_patterns": all_patterns, "match": latest.get("match", 100.0),
        "Result": latest.get("Result", "OPEN"),
        "Entry Date": latest.get("Entry Date"),
        "Exit Date": latest.get("Exit Date"),
        "Trade Recommendation": latest.get("Trade Recommendation", ""),
        "Max Reach %": latest.get("Max Reach %", 0),
        "error": None,
    }


# ==============================================================================
# 📤 backtest_strategy
# ==============================================================================
def backtest_strategy(df, interval="1h", symbol=None):
    if df is None or df.empty or len(df) < 30:
        return []
    df = df.copy()
    for col in ["Open", "High", "Low", "Close"]:
        if col not in df.columns: return []
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["Open", "High", "Low", "Close"])
    if len(df) < 30: return []

    df = calculate_indicators(df)
    df = calculate_zigzag(df, CONFIG["ZIGZAG_DEPTH"], CONFIG["ZIGZAG_BACKSTEP"])
    pivots = get_chronological_pivots(df)
    patterns = detect_all_head_shoulders(
        pivots, df, is_backtest=True,
        max_gap=_get_max_gap(interval),
        max_pattern_duration=_get_max_pattern_duration(interval))

    trades = []
    for p in patterns:
        trades.append({
            "Symbol": symbol or "N/A", "symbol": symbol or "N/A",
            "Pattern": p["pattern"], "pattern": p["pattern"],
            "Pattern Type": p.get("pattern_type", "Reversal"),
            "Bias": p["bias"], "bias": p["bias"],
            "Result": p.get("Result", "OPEN"),
            "Head Result": p.get("Head Result", "OPEN"),
            "Entry": p["entry"], "Entry Price": p["entry"],
            "SL": p["sl"], "Stop Loss": p["sl"],
            "TP": p["tp"], "Take Profit": p["tp"],
            "Structural SL": p.get("structural_sl"),
            "Safe SL": p.get("safe_sl"),
            "TP Factor Used": CONFIG["TP_REACH_FACTOR"],
            "Entry Date": p.get("Entry Date"), "Exit Date": p.get("Exit Date"),
            "Exit Price": p.get("exit_price"),
            "time": p.get("Entry Date"), "close_time": p.get("Exit Date"),
            "Max Reach %": p.get("Max Reach %", 0.0),
            "Max Extension %": p.get("Max Extension %", 0.0),
            "Extension Beyond TP %": p.get("Extension Beyond TP %", 0.0),
            "TP Hit At Candle": p.get("TP Hit At Candle"),
            "Extension Duration Candles": p.get("Extension Duration Candles", 0),
            "SL Safety %": p.get("SL Safety %", 0.0),
            "Entry Conditions": p.get("Entry Conditions", ""),
            "nodes": p["nodes"],
            "candles_to_exit": p.get("candles_to_exit", 0),
            "progress_ratio": p.get("progress_ratio", 0.0),
            "neckline_end_idx": p["neckline_end_idx"],
            "Pattern Duration": p.get("Pattern Duration", 0),
            "Timeout Used": p.get("Timeout Used", 0),
            "Breakeven Activated": p.get("Breakeven Activated", False),
            "Breakeven Exit": p.get("Breakeven Exit", False),
            "Loss Category": p.get("Loss Category"),
            "Trailing Stage": p.get("Trailing Stage", 0),
            "Initial SL": p.get("Initial SL"),
            "Final SL": p.get("Final SL"),
            "Trade Recommendation": p.get("Trade Recommendation", ""),
        })
    return trades


# ==============================================================================
# 🧪 diagnose_filters
# ==============================================================================
def diagnose_filters(df, interval="1h", symbol=None):
    result = {
        "error": None, "total_raw_candidates": 0, "final_count": 0,
        "stages": {}, "smart_diagnosis": {}, "recommendations": [],
        "trade_analysis": [], "by_pattern_type": {},
        "tp_distribution": {}, "extension_analysis": {},
    }

    if df is None or df.empty or len(df) < 30:
        result["error"] = "بيانات غير كافية"; return result

    df = df.copy()
    for col in ["Open", "High", "Low", "Close"]:
        if col not in df.columns:
            result["error"] = f"مفقود: {col}"; return result
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["Open", "High", "Low", "Close"])

    df = calculate_indicators(df)
    df = calculate_zigzag(df, CONFIG["ZIGZAG_DEPTH"], CONFIG["ZIGZAG_BACKSTEP"])
    pivots = get_chronological_pivots(df)

    raw_count = 0
    if len(pivots) >= 6:
        for i in range(len(pivots) - 5):
            p = pivots[i:i + 6]
            if [x["type"] for x in p] in (["L","H","L","H","L","H"], ["H","L","H","L","H","L"]):
                raw_count += 1
    result["total_raw_candidates"] = raw_count

    trades = backtest_strategy(df, interval=interval, symbol=symbol)
    result["final_count"] = len(trades)

    wins = [t for t in trades if "WIN" in str(t.get("Result","")).upper()]
    losses = [t for t in trades if "LOSS" in str(t.get("Result","")).upper()]
    bes = [t for t in trades if "BREAKEVEN" in str(t.get("Result","")).upper()]
    tos = [t for t in trades if "TIMEOUT" in str(t.get("Result","")).upper()]

    for ptype in ["Reversal", "Continuation"]:
        subset = [t for t in trades if t.get("Pattern Type") == ptype]
        if not subset: continue
        w = [t for t in subset if "WIN" in str(t.get("Result","")).upper()]
        l = [t for t in subset if "LOSS" in str(t.get("Result","")).upper()]
        total_closed = len(w) + len(l)
        wr = round(len(w) / total_closed * 100, 1) if total_closed else 0
        result["by_pattern_type"][ptype] = {
            "count": len(subset),
            "wins": len(w), "losses": len(l),
            "breakevens": len([t for t in subset if "BREAKEVEN" in str(t.get("Result","")).upper()]),
            "timeouts": len([t for t in subset if "TIMEOUT" in str(t.get("Result","")).upper()]),
            "win_rate_%": wr,
        }

    win_ext = [t.get("Max Extension %", 0) for t in wins if t.get("Max Extension %") is not None]

    def _pct(lst, cond):
        return round(sum(1 for x in lst if cond(x)) / max(len(lst), 1) * 100, 1)

    result["extension_analysis"] = {
        "sample_wins": len(win_ext),
        "median_extension_wins_%": round(float(np.median(win_ext)), 1) if win_ext else 0,
        "pct_wins_reach_1.0x": _pct(win_ext, lambda x: x >= 100),
    }

    win_reach = [t.get("Max Reach %", 0) for t in wins]
    result["tp_distribution"] = {
        "wins_count": len(wins),
        "pct_wins_>=60%": _pct(win_reach, lambda x: x >= 60),
        "pct_wins_>=100%": _pct(win_reach, lambda x: x >= 100),
    }

    loss_breakdown = {"immediate_rejection": 0, "early_reversal": 0,
                      "mid_reversal": 0, "late_reversal": 0,
                      "unavoidable": 0, "avoidable": 0}
    for t in losses:
        cat = t.get("Loss Category") or ""
        if cat in loss_breakdown:
            loss_breakdown[cat] += 1
        if t.get("Max Reach %", 0) >= 60:
            loss_breakdown["unavoidable"] += 1
        else:
            loss_breakdown["avoidable"] += 1

    win_breakdown = {"total_wins": len(wins), "avg_max_reach": 0.0}
    if wins:
        win_breakdown["avg_max_reach"] = round(
            sum(t.get("Max Reach %", 0) for t in wins) / len(wins), 1)

    total_closed = len(wins) + len(losses)
    win_rate = round(len(wins) / total_closed * 100, 1) if total_closed else 0

    if total_closed == 0:
        verdict = "لا توجد صفقات كافية"
    elif win_rate >= 70:
        verdict = f"ممتاز — {win_rate}%"
    elif win_rate >= 50:
        verdict = f"جيد — {win_rate}%"
    elif win_rate >= 35:
        verdict = f"متوسط — {win_rate}%"
    else:
        verdict = f"ضعيف — {win_rate}%"

    action_plan = []
    avoidable = loss_breakdown["avoidable"]
    unavoidable = loss_breakdown["unavoidable"]
    if avoidable > unavoidable:
        action_plan.append(f"🔴 خسائر قابلة للتجنب ({avoidable}) > غير قابلة ({unavoidable}).")
    elif unavoidable > 0:
        action_plan.append(f"🟢 معظم الخسائر ({unavoidable}) لا مفر منها.")

    rev = result["by_pattern_type"].get("Reversal", {})
    con = result["by_pattern_type"].get("Continuation", {})
    if rev and con:
        rev_wr = rev.get("win_rate_%", 0)
        con_wr = con.get("win_rate_%", 0)
        if con_wr < 50 and rev_wr >= 60:
            action_plan.append(f"🔴 Continuation ضعيف ({con_wr}%) — أوصي بتعطيله.")
        elif con_wr >= 60:
            action_plan.append(f"🟢 Continuation مقبول ({con_wr}%) — يمكن دمجه.")

    result["smart_diagnosis"] = {
        "verdict": verdict,
        "win_breakdown": win_breakdown,
        "loss_breakdown": loss_breakdown,
        "action_plan": action_plan,
    }

    trade_analysis = []
    for i, t in enumerate(trades):
        cat = t.get("Loss Category") or "open"
        info = REASON_MAP.get(cat, REASON_MAP.get("open"))
        entry = t.get("Entry", 0) or 0
        sl = t.get("SL", 0) or 0
        tp = t.get("TP", 0) or 0
        risk = abs(entry - sl)
        reward = abs(tp - entry)
        rr = round(reward / risk, 2) if risk > 0 else "—"
        trade_analysis.append({
            "trade_num": i + 1,
            "bias": t.get("Bias", "—"),
            "pattern": t.get("Pattern", "—"),
            "pattern_type": t.get("Pattern Type", "—"),
            "result": t.get("Result", "—"),
            "category": cat,
            "max_reach_%": t.get("Max Reach %", 0),
            "rr_ratio": rr,
            "is_unavoidable": t.get("Max Reach %", 0) >= 60 and "LOSS" in str(t.get("Result", "")).upper(),
            "reason": info.get("reason", "—"),
            "action": info.get("action", "—"),
            "prevention": info.get("prevention", "—"),
        })
    result["trade_analysis"] = trade_analysis

    recommendations = []
    if len(tos) > len(wins):
        recommendations.append({"severity": "حرج", "message": "الصفقات المنتهية بالوقت كثيرة."})
    if len(bes) > 0:
        recommendations.append({"severity": "منخفض", "message": f"{len(bes)} صفقة عند التعادل."})
    result["recommendations"] = recommendations
    return result


if __name__ == "__main__":
    print("ENGINE.PY — H&S Reversal + Continuation")
    print(f"Reversal: {CONFIG['ENABLE_REVERSAL']}")
    print(f"Continuation: {CONFIG['ENABLE_CONTINUATION']}")
    print(f"TP: {CONFIG['TP_REACH_FACTOR']}× head | Safe SL: {CONFIG['USE_SAFE_SL']}")
