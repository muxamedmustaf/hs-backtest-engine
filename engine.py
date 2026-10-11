# -*- coding: utf-8 -*-
"""
ENGINE.PY - Head & Shoulders Detector + Diagnostics (v3)
=========================================================
- فلتر الاتجاه السابق الصارم
- وقف آمن صارم (هامش 15%) مُفعَّل في المحاكاة
- TP = 2× الرأس (مُعاير على البيانات التاريخية)
- Trailing بوحدات الرأس (لا الهدف) لتفادي Timeouts
- قياس الامتداد الكامل بعد الهدف
- تشخيص ذكي مع قرار آلي
"""
import pandas as pd
import numpy as np

# ==============================================================================
CONFIG = {
    "ZIGZAG_DEPTH": 8,
    "ZIGZAG_BACKSTEP": 4,
    "MIN_WAVE_CANDLES": 3,
    "SHOULDER_DIFF_MAX_RATIO": 0.35,
    "HEAD_PROPORTION_MIN_RATIO": 0.15,
    "NECKLINE_DIFF_MAX_RATIO": 0.10,
    "LIVE_MAX_BREAKOUT_CANDLES": 10,
    "BREAKOUT_MIN_PCT": 0.0001,
    "REQUIRE_VOLUME_BREAKOUT": False,
    "VOLUME_FACTOR": 1.2,
    "VOLUME_MA_PERIOD": 20,

    # 🎯 الهدف: 2× الرأس
    "TP_REACH_FACTOR": 2.0,

    # 🛡️ الوقف الآمن
    "USE_SAFE_SL": True,
    "SAFE_SL_MARGIN": 0.15,

    # 📈 Trailing بوحدات الرأس (مستقل عن حجم الهدف)
    "TRAILING_LEVELS_HEAD": [
    (1.00, 0.00),   # BE بعد وصول 1:1
    (1.40, 0.60),   # +0.6× رأس
    (1.70, 1.00),   # +1.0× رأس
    (1.90, 1.50),   # +1.5× رأس
],

    "MEASURE_FULL_EXTENSION": True,
}

TIMEOUT_STATISTICAL_FLOOR = 200
TIMEOUT_DURATION_MULTIPLIER = 3

REASON_MAP = {
    "immediate_rejection": {
        "reason": "رفض فوري لخط العنق — اختراق وهمي.",
        "action": "انتظر إعادة اختبار + شمعة تأكيد.",
        "prevention": "لا تدخل بأول لمسة."
    },
    "early_reversal": {
        "reason": "انعكاس مبكر قبل 30% من الهدف.",
        "action": "نقل SL للتعادل عند 20% من الهدف.",
        "prevention": "استخدم Trailing مبكرًا."
    },
    "mid_reversal": {
        "reason": "انعكاس في منتصف الطريق.",
        "action": "خروج جزئي 50% عند 50% من الهدف.",
        "prevention": "حدد TP جزئي عند أقرب مستوى عرضي."
    },
    "late_reversal": {
        "reason": "وصل 70%+ ثم عاد — جني أرباح.",
        "action": "Trailing بـ 30% من الهدف.",
        "prevention": "راقب التقويم الاقتصادي."
    },
    "timeout": {
        "reason": "انتهت المدة دون لمس TP/SL.",
        "action": "أغلق يدويًا إذا تجاوز 2× المتوسط.",
        "prevention": "أضف فلتر ADX."
    },
    "breakeven": {
        "reason": "أُغلقت عند التعادل — حماية رأس المال.",
        "action": "لا شيء.",
        "prevention": "استمر."
    },
    "success": {
        "reason": "وصل الهدف بالكامل.",
        "action": "سجّل الإعداد وكرره.",
        "prevention": "—"
    },
    "trailing_win": {
        "reason": "أُغلقت بـ Trailing بعد ربح.",
        "action": "لا شيء.",
        "prevention": "—"
    },
    "open": {
        "reason": "ما زالت مفتوحة عند نهاية الاختبار.",
        "action": "راقب يدويًا.",
        "prevention": "—"
    },
}


