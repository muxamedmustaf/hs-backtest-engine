# -*- coding: utf-8 -*-
"""
ENGINE.PY - Head & Shoulders Detector + Diagnostics
No EMA / No RSI / Break-even + Time Stop 700
"""
import pandas as pd
import numpy as np

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
    "BREAKEVEN_ACTIVATION_PCT": 0.60,
}

TIMEOUT_STATISTICAL_FLOOR = 200
TIMEOUT_DURATION_MULTIPLIER = 3


# ==============================================================================
# 🧠 خريطة أسباب الخسارة والتصرف المناسب
# ==============================================================================
REASON_MAP = {
    "immediate_rejection": {
        "reason": "السعر رفض خط العنق فورًا بعد الاختراق — السيولة ضعيفة أو الاختراق وهمي.",
        "action": "انتظر إعادة اختبار خط العنق مع شمعة تأكيد قبل الدخول.",
        "prevention": "لا تدخل عند أول لمسة؛ انتظر إغلاق شمعة فوق خط العنق + حجم تداول مرتفع."
    },
    "early_reversal": {
        "reason": "انعكاس مبكر قبل الوصول إلى 30% من الهدف — ضغط بيعي/شرائي مفاجئ.",
        "action": "نقل وقف الخسارة إلى التعادل (Breakeven) عند 20% من الهدف.",
        "prevention": "استخدم Trailing Stop بعد 15-20 نقطة، أو ادخل بنصف الحجم ثم عزّز."
    },
    "mid_reversal": {
        "reason": "انعكاس في منتصف الطريق — السوق واجه مقاومة/دعمًا متوسطًا.",
        "action": "جزّئ الخروج: 50% عند 50% من الهدف، والباقي بـ Trailing Stop.",
        "prevention": "حدد TP جزئي عند أقرب مستوى عرضي قبل الدخول."
    },
    "late_reversal": {
        "reason": "وصل السعر إلى 70%+ من الهدف ثم عاد — ضغط أخبار أو جني أرباح.",
        "action": "استخدم Trailing Stop بنسبة 30% من الهدف.",
        "prevention": "راقب التقويم الاقتصادي؛ أغلق قبل الأخبار الكبرى."
    },
    "timeout": {
        "reason": "انتهت مدة الصفقة دون لمس TP أو SL — سوق عرضي.",
        "action": "أغلق يدويًا إذا تجاوزت مدة الصفقة 2× المتوسط التاريخي.",
        "prevention": "أضف فلتر ADX > 20 لتجنب الأسواق العرضية."
    },
    "breakeven": {
        "reason": "الصفقة أُغلقت عند التعادل — حماية رأس المال.",
        "action": "لا شيء؛ هذا سلوك صحيح.",
        "prevention": "استمر في استخدام Breakeven Stop."
    },
    "success": {
        "reason": "وصل السعر إلى الهدف بالكامل.",
        "action": "سجّل الإعداد وكرره.",
        "prevention": "—"
    },
    "open": {
        "reason": "الصفقة ما زالت مفتوحة عند انتهاء فترة الاختبار.",
        "action": "راقبها يدويًا حتى الإغلاق.",
        "prevention": "—"
    },
}


def _get_max_gap(interval):
    return {
        "1m": 120, "2m": 90, "3m": 80, "4m": 70,
        "5m": 50, "10m": 40, "15m": 30, "30m": 25, "45m": 22,
        "1h": 20, "2h": 18, "3h": 17, "4h": 15, "6h": 13,
        "8h": 12, "12h": 11, "1d": 10, "2d": 8, "3d": 7,
        "1wk": 5, "1mo": 3,
    }.get(interval, 50)


def _get_max_pattern_duration(interval):
    return {
        "1m": 600, "2m": 400, "3m": 320, "4m": 280,
        "5m": 200, "10m": 180, "15m": 150, "30m": 120, "45m": 110,
        "1h": 100, "2h": 90, "3h": 85, "4h": 80, "6h": 75,
        "8h": 70, "12h": 65, "1d": 60, "2d": 50, "3d": 45,
        "1wk": 30, "1mo": 20,
    }.get(interval, 200)