def _get_max_gap(interval):
    return {"1m": 120, "5m": 50, "15m": 30, "30m": 25, "1h": 20,
            "4h": 15, "1d": 10, "1wk": 5}.get(interval, 50)


def _get_max_pattern_duration(interval):
    return {"1m": 600, "5m": 200, "15m": 150, "30m": 120, "1h": 100,
            "4h": 80, "1d": 60, "1wk": 30}.get(interval, 200)


def compute_safe_sl_and_tp(bias, entry, structural_sl, head_size):
    """الوقف الآمن الصارم + الهدف حسب TP_REACH_FACTOR."""
    structural_risk = abs(entry - structural_sl)
    if bias == "Bullish":
        safe_sl = structural_sl - (structural_risk * CONFIG["SAFE_SL_MARGIN"])
    else:
        safe_sl = structural_sl + (structural_risk * CONFIG["SAFE_SL_MARGIN"])

    final_sl = safe_sl if CONFIG["USE_SAFE_SL"] else structural_sl

    target_distance = head_size * CONFIG["TP_REACH_FACTOR"]
    tp = entry + target_distance if bias == "Bullish" else entry - target_distance

    return final_sl, tp, safe_sl, structural_sl


def generate_trade_recommendation(bias, entry, sl, tp, structural_sl, head_size):
    risk = abs(entry - sl)
    reward = abs(tp - entry)
    rr = round(reward / risk, 2) if risk > 0 else 0.0
    factor = CONFIG["TP_REACH_FACTOR"]
    margin = round(CONFIG["SAFE_SL_MARGIN"] * 100, 0)

    if bias == "Bullish":
        return (
            f"🟢 توصية إيجابية (Bullish Inverse H&S):\n"
            f"- الدخول: اختراق خط العنق ({entry}).\n"
            f"- الوقف الآمن: ({round(sl, 5)}) = قاع الرأس ({round(structural_sl, 5)}) + هامش {margin}%.\n"
            f"- الهدف: ({round(tp, 5)}) = {factor}× من الرأس.\n"
            f"- R:R = 1 : {rr}."
        )
    else:
        return (
            f"🔴 توصية سلبية (Bearish H&S):\n"
            f"- الدخول: كسر خط العنق ({entry}).\n"
            f"- الوقف الآمن: ({round(sl, 5)}) = قمة الرأس ({round(structural_sl, 5)}) + هامش {margin}%.\n"
            f"- الهدف: ({round(tp, 5)}) = {factor}× من الرأس.\n"
            f"- R:R = 1 : {rr}."
        )


def calculate_indicators(df):
    df = df.copy()
    high_low = df["High"] - df["Low"]
    high_close = np.abs(df["High"] - df["Close"].shift())
    low_close = np.abs(df["Low"] - df["Close"].shift())
    true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df["ATR"] = true_range.rolling(14).mean()
    df["Dynamic_Swing"] = (df["ATR"] / df["Close"]) * 0.5
    df["Dynamic_Swing"] = df["Dynamic_Swing"].fillna(0.001)

    if "Volume" in df.columns:
        v = pd.to_numeric(df["Volume"], errors="coerce").fillna(0.0)
        df["Volume"] = v
        df["Volume_MA"] = v.rolling(CONFIG["VOLUME_MA_PERIOD"]).mean().fillna(0.0)
        df["Has_Valid_Volume"] = v.std() > 0
    else:
        df["Volume"] = 0.0
        df["Volume_MA"] = 0.0
        df["Has_Valid_Volume"] = False
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
                if last["type"] == "H" and p["val"] > last["val"]:
                    clean[-1] = p
                elif last["type"] == "L" and p["val"] < last["val"]:
                    clean[-1] = p
        else:
            if p["type"] == "H" and p["val"] > last["val"]:
                clean[-1] = p
            elif p["type"] == "L" and p["val"] < last["val"]:
                clean[-1] = p

    final = []
    for p in clean:
        if not final:
            final.append(p)
        else:
            if final[-1]["type"] != p["type"]:
                final.append(p)
            else:
                if p["type"] == "H" and p["val"] > final[-1]["val"]:
                    final[-1] = p
                elif p["type"] == "L" and p["val"] < final[-1]["val"]:
                    final[-1] = p
    return final


# ==============================================================================
# 🎬 محاكاة الصفقة — Trailing بوحدات الرأس
# ==============================================================================
def simulate_trade_outcome(pattern, df):
    bias = pattern["bias"]
    entry = float(pattern["entry"])
    initial_sl = float(pattern["sl"])
    sl = initial_sl
    tp = float(pattern["tp"])
    end_idx = pattern["neckline_end_idx"]

    # حجم الرأس الفعلي (المسافة من الدخول إلى TP مقسومة على factor)
    head_size = abs(tp - entry) / CONFIG["TP_REACH_FACTOR"]
    head_pct = (head_size / entry * 100) if entry > 0 else 0

    MIN_HEAD_PCT = 0.10
    MAX_HEAD_PCT = 10.00

    if head_pct < MIN_HEAD_PCT:
        return {
            "Result": "SKIPPED", "Head Result": "SKIPPED",
            "Loss Category": "too_small",
            "Skip Reason": f"Head too small ({head_pct:.3f}% < {MIN_HEAD_PCT}%)",
            "Max Reach %": 0, "Max Extension %": 0, "Extension Beyond TP %": 0,
            "SL Safety %": 0, "Entry Date": str(end_idx), "Exit Date": None,
            "candles_to_exit": 0, "progress_ratio": 0,
        }
    if head_pct > MAX_HEAD_PCT:
        return {
            "Result": "SKIPPED", "Head Result": "SKIPPED",
            "Loss Category": "too_large",
            "Skip Reason": f"Head too large ({head_pct:.3f}% > {MAX_HEAD_PCT}%)",
            "Max Reach %": 0, "Max Extension %": 0, "Extension Beyond TP %": 0,
            "SL Safety %": 0, "Entry Date": str(end_idx), "Exit Date": None,
            "candles_to_exit": 0, "progress_ratio": 0,
        }

    nodes = pattern.get("nodes", [])
    if len(nodes) >= 6:
        try:
            first_pos = df.index.get_loc(nodes[0][0])
            h3_pos = df.index.get_loc(nodes[-2][0])
            pattern_duration = max(1, h3_pos - first_pos)
        except KeyError:
            pattern_duration = 50
    else:
        pattern_duration = 50

    TIMEOUT_CANDLES = max(TIMEOUT_STATISTICAL_FLOOR,
                          pattern_duration * TIMEOUT_DURATION_MULTIPLIER)

    # 🎯 Trailing بوحدات الرأس
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

    if end_idx not in df.index:
        return stats
    post_df = df.loc[end_idx:]
    if len(post_df) <= 1:
        return stats

    stats["Entry Date"] = str(end_idx)

    total_tp_dist = abs(tp - entry)
    total_sl_dist = abs(initial_sl - entry)
    max_favorable = 0.0
    max_adverse = 0.0
    full_window_max = 0.0
    tp_hit_candle = None
    max_ext_candle = 0
    exited = False

    for candle_count, (idx, row) in enumerate(post_df.iloc[1:].iterrows(), start=1):
        high = float(row["High"])
        low = float(row["Low"])
        close = float(row["Close"])

        if bias == "Bearish":
            favorable = max(0.0, entry - low)
            adverse = max(0.0, high - entry)
        else:
            favorable = max(0.0, high - entry)
            adverse = max(0.0, entry - low)

        # نسبة الوصول إلى الهدف الحالي (للإحصاء)
        progress = (favorable / total_tp_dist) if total_tp_dist > 0 else 0.0
        # 🆕 نسبة الوصول بوحدات الرأس
        progress_head = (favorable / head_size) if head_size > 0 else 0.0

        if CONFIG.get("MEASURE_FULL_EXTENSION", True) and total_tp_dist > 0:
            if progress * 100 > full_window_max:
                full_window_max = progress * 100
                max_ext_candle = candle_count

        if not exited:
            if total_tp_dist > 0:
                max_favorable = max(max_favorable, progress * 100)
            if total_sl_dist > 0:
                max_adverse = max(max_adverse, adverse / total_sl_dist * 100)

        if exited:
            if candle_count >= TIMEOUT_CANDLES:
                break
            continue

        # 🎯 Trailing بوحدات الرأس
        for stage_idx, (threshold_head, profit_head) in enumerate(TRAILING):
            if stage_idx < trailing_stage:
                continue
            if progress_head < threshold_head:
                break

            if profit_head == 0.0:
                new_sl = entry
            else:
                if bias == "Bearish":
                    new_sl = entry - profit_head * head_size
                else:
                    new_sl = entry + profit_head * head_size

            if bias == "Bearish":
                if new_sl < sl:
                    sl = new_sl
                    trailing_stage = stage_idx + 1
                    if profit_head == 0.0:
                        breakeven_activated = True
                        stats["Breakeven Activated"] = True
            else:
                if new_sl > sl:
                    sl = new_sl
                    trailing_stage = stage_idx + 1
                    if profit_head == 0.0:
                        breakeven_activated = True
                        stats["Breakeven Activated"] = True

        stats["Trailing Stage"] = trailing_stage
        stats["Final SL"] = sl

        if bias == "Bearish":
            hit_sl = high >= sl
            hit_tp = low <= tp
        else:
            hit_sl = low <= sl
            hit_tp = high >= tp

        if hit_sl and not hit_tp:
            if bias == "Bearish":
                is_profit = sl < entry - 1e-9
                is_be = abs(sl - entry) < 1e-9
            else:
                is_profit = sl > entry + 1e-9
                is_be = abs(sl - entry) < 1e-9

            if is_be:
                stats["Result"] = "BREAKEVEN"
                stats["Head Result"] = "BREAKEVEN"
                stats["Breakeven Exit"] = True
                stats["Loss Category"] = "breakeven"
            elif is_profit:
                stats["Result"] = "WIN"
                stats["Head Result"] = "WIN"
                stats["Loss Category"] = "trailing_win"
            else:
                stats["Result"] = "LOSS"
                stats["Head Result"] = "LOSS"
                reach = max_favorable
                if reach < 5:
                    stats["Loss Category"] = "immediate_rejection"
                elif reach < 30:
                    stats["Loss Category"] = "early_reversal"
                elif reach < 70:
                    stats["Loss Category"] = "mid_reversal"
                else:
                    stats["Loss Category"] = "late_reversal"

            stats["exit_idx"] = idx
            stats["exit_price"] = sl
            stats["candles_to_exit"] = candle_count
            stats["Exit Date"] = str(idx)
            exited = True
            continue

        elif hit_tp:
            stats["Result"] = "WIN"
            stats["Head Result"] = "WIN"
            stats["Loss Category"] = "success"
            stats["exit_idx"] = idx
            stats["exit_price"] = tp
            stats["candles_to_exit"] = candle_count
            stats["Exit Date"] = str(idx)
            tp_hit_candle = candle_count
            exited = True
            continue

        if candle_count >= TIMEOUT_CANDLES:
            if breakeven_activated:
                stats["Result"] = "BREAKEVEN"
                stats["Head Result"] = "BREAKEVEN"
                stats["Breakeven Exit"] = True
                stats["Loss Category"] = "breakeven"
                stats["exit_price"] = entry
            else:
                stats["Result"] = "TIMEOUT"
                stats["Head Result"] = "TIMEOUT"
                stats["Loss Category"] = "timeout"
                stats["exit_price"] = close

            stats["exit_idx"] = idx
            stats["candles_to_exit"] = candle_count
            stats["Exit Date"] = str(idx)

            if bias == "Bearish":
                moved = max(0.0, entry - close)
            else:
                moved = max(0.0, close - entry)
            if total_tp_dist > 0:
                stats["progress_ratio"] = round(moved / total_tp_dist * 100, 2)
            exited = True
            break
    else:
        stats["candles_to_exit"] = max(0, len(post_df) - 1)
        stats["Exit Date"] = str(df.index[-1])
        stats["Loss Category"] = "open"

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

    def breakout_filter(self, p):
        idx_h3 = p[5]["idx"]
        l1, l2 = p[2]["val"], p[4]["val"]
        neckline = (l1 + l2) / 2.0
        is_bearish = (p[3]["type"] == "H")
        post_h3 = self.df.loc[idx_h3:]
        if is_bearish:
            breakout = post_h3[post_h3["Close"] < neckline]
        else:
            breakout = post_h3[post_h3["Close"] > neckline]
        if breakout.empty:
            return None
        return breakout.index[0], float(breakout["Close"].iloc[0])

    def breakout_confirm_filter(self, p, breakout_price):
        l1, l2 = p[2]["val"], p[4]["val"]
        neckline = (l1 + l2) / 2.0
        is_bearish = (p[3]["type"] == "H")
        min_pct = CONFIG["BREAKOUT_MIN_PCT"]
        if is_bearish:
            return breakout_price <= neckline * (1 - min_pct)
        return breakout_price >= neckline * (1 + min_pct)

    def volume_filter(self, breakout_idx):
        if not CONFIG["REQUIRE_VOLUME_BREAKOUT"]:
            return True
        if breakout_idx not in self.df.index:
            return False
        row = self.df.loc[breakout_idx]
        vol = float(row.get("Volume", 0))
        vol_ma = float(row.get("Volume_MA", 0))
        if vol == 0 or vol_ma == 0:
            return True
        return vol >= vol_ma * CONFIG["VOLUME_FACTOR"]

    def run(self, p):
        if not self.time_filter(p):
            return False, None, None
        result = self.breakout_filter(p)
        if result is None:
            return False, None, None
        breakout_idx, breakout_price = result
        if not self.breakout_confirm_filter(p, breakout_price):
            return False, None, None
        if not self.volume_filter(breakout_idx):
            return False, None, None
        return True, breakout_idx, breakout_price