def calculate_indicators(df):
    df = df.copy()
    high_low = df["High"] - df["Low"]
    high_close = np.abs(df["High"] - df["Close"].shift())
    low_close = np.abs(df["Low"] - df["Close"].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = ranges.max(axis=1)
    df["ATR"] = true_range.rolling(14).mean()
    df["Dynamic_Swing"] = (df["ATR"] / df["Close"]) * 0.5
    df["Dynamic_Swing"] = df["Dynamic_Swing"].fillna(0.001)

    if "Volume" in df.columns:
        vol_numeric = pd.to_numeric(df["Volume"], errors="coerce").fillna(0.0)
        df["Volume"] = vol_numeric
        df["Volume_MA"] = vol_numeric.rolling(CONFIG["VOLUME_MA_PERIOD"]).mean().fillna(0.0)
        df["Has_Valid_Volume"] = vol_numeric.std() > 0
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
        high_window = highs[i - depth:i + backstep + 1]
        low_window = lows[i - depth:i + backstep + 1]
        current_high = highs[i]
        current_low = lows[i]

        is_high = (current_high == np.max(high_window) and np.sum(high_window == current_high) == 1)
        is_low = (current_low == np.min(low_window) and np.sum(low_window == current_low) == 1)

        if is_high and not is_low:
            df.iloc[i, df.columns.get_loc("Pivot_H")] = current_high
        elif is_low and not is_high:
            df.iloc[i, df.columns.get_loc("Pivot_L")] = current_low

    return df


def get_chronological_pivots(df):
    raw = []
    for pos, (idx, row) in enumerate(df.iterrows()):
        if not pd.isna(row["Pivot_H"]):
            raw.append({"idx": idx, "pos": pos, "val": float(row["Pivot_H"]), "type": "H",
                        "dynamic_swing": float(row.get("Dynamic_Swing", 0.001))})
        elif not pd.isna(row["Pivot_L"]):
            raw.append({"idx": idx, "pos": pos, "val": float(row["Pivot_L"]), "type": "L",
                        "dynamic_swing": float(row.get("Dynamic_Swing", 0.001))})

    if not raw:
        return []

    clean = []
    for p in raw:
        if not clean:
            clean.append(p); continue
        last = clean[-1]
        current_min_swing = p["dynamic_swing"]
        if last["type"] != p["type"]:
            movement = abs(p["val"] - last["val"]) / max(abs(last["val"]), 1e-9)
            if movement >= current_min_swing:
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

    final_clean = []
    for p in clean:
        if not final_clean:
            final_clean.append(p)
        else:
            if final_clean[-1]["type"] != p["type"]:
                final_clean.append(p)
            else:
                if p["type"] == "H" and p["val"] > final_clean[-1]["val"]:
                    final_clean[-1] = p
                elif p["type"] == "L" and p["val"] < final_clean[-1]["val"]:
                    final_clean[-1] = p

    return final_clean


def simulate_trade_outcome(pattern, df):
    """محاكاة مع Break-even + Trailing Stop تدريجي + Time Stop."""
    bias = pattern["bias"]
    entry = float(pattern["entry"])
    initial_sl = float(pattern["sl"])
    sl = initial_sl
    tp = float(pattern["tp"])
    end_idx = pattern["neckline_end_idx"]

    nodes = pattern.get("nodes", [])
    if len(nodes) >= 6:
        first_idx = nodes[0][0]
        h3_idx = nodes[-2][0]
        try:
            first_pos = df.index.get_loc(first_idx)
            h3_pos = df.index.get_loc(h3_idx)
            pattern_duration = max(1, h3_pos - first_pos)
        except KeyError:
            pattern_duration = 50
    else:
        pattern_duration = 50

    TIMEOUT_CANDLES = max(
        TIMEOUT_STATISTICAL_FLOOR,
        pattern_duration * TIMEOUT_DURATION_MULTIPLIER
    )
    BE_ACTIVATION = CONFIG.get("BREAKEVEN_ACTIVATION_PCT", 0.30)

    TRAILING_LEVELS = [
        (BE_ACTIVATION, 0.00),
        (0.50, 0.30),
        (0.70, 0.50),
        (0.90, 0.70),
    ]

    breakeven_activated = False
    trailing_stage = 0

    stats = {
        "Result": "OPEN", "Head Result": "OPEN",
        "progress_ratio": 0.0, "candles_to_exit": 0,
        "exit_idx": None, "exit_price": None,
        "Entry Date": None, "Exit Date": None,
        "Max Reach %": 0.0, "SL Safety %": 0.0,
        "Pattern Duration": pattern_duration,
        "Timeout Used": TIMEOUT_CANDLES,
        "Breakeven Activated": False,
        "Breakeven Exit": False,
        "Trailing Stage": 0,
        "Initial SL": initial_sl,
        "Final SL": initial_sl,
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

        progress = (favorable / total_tp_dist) if total_tp_dist > 0 else 0.0

        if total_tp_dist > 0:
            max_favorable = max(max_favorable, progress * 100)
        if total_sl_dist > 0:
            max_adverse = max(max_adverse, adverse / total_sl_dist * 100)

        # Trailing Stop تدريجي
        for stage_idx, (threshold, profit_ratio) in enumerate(TRAILING_LEVELS):
            if stage_idx < trailing_stage:
                continue
            if progress < threshold:
                break

            if profit_ratio == 0.0:
                new_sl = entry
            else:
                if bias == "Bearish":
                    new_sl = entry - profit_ratio * total_tp_dist
                else:
                    new_sl = entry + profit_ratio * total_tp_dist

            if bias == "Bearish":
                if new_sl < sl:
                    sl = new_sl
                    trailing_stage = stage_idx + 1
                    if profit_ratio == 0.0:
                        breakeven_activated = True
                        stats["Breakeven Activated"] = True
            else:
                if new_sl > sl:
                    sl = new_sl
                    trailing_stage = stage_idx + 1
                    if profit_ratio == 0.0:
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

        if hit_sl:
            if bias == "Bearish":
                is_profit = sl < entry - 1e-9
                is_breakeven = abs(sl - entry) < 1e-9
            else:
                is_profit = sl > entry + 1e-9
                is_breakeven = abs(sl - entry) < 1e-9

            if is_breakeven:
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
            break

        elif hit_tp:
            stats["Result"] = "WIN"
            stats["Head Result"] = "WIN"
            stats["Loss Category"] = "success"
            stats["exit_idx"] = idx
            stats["exit_price"] = tp
            stats["candles_to_exit"] = candle_count
            stats["Exit Date"] = str(idx)
            break

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
            break
    else:
        stats["candles_to_exit"] = max(0, len(post_df) - 1)
        stats["Exit Date"] = str(df.index[-1])
        stats["Loss Category"] = "open"

    stats["Max Reach %"] = round(max_favorable, 1)
    stats["SL Safety %"] = round(100 - max_adverse, 1) if max_adverse <= 100 else 0.0

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

    def invalidation_filter(self, p):
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
        min_pct = CONFIG.get("BREAKOUT_MIN_PCT", 0.001)
        if is_bearish:
            return breakout_price <= neckline * (1 - min_pct)
        else:
            return breakout_price >= neckline * (1 + min_pct)

    def volume_filter(self, breakout_idx):
        if not CONFIG.get("REQUIRE_VOLUME_BREAKOUT", False):
            return True
        if breakout_idx not in self.df.index:
            return False
        row = self.df.loc[breakout_idx]
        vol = float(row.get("Volume", 0))
        vol_ma = float(row.get("Volume_MA", 0))
        if vol == 0 or vol_ma == 0:
            return True
        factor = CONFIG.get("VOLUME_FACTOR", 1.2)
        return vol >= vol_ma * factor

    def run(self, p):
        if not self.time_filter(p):
            return False, None, None
        if not self.invalidation_filter(p):
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
        if abs(h1 - h3) > (head_height * CONFIG["SHOULDER_DIFF_MAX_RATIO"]): continue
        max_shoulder = max(h1, h3)
        if (h2 - max_shoulder) < (head_height * CONFIG["HEAD_PROPORTION_MIN_RATIO"]): continue
        if abs(l1 - l2) > (head_height * CONFIG["NECKLINE_DIFF_MAX_RATIO"]): continue
        l0_pos = p[0]["pos"]; h3_pos = p[5]["pos"]
        pattern_size = h3_pos - l0_pos
        if pattern_size > max_pattern_duration: continue
        passed, end_idx, end_val = validator.run(p)
        if not passed: continue
        if end_idx not in df.index: continue
        end_pos = df.index.get_loc(end_idx)
        if (end_pos - h3_pos) > max_gap: continue
        if not is_backtest:
            if (total_candles - end_pos) > CONFIG["LIVE_MAX_BREAKOUT_CANDLES"]:
                continue

        l1_idx, l2_idx = p[2]["idx"], p[4]["idx"]
        neckline_avg = (l1 + l2) / 2.0
        actual_head_length = h2 - neckline_avg
        entry = neckline_avg; sl = h2; tp = entry - actual_head_length

        nodes = [(x["idx"], x["val"]) for x in p]
        nodes.append((end_idx, float(end_val)))

        pattern = {
            "name": "Head and Shoulders", "pattern": "Head and Shoulders",
            "bias": "Bearish", "match": 100.0, "nodes": nodes,
            "entry": float(round(entry, 5)), "entry_trigger": float(round(entry, 5)),
            "sl": float(round(sl, 5)), "tp": float(round(tp, 5)),
            "neckline_start_idx": l1_idx, "neckline_end_idx": end_idx,
            "neckline_nodes": [(l1_idx, l1), (l2_idx, l2)],
            "target_nodes": [(end_idx, float(round(entry, 5))), (end_idx, float(round(tp, 5)))],
            "end_pos": p[5]["pos"],
            "SL": float(round(sl, 5)), "TP": float(round(tp, 5)),
            "Entry": float(round(entry, 5)),
            "Pattern": "Head and Shoulders",
            "Entry Conditions": "Breakout Only",
        }
        sim = simulate_trade_outcome(pattern, df)
        pattern.update(sim)
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
        if abs(l1 - l3) > (head_depth * CONFIG["SHOULDER_DIFF_MAX_RATIO"]): continue
        min_shoulder = min(l1, l3)
        if (min_shoulder - l2) < (head_depth * CONFIG["HEAD_PROPORTION_MIN_RATIO"]): continue
        if abs(h1 - h2) > (head_depth * CONFIG["NECKLINE_DIFF_MAX_RATIO"]): continue
        positions = [x["pos"] for x in p]
        if any((positions[j+1] - positions[j]) < CONFIG["MIN_WAVE_CANDLES"] for j in range(len(positions) - 1)):
            continue
        h0_pos = p[0]["pos"]; l3_pos = p[5]["pos"]
        pattern_size = l3_pos - h0_pos
        if pattern_size > max_pattern_duration: continue
        idx_l2 = p[3]["idx"]
        post_head_df = df.loc[idx_l2:]
        if not post_head_df.empty and post_head_df["Low"].min() < l2: continue
        passed, end_idx, end_val = validator.run(p)
        if not passed: continue
        if end_idx not in df.index: continue
        end_pos = df.index.get_loc(end_idx)
        if (end_pos - l3_pos) > max_gap: continue
        if not is_backtest:
            if (total_candles - end_pos) > CONFIG["LIVE_MAX_BREAKOUT_CANDLES"]:
                continue

        h1_idx, h2_idx = p[2]["idx"], p[4]["idx"]
        neckline_avg = (h1 + h2) / 2.0
        actual_head_length = neckline_avg - l2
        entry = neckline_avg; sl = l2; tp = entry + actual_head_length

        nodes = [(x["idx"], x["val"]) for x in p]
        nodes.append((end_idx, end_val))

        pattern = {
            "name": "Inverse Head and Shoulders", "pattern": "Inverse Head and Shoulders",
            "bias": "Bullish", "match": 100.0, "nodes": nodes,
            "entry": float(round(entry, 5)), "entry_trigger": float(round(entry, 5)),
            "sl": float(round(sl, 5)), "tp": float(round(tp, 5)),
            "neckline_start_idx": h1_idx, "neckline_end_idx": end_idx,
            "neckline_nodes": [(h1_idx, h1), (h2_idx, h2)],
            "target_nodes": [(end_idx, float(round(entry, 5))), (end_idx, float(round(tp, 5)))],
            "end_pos": p[5]["pos"],
            "SL": float(round(sl, 5)), "TP": float(round(tp, 5)),
            "Entry": float(round(entry, 5)),
            "Pattern": "Inverse Head and Shoulders",
            "Entry Conditions": "Breakout Only",
        }
        sim = simulate_trade_outcome(pattern, df)
        pattern.update(sim)
        patterns.append(pattern)
    return patterns


def detect_all_head_shoulders(pivots, df, is_backtest=False,
                               max_gap=50, max_pattern_duration=200):
    normal_patterns = detect_all_head_shoulders_base(pivots, df, is_backtest, max_gap, max_pattern_duration)
    inverse_patterns = detect_all_inverse_head_shoulders(pivots, df, is_backtest, max_gap, max_pattern_duration)
    all_patterns = normal_patterns + inverse_patterns
    all_patterns.sort(key=lambda x: x.get("end_pos", -1))
    return all_patterns


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
    all_patterns = detect_all_head_shoulders(pivots, df_active, is_backtest=False,
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
        "Entry Date": latest.get("Entry Date"), "Exit Date": latest.get("Exit Date"),
        "error": None,
    }


def backtest_strategy(df, interval="1h", symbol=None):
    if df is None or df.empty or len(df) < 30:
        return []
    df = df.copy()
    required = ["Open", "High", "Low", "Close"]
    for col in required:
        if col not in df.columns:
            return []
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=required)
    if len(df) < 30:
        return []

    df = calculate_indicators(df)
    df = calculate_zigzag(df, CONFIG["ZIGZAG_DEPTH"], CONFIG["ZIGZAG_BACKSTEP"])
    pivots = get_chronological_pivots(df)
    max_gap = _get_max_gap(interval)
    max_pattern_dur = _get_max_pattern_duration(interval)
    all_patterns = detect_all_head_shoulders(pivots, df, is_backtest=True,
                                              max_gap=max_gap, max_pattern_duration=max_pattern_dur)

    trades = []
    for p in all_patterns:
        trade = {
            "Symbol": symbol or "N/A",
            "symbol": symbol or "N/A",
            "Pattern": p["pattern"], "pattern": p["pattern"],
            "Bias": p["bias"], "bias": p["bias"],
            "Result": p.get("Result", "OPEN"),
            "Head Result": p.get("Head Result", "OPEN"),
            "Entry": p["entry"], "Entry Price": p["entry"],
            "SL": p["sl"], "Stop Loss": p["sl"],
            "TP": p["tp"], "Take Profit": p["tp"],
            "Entry Date": p.get("Entry Date"), "Exit Date": p.get("Exit Date"),
            "Exit Price": p.get("exit_price"),
            "time": p.get("Entry Date"), "close_time": p.get("Exit Date"),
            "Max Reach %": p.get("Max Reach %", 0.0),
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
            "Initial SL":     p.get("Initial SL"),
            "Final SL":       p.get("Final SL"),
        }
        trades.append(trade)
    return trades


# ==============================================================================
# 🔬 دالة التشخيص الذكي (كانت مفقودة)
# ==============================================================================
def diagnose_filters(df, interval="1h", symbol=None):
    """يحلل الفلاتر ويكتشف أسباب الخسارة والتصرف المناسب."""
    result = {
        "error": None,
        "total_raw_candidates": 0,
        "final_count": 0,
        "stages": {},
        "smart_diagnosis": {},
        "recommendations": [],
        "rejection_samples": {},
        "trade_analysis": [],
    }

    if df is None or df.empty or len(df) < 30:
        result["error"] = "بيانات غير كافية للتشخيص"
        return result

    df = df.copy()
    required = ["Open", "High", "Low", "Close"]
    for col in required:
        if col not in df.columns:
            result["error"] = f"عمود مفقود: {col}"
            return result
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=required)

    df = calculate_indicators(df)
    df = calculate_zigzag(df, CONFIG["ZIGZAG_DEPTH"], CONFIG["ZIGZAG_BACKSTEP"])
    pivots = get_chronological_pivots(df)

    # 1. العدّ الخام (قبل الفلاتر)
    raw_count = 0
    if len(pivots) >= 6:
        for i in range(len(pivots) - 5):
            p = pivots[i:i + 6]
            if [x["type"] for x in p] in (["L","H","L","H","L","H"], ["H","L","H","L","H","L"]):
                raw_count += 1
    result["total_raw_candidates"] = raw_count

    # 2. تشغيل الفلاتر مرحلة بمرحلة
    validator = PatternValidatorPipeline(df)
    stages = {
        "1. فلتر الوقت (MIN_WAVE_CANDLES)": {"before": 0, "after": 0, "rejected": 0, "pass_rate": "0%"},
        "2. فلتر الاختراق (Breakout)": {"before": 0, "after": 0, "rejected": 0, "pass_rate": "0%"},
        "3. فلتر تأكيد الاختراق": {"before": 0, "after": 0, "rejected": 0, "pass_rate": "0%"},
        "4. فلتر الحجم": {"before": 0, "after": 0, "rejected": 0, "pass_rate": "0%"},
    }

    # نطبق الفلاتر خطوة بخطوة لتسجيل عدد المرفوضات
    if len(pivots) >= 6:
        for i in range(len(pivots) - 5):
            p = pivots[i:i + 6]
            if [x["type"] for x in p] not in (["L","H","L","H","L","H"], ["H","L","H","L","H","L"]):
                continue

            stages["1. فلتر الوقت (MIN_WAVE_CANDLES)"]["before"] += 1
            if validator.time_filter(p):
                stages["1. فلتر الوقت (MIN_WAVE_CANDLES)"]["after"] += 1
            else:
                stages["1. فلتر الوقت (MIN_WAVE_CANDLES)"]["rejected"] += 1
                continue

            br = validator.breakout_filter(p)
            stages["2. فلتر الاختراق (Breakout)"]["before"] += 1
            if br is None:
                stages["2. فلتر الاختراق (Breakout)"]["rejected"] += 1
                continue
            else:
                stages["2. فلتر الاختراق (Breakout)"]["after"] += 1

            breakout_idx, breakout_price = br
            stages["3. فلتر تأكيد الاختراق"]["before"] += 1
            if not validator.breakout_confirm_filter(p, breakout_price):
                stages["3. فلتر تأكيد الاختراق"]["rejected"] += 1
                continue
            else:
                stages["3. فلتر تأكيد الاختراق"]["after"] += 1

            stages["4. فلتر الحجم"]["before"] += 1
            if not validator.volume_filter(breakout_idx):
                stages["4. فلتر الحجم"]["rejected"] += 1
                continue
            else:
                stages["4. فلتر الحجم"]["after"] += 1

    for k, v in stages.items():
        if v["before"] > 0:
            v["pass_rate"] = f"{round(v['after'] / v['before'] * 100, 1)}%"
    result["stages"] = stages

    # 3. تشغيل الباكتست لتحليل الصفقات
    trades = backtest_strategy(df, interval=interval, symbol=symbol)
    result["final_count"] = len(trades)

    wins = [t for t in trades if "WIN" in str(t.get("Result", "")).upper()]
    losses = [t for t in trades if "LOSS" in str(t.get("Result", "")).upper()]
    breakevens = [t for t in trades if "BREAKEVEN" in str(t.get("Result", "")).upper()]
    timeouts = [t for t in trades if "TIMEOUT" in str(t.get("Result", "")).upper()]

    # 4. تفصيل الرابحة
    win_breakdown = {"total_wins": len(wins), "avg_max_reach": 0.0}
    if wins:
        win_breakdown["avg_max_reach"] = round(
            sum(t.get("Max Reach %", 0) for t in wins) / len(wins), 1
        )

    # 5. تفصيل الخاسرة حسب التصنيف
    loss_breakdown = {
        "immediate_rejection": 0, "early_reversal": 0,
        "mid_reversal": 0, "late_reversal": 0,
        "unavoidable": 0, "avoidable": 0,
    }
    for t in losses:
        cat = t.get("Loss Category") or ""
        if cat in loss_breakdown:
            loss_breakdown[cat] += 1
        reach = t.get("Max Reach %", 0)
        # خسائر لا مفر منها: وصلت السعر إلى 60%+ ثم انعكس
        if reach >= 60:
            loss_breakdown["unavoidable"] += 1
        else:
            loss_breakdown["avoidable"] += 1

    # 6. تحليل كل صفقة
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
            "result": t.get("Result", "—"),
            "category": cat,
            "max_reach_%": t.get("Max Reach %", 0),
            "rr_ratio": rr,
            "is_unavoidable": t.get("Max Reach %", 0) >= 60 and "LOSS" in str(t.get("Result", "")).upper(),
            "reason": info.get("reason", "—"),
            "action": info.get("action", "—"),
            "prevention": info.get("prevention", "—"),
            "recommendation": f"{info.get('action','')} | وقاية: {info.get('prevention','')}",
        })

    # 7. الحكم النهائي وخطة العمل
    total_closed = len(wins) + len(losses)
    win_rate = round(len(wins) / total_closed * 100, 1) if total_closed > 0 else 0
    avoidable = loss_breakdown["avoidable"]
    unavoidable = loss_breakdown["unavoidable"]

    if total_closed == 0:
        verdict = "لا توجد صفقات مغلقة كافية للحكم"
    elif win_rate >= 70:
        verdict = f"أداء ممتاز — نسبة نجاح {win_rate}%"
    elif win_rate >= 50:
        verdict = f"أداء جيد — نسبة نجاح {win_rate}%"
    elif win_rate >= 35:
        verdict = f"أداء متوسط — يحتاج تحسين (نجاح {win_rate}%)"
    else:
        verdict = f"أداء ضعيف — يتطلب مراجعة الفلاتر (نجاح {win_rate}%)"

    action_plan = []
    if avoidable > unavoidable:
        action_plan.append(f"🔴 عدد الخسائر القابلة للتجنب ({avoidable}) أكبر من غير القابلة ({unavoidable}) — راجع شروط الدخول.")
    elif unavoidable > 0:
        action_plan.append(f"🟢 معظم الخسائر ({unavoidable}) لا مفر منها إحصائيًا — النظام يعمل بشكل طبيعي.")
    if loss_breakdown["immediate_rejection"] > 0:
        action_plan.append(f"🟡 {loss_breakdown['immediate_rejection']} صفقة رُفضت فورًا — أضف شرط إغلاق شمعة فوق خط العنق.")
    if loss_breakdown["early_reversal"] > 0:
        action_plan.append(f"🟡 {loss_breakdown['early_reversal']} صفقة انعكست مبكرًا — استخدم Trailing Stop بعد 20% من الهدف.")
    if loss_breakdown["mid_reversal"] > 0:
        action_plan.append(f"🟡 {loss_breakdown['mid_reversal']} صفقة انعكست في المنتصف — جزّئ الخروج عند 50%.")
    if loss_breakdown["late_reversal"] > 0:
        action_plan.append(f"🟢 {loss_breakdown['late_reversal']} صفقة وصلت 70%+ ثم عادت — ضع Trailing Stop بنسبة 30%.")

    result["smart_diagnosis"] = {
        "verdict": verdict,
        "win_breakdown": win_breakdown,
        "loss_breakdown": loss_breakdown,
        "action_plan": action_plan,
    }

    # 8. توصيات عامة
    recommendations = []
    if raw_count > 0 and result["final_count"] / max(raw_count, 1) < 0.1:
        recommendations.append({"severity": "متوسط", "message": "نسبة القبول منخفضة جدًا (< 10%) — راجع شدة الفلاتر."})
    if len(timeouts) > len(wins):
        recommendations.append({"severity": "حرج", "message": "عدد الصفقات المنتهية بالوقت كبير — السوق عرضي، أضف فلتر اتجاه."})
    if len(breakevens) > 0:
        recommendations.append({"severity": "منخفض", "message": f"{len(breakevens)} صفقة أُغلقت عند التعادل — سلوك جيد لحماية رأس المال."})
    result["recommendations"] = recommendations

    result["trade_analysis"] = trade_analysis
    return result


if __name__ == "__main__":
    print("ENGINE.PY - H&S Detector + Diagnostics")
    print("Filters: time, breakout, confirm, volume")
    print("Diagnostics: diagnose_filters(df, interval, symbol)")