def detect_all_head_shoulders_base(pivots, df, is_backtest=False,
                                    max_gap=50, max_pattern_duration=200):
    patterns = []
    if len(pivots) < 6:
        return patterns
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

        # 🛡️ فلتر الاتجاه السابق الصارم
        if i >= 2:
            prior_h = pivots[i - 1]["val"] - pivots[i - 2]["val"]
            if prior_h < head_height:
                continue
        else:
            if (h2 - l0) < head_height:
                continue

        if abs(h1 - h3) > (head_height * CONFIG["SHOULDER_DIFF_MAX_RATIO"]): continue
        max_sh = max(h1, h3)
        if (h2 - max_sh) < (head_height * CONFIG["HEAD_PROPORTION_MIN_RATIO"]): continue
        if abs(l1 - l2) > (head_height * CONFIG["NECKLINE_DIFF_MAX_RATIO"]): continue

        l0_pos, h3_pos = p[0]["pos"], p[5]["pos"]
        if (h3_pos - l0_pos) > max_pattern_duration: continue

        passed, end_idx, end_val = validator.run(p)
        if not passed: continue
        if end_idx not in df.index: continue
        end_pos = df.index.get_loc(end_idx)
        if (end_pos - h3_pos) > max_gap: continue
        if not is_backtest and (total_candles - end_pos) > CONFIG["LIVE_MAX_BREAKOUT_CANDLES"]:
            continue

        l1_idx, l2_idx = p[2]["idx"], p[4]["idx"]
        neckline_avg = (l1 + l2) / 2.0
        actual_head_length = h2 - neckline_avg
        entry = neckline_avg
        structural_sl = h2

        final_sl, tp, safe_sl, _ = compute_safe_sl_and_tp(
            "Bearish", entry, structural_sl, actual_head_length)

        nodes = [(x["idx"], x["val"]) for x in p]
        nodes.append((end_idx, float(end_val)))

        pattern = {
            "name": "Head and Shoulders", "pattern": "Head and Shoulders",
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
            "Pattern": "Head and Shoulders",
            "Entry Conditions": "Breakout Only",
        }
        sim = simulate_trade_outcome(pattern, df)
        pattern.update(sim)
        pattern["Trade Recommendation"] = generate_trade_recommendation(
            pattern["bias"], pattern["entry"], pattern["sl"], pattern["tp"],
            structural_sl, actual_head_length)
        patterns.append(pattern)
    return patterns


def detect_all_inverse_head_shoulders(pivots, df, is_backtest=False,
                                       max_gap=50, max_pattern_duration=200):
    patterns = []
    if len(pivots) < 6:
        return patterns
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

        # 🛡️ فلتر الاتجاه السابق الصارم
        if i >= 2:
            prior_d = pivots[i - 2]["val"] - pivots[i - 1]["val"]
            if prior_d < head_depth:
                continue
        else:
            if (h0 - l2) < head_depth:
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
        post_head_df = df.loc[idx_l2:]
        if not post_head_df.empty and post_head_df["Low"].min() < l2:
            continue

        passed, end_idx, end_val = validator.run(p)
        if not passed: continue
        if end_idx not in df.index: continue
        end_pos = df.index.get_loc(end_idx)
        if (end_pos - l3_pos) > max_gap: continue
        if not is_backtest and (total_candles - end_pos) > CONFIG["LIVE_MAX_BREAKOUT_CANDLES"]:
            continue

        h1_idx, h2_idx = p[2]["idx"], p[4]["idx"]
        neckline_avg = (h1 + h2) / 2.0
        actual_head_length = neckline_avg - l2
        entry = neckline_avg
        structural_sl = l2

        final_sl, tp, safe_sl, _ = compute_safe_sl_and_tp(
            "Bullish", entry, structural_sl, actual_head_length)

        nodes = [(x["idx"], x["val"]) for x in p]
        nodes.append((end_idx, end_val))

        pattern = {
            "name": "Inverse Head and Shoulders", "pattern": "Inverse Head and Shoulders",
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
            "Pattern": "Inverse Head and Shoulders",
            "Entry Conditions": "Breakout Only",
        }
        sim = simulate_trade_outcome(pattern, df)
        pattern.update(sim)
        pattern["Trade Recommendation"] = generate_trade_recommendation(
            pattern["bias"], pattern["entry"], pattern["sl"], pattern["tp"],
            structural_sl, actual_head_length)
        patterns.append(pattern)
    return patterns


def detect_all_head_shoulders(pivots, df, is_backtest=False,
                               max_gap=50, max_pattern_duration=200):
    a = detect_all_head_shoulders_base(pivots, df, is_backtest, max_gap, max_pattern_duration)
    b = detect_all_inverse_head_shoulders(pivots, df, is_backtest, max_gap, max_pattern_duration)
    all_p = a + b
    all_p.sort(key=lambda x: x.get("end_pos", -1))
    return all_p


def run_full_analysis(df, interval="1h", symbol=None):
    default = {"df": df, "symbol": symbol or "N/A", "signal": "WAITING",
               "pattern": "NO PATTERN", "bias": "Neutral",
               "entry": None, "sl": None, "tp": None,
               "nodes": [], "all_patterns": [], "error": None}
    if df is None or df.empty:
        return default
    df = df.copy()
    for col in ["Open", "High", "Low", "Close"]:
        if col not in df.columns:
            default["error"] = f"Missing: {col}"; return default
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["Open", "High", "Low", "Close"])
    if len(df) < 30:
        default["error"] = f"Insufficient: {len(df)}"; return default

    df_active = df.tail(200).copy()
    df_active = calculate_indicators(df_active)
    df_active = calculate_zigzag(df_active, CONFIG["ZIGZAG_DEPTH"], CONFIG["ZIGZAG_BACKSTEP"])
    pivots = get_chronological_pivots(df_active)
    all_patterns = detect_all_head_shoulders(pivots, df_active, is_backtest=False,
                                              max_gap=_get_max_gap(interval),
                                              max_pattern_duration=_get_max_pattern_duration(interval))
    if not all_patterns:
        default["df"] = df_active; return default

    latest = all_patterns[-1]
    signal = "STRONG BUY" if latest["bias"] == "Bullish" else "STRONG SELL"
    return {
        "df": df_active, "symbol": symbol or "N/A",
        "signal": signal, "pattern": latest["pattern"], "bias": latest["bias"],
        "entry": latest["entry"], "sl": latest["sl"], "tp": latest["tp"],
        "nodes": latest["nodes"], "all_patterns": all_patterns,
        "Trade Recommendation": latest.get("Trade Recommendation", ""),
        "error": None,
    }


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
    all_patterns = detect_all_head_shoulders(pivots, df, is_backtest=True,
                                              max_gap=_get_max_gap(interval),
                                              max_pattern_duration=_get_max_pattern_duration(interval))

    trades = []
    for p in all_patterns:
        trade = {
            "Symbol": symbol or "N/A", "symbol": symbol or "N/A",
            "Pattern": p["pattern"], "pattern": p["pattern"],
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
        }
        trades.append(trade)
    return trades


def diagnose_filters(df, interval="1h", symbol=None):
    result = {"error": None, "total_raw_candidates": 0, "final_count": 0,
              "stages": {}, "smart_diagnosis": {}, "recommendations": [],
              "trade_analysis": [], "tp_distribution": {}, "extension_analysis": {}}

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

    validator = PatternValidatorPipeline(df)
    stages = {k: {"before": 0, "after": 0, "rejected": 0, "pass_rate": "0%"}
              for k in ["1. الوقت", "2. الاختراق", "3. التأكيد", "4. الحجم"]}

    if len(pivots) >= 6:
        for i in range(len(pivots) - 5):
            p = pivots[i:i + 6]
            if [x["type"] for x in p] not in (["L","H","L","H","L","H"], ["H","L","H","L","H","L"]):
                continue
            stages["1. الوقت"]["before"] += 1
            if validator.time_filter(p):
                stages["1. الوقت"]["after"] += 1
            else:
                stages["1. الوقت"]["rejected"] += 1; continue

            br = validator.breakout_filter(p)
            stages["2. الاختراق"]["before"] += 1
            if br is None:
                stages["2. الاختراق"]["rejected"] += 1; continue
            stages["2. الاختراق"]["after"] += 1

            bi, bp = br
            stages["3. التأكيد"]["before"] += 1
            if not validator.breakout_confirm_filter(p, bp):
                stages["3. التأكيد"]["rejected"] += 1; continue
            stages["3. التأكيد"]["after"] += 1

            stages["4. الحجم"]["before"] += 1
            if not validator.volume_filter(bi):
                stages["4. الحجم"]["rejected"] += 1; continue
            stages["4. الحجم"]["after"] += 1

    for k, v in stages.items():
        if v["before"] > 0:
            v["pass_rate"] = f"{round(v['after'] / v['before'] * 100, 1)}%"
    result["stages"] = stages

    trades = backtest_strategy(df, interval=interval, symbol=symbol)
    result["final_count"] = len(trades)

    wins = [t for t in trades if "WIN" in str(t.get("Result","")).upper()]
    losses = [t for t in trades if "LOSS" in str(t.get("Result","")).upper()]
    bes = [t for t in trades if "BREAKEVEN" in str(t.get("Result","")).upper()]
    tos = [t for t in trades if "TIMEOUT" in str(t.get("Result","")).upper()]

    win_ext = [t.get("Max Extension %", 0) for t in wins if t.get("Max Extension %") is not None]
    all_ext = [t.get("Max Extension %", 0) for t in trades if t.get("Max Extension %") is not None]

    def _pct(lst, cond):
        return round(sum(1 for x in lst if cond(x)) / max(len(lst), 1) * 100, 1)

    ext_analysis = {
        "sample_wins": len(win_ext),
        "median_extension_wins_%": round(float(np.median(win_ext)), 1) if win_ext else 0,
        "median_extension_all_%": round(float(np.median(all_ext)), 1) if all_ext else 0,
        "max_extension_seen_%": round(max(all_ext), 1) if all_ext else 0,
        "pct_wins_reach_1.0x": _pct(win_ext, lambda x: x >= 100),
        "pct_wins_reach_1.5x": _pct(win_ext, lambda x: x >= 150),
        "pct_wins_reach_2.0x": _pct(win_ext, lambda x: x >= 200),
        "pct_wins_reach_2.5x": _pct(win_ext, lambda x: x >= 250),
        "pct_wins_reach_3.0x": _pct(win_ext, lambda x: x >= 300),
    }
    r2 = ext_analysis["pct_wins_reach_2.0x"]
    if r2 >= 60:
        ext_analysis["recommendation"] = f"✅ {r2}% بلغت 2× — 1:2 آمن."
        ext_analysis["suggested_TP_FACTOR"] = 2.0
    elif ext_analysis["pct_wins_reach_1.5x"] >= 60:
        ext_analysis["recommendation"] = "🟡 الأغلبية 1.5× — استخدم 1.5:1."
        ext_analysis["suggested_TP_FACTOR"] = 1.5
    else:
        ext_analysis["recommendation"] = "🔴 ابقَ على 1:1."
        ext_analysis["suggested_TP_FACTOR"] = 1.0
    result["extension_analysis"] = ext_analysis

    win_reach = [t.get("Max Reach %", 0) for t in wins]
    result["tp_distribution"] = {
        "wins_count": len(wins),
        "median_win_reach_%": round(float(np.median(win_reach)), 1) if win_reach else 0,
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

    total_closed = len(wins) + len(losses)
    win_rate = round(len(wins) / total_closed * 100, 1) if total_closed else 0

    if total_closed == 0:
        verdict = "لا صفقات كافية"
    elif win_rate >= 70:
        verdict = f"ممتاز — {win_rate}%"
    elif win_rate >= 50:
        verdict = f"جيد — {win_rate}%"
    elif win_rate >= 35:
        verdict = f"متوسط — {win_rate}%"
    else:
        verdict = f"ضعيف — {win_rate}%"

    result["smart_diagnosis"] = {
        "verdict": verdict,
        "loss_breakdown": loss_breakdown,
        "wins_count": len(wins),
        "losses_count": len(losses),
        "breakevens_count": len(bes),
        "timeouts_count": len(tos),
        "action_plan": [ext_analysis["recommendation"]],
    }
    result["trade_analysis"] = trades
    return result


if __name__ == "__main__":
    print("ENGINE.PY v3 — H&S + Strict Diagnostics")
    print(f"TP Factor: {CONFIG['TP_REACH_FACTOR']} | "
          f"Safe SL: {CONFIG['USE_SAFE_SL']} | "
          f"Trailing: Head-based")
