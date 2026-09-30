# -*- coding: utf-8 -*-
"""
ENGINE.PY - Head & Shoulders Detector
Merged: v4.6 pattern logic + strict filters + diagnostics
"""
import pandas as pd
import numpy as np

# ==============================================================================
# [1] الإعدادات المركزية
# ==============================================================================
CONFIG = {
    "ZIGZAG_DEPTH": 12,
    "ZIGZAG_BACKSTEP": 6,
    "MIN_WAVE_CANDLES": 3,
    "SHOULDER_DIFF_MAX_RATIO": 0.35,
    "HEAD_PROPORTION_MIN_RATIO": 0.25,
    "NECKLINE_DIFF_MAX_RATIO": 0.25,
    "LIVE_MAX_BREAKOUT_CANDLES": 10,

    # RSI
    "RSI_MIN_BEARISH": 30.0,
    "RSI_MAX_BEARISH": 75.0,
    "RSI_MIN_BULLISH": 25.0,
    "RSI_MAX_BULLISH": 70.0,

    # EMA
    "EMA_FAST_SPAN": 50,
    "EMA_SLOW_SPAN": 200,

    # الاتجاه الصارم
    "REQUIRE_STRICT_TREND": True,

    # قوة الكسر
    "BREAKOUT_MIN_PCT": 0.001,

    # الحجم (اختياري)
    "REQUIRE_VOLUME_BREAKOUT": False,
    "VOLUME_FACTOR": 1.2,
    "VOLUME_MA_PERIOD": 20,
}

TIMEOUT_STATISTICAL_FLOOR = 300
TIMEOUT_DURATION_MULTIPLIER = 3


# ==============================================================================
# [1.b] الحد الأقصى للمسافة H3 → نقطة الكسر
# ==============================================================================
def _get_max_gap(interval):
    return {
        "1m": 120, "2m": 90, "3m": 80, "4m": 70,
        "5m": 50, "10m": 40, "15m": 30, "30m": 25, "45m": 22,
        "1h": 20, "2h": 18, "3h": 17, "4h": 15, "6h": 13,
        "8h": 12, "12h": 11, "1d": 10, "2d": 8, "3d": 7,
        "1wk": 5, "1mo": 3,
    }.get(interval, 50)


# ==============================================================================
# [1.c] الحد الأقصى لحجم النمط (L0 → H3)
# ==============================================================================
def _get_max_pattern_duration(interval):
    return {
        "1m": 600, "2m": 400, "3m": 320, "4m": 280,
        "5m": 200, "10m": 180, "15m": 150, "30m": 120, "45m": 110,
        "1h": 100, "2h": 90, "3h": 85, "4h": 80, "6h": 75,
        "8h": 70, "12h": 65, "1d": 60, "2d": 50, "3d": 45,
        "1wk": 30, "1mo": 20,
    }.get(interval, 200)


# ==============================================================================
# [2] حساب المؤشرات
# ==============================================================================
def calculate_indicators(df):
    df = df.copy()
    df["EMA50"] = df["Close"].ewm(span=CONFIG["EMA_FAST_SPAN"], adjust=False).mean()
    df["EMA200"] = df["Close"].ewm(span=CONFIG["EMA_SLOW_SPAN"], adjust=False).mean()

    delta = df["Close"].diff()
    gain = delta.where(delta > 0, 0.0).ewm(alpha=1/14, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0.0)).ewm(alpha=1/14, adjust=False).mean()
    loss_safe = loss.replace(0, 1e-9)
    rs = gain / loss_safe
    df["RSI"] = 100 - (100 / (1 + rs))
    df["RSI"] = df["RSI"].fillna(50.0)

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


# ==============================================================================
# [3] ZigZag
# ==============================================================================
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

        is_high = (
            current_high == np.max(high_window)
            and np.sum(high_window == current_high) == 1
        )
        is_low = (
            current_low == np.min(low_window)
            and np.sum(low_window == current_low) == 1
        )

        if is_high and not is_low:
            df.iloc[i, df.columns.get_loc("Pivot_H")] = current_high
        elif is_low and not is_high:
            df.iloc[i, df.columns.get_loc("Pivot_L")] = current_low

    return df


# ==============================================================================
# [4] تنقية النقاط الزمنية
# ==============================================================================
def get_chronological_pivots(df):
    raw = []

    for pos, (idx, row) in enumerate(df.iterrows()):
        if not pd.isna(row["Pivot_H"]):
            raw.append({
                "idx": idx, "pos": pos,
                "val": float(row["Pivot_H"]),
                "type": "H",
                "dynamic_swing": float(row.get("Dynamic_Swing", 0.001))
            })
        elif not pd.isna(row["Pivot_L"]):
            raw.append({
                "idx": idx, "pos": pos,
                "val": float(row["Pivot_L"]),
                "type": "L",
                "dynamic_swing": float(row.get("Dynamic_Swing", 0.001))
            })

    if not raw:
        return []

    clean = []
    for p in raw:
        if not clean:
            clean.append(p)
            continue

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


# ==============================================================================
# [5] محاكاة نتيجة الصفقة مع Time Stop
# ==============================================================================
def simulate_trade_outcome(pattern, df):
    bias = pattern["bias"]
    entry = float(pattern["entry"])
    sl = float(pattern["sl"])
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

    stats = {
        "Result": "OPEN", "Head Result": "OPEN",
        "progress_ratio": 0.0, "candles_to_exit": 0,
        "exit_idx": None, "exit_price": None,
        "Entry Date": None, "Exit Date": None,
        "Max Reach %": 0.0, "SL Safety %": 0.0,
        "Pattern Duration": pattern_duration,
        "Timeout Used": TIMEOUT_CANDLES,
    }

    if end_idx not in df.index:
        return stats

    post_df = df.loc[end_idx:]
    if len(post_df) <= 1:
        return stats

    stats["Entry Date"] = str(end_idx)

    total_tp_dist = abs(tp - entry)
    total_sl_dist = abs(sl - entry)
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

        if total_tp_dist > 0:
            max_favorable = max(max_favorable, favorable / total_tp_dist * 100)
        if total_sl_dist > 0:
            max_adverse = max(max_adverse, adverse / total_sl_dist * 100)

        if bias == "Bearish":
            hit_sl = high >= sl
            hit_tp = low <= tp
        else:
            hit_sl = low <= sl
            hit_tp = high >= tp

        if hit_sl and hit_tp:
            stats["Result"] = "LOSS"
            stats["Head Result"] = "LOSS"
            stats["exit_idx"] = idx
            stats["exit_price"] = sl
            stats["candles_to_exit"] = candle_count
            stats["Exit Date"] = str(idx)
            break
        elif hit_sl:
            stats["Result"] = "LOSS"
            stats["Head Result"] = "LOSS"
            stats["exit_idx"] = idx
            stats["exit_price"] = sl
            stats["candles_to_exit"] = candle_count
            stats["Exit Date"] = str(idx)
            break
        elif hit_tp:
            stats["Result"] = "WIN"
            stats["Head Result"] = "WIN"
            stats["exit_idx"] = idx
            stats["exit_price"] = tp
            stats["candles_to_exit"] = candle_count
            stats["Exit Date"] = str(idx)
            break

        if candle_count >= TIMEOUT_CANDLES:
            stats["Result"] = "TIMEOUT"
            stats["Head Result"] = "TIMEOUT"
            stats["exit_idx"] = idx
            stats["exit_price"] = close
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

    stats["Max Reach %"] = round(max_favorable, 1)
    stats["SL Safety %"] = round(100 - max_adverse, 1) if max_adverse <= 100 else 0.0

    if stats["Result"] == "WIN":
        stats["progress_ratio"] = 100.0
    elif stats["Result"] == "LOSS":
        stats["progress_ratio"] = 0.0

    return stats


# ==============================================================================
# [6] PatternValidatorPipeline
# ==============================================================================
class PatternValidatorPipeline:

    def __init__(self, df):
        self.df = df

    def time_filter(self, p):
        positions = [x["pos"] for x in p]
        for j in range(len(positions) - 1):
            if positions[j + 1] - positions[j] < CONFIG["MIN_WAVE_CANDLES"]:
                return False
        return True

    def strict_trend_filter(self, p):
        if not CONFIG.get("REQUIRE_STRICT_TREND", True):
            return True

        idx_end = p[5]["idx"]
        if idx_end not in self.df.index:
            return False

        row = self.df.loc[idx_end]
        ema50 = row.get("EMA50", None)
        ema200 = row.get("EMA200", None)
        price = row.get("Close", None)

        if pd.isna(ema50) or pd.isna(ema200) or pd.isna(price):
            return False

        ema50 = float(ema50)
        ema200 = float(ema200)
        price = float(price)
        is_bearish = (p[3]["type"] == "H")

        if is_bearish:
            return price < ema50 < ema200
        else:
            return price > ema50 > ema200

    def invalidation_filter(self, p):
        return True

    def indicator_filter(self, p):
        idx_end = p[5]["idx"]
        if idx_end not in self.df.index:
            return False
        rsi_val = self.df.loc[idx_end, "RSI"]
        if pd.isna(rsi_val):
            return False
        rsi_val = float(rsi_val)

        is_bearish = (p[3]["type"] == "H")
        if is_bearish:
            return CONFIG["RSI_MIN_BEARISH"] <= rsi_val <= CONFIG["RSI_MAX_BEARISH"]
        else:
            return CONFIG["RSI_MIN_BULLISH"] <= rsi_val <= CONFIG["RSI_MAX_BULLISH"]

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
        if not self.strict_trend_filter(p):
            return False, None, None
        if not self.invalidation_filter(p):
            return False, None, None
        if not self.indicator_filter(p):
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


# ==============================================================================
# [7] كشف H&S الهابط
# ==============================================================================
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

        if h1 <= l0 or l1 <= l0:
            continue
        if h2 <= h1 or h2 <= h3:
            continue

        neckline_min = min(l1, l2)
        head_height = h2 - neckline_min

        if head_height <= 0:
            continue

        if abs(h1 - h3) > (head_height * CONFIG["SHOULDER_DIFF_MAX_RATIO"]):
            continue

        max_shoulder = max(h1, h3)
        if (h2 - max_shoulder) < (head_height * CONFIG["HEAD_PROPORTION_MIN_RATIO"]):
            continue

        if abs(l1 - l2) > (head_height * CONFIG["NECKLINE_DIFF_MAX_RATIO"]):
            continue

        l0_pos = p[0]["pos"]
        h3_pos = p[5]["pos"]
        pattern_size = h3_pos - l0_pos
        if pattern_size > max_pattern_duration:
            continue

        passed, end_idx, end_val = validator.run(p)
        if not passed:
            continue

        if end_idx not in df.index:
            continue

        end_pos = df.index.get_loc(end_idx)

        if (end_pos - h3_pos) > max_gap:
            continue

        if not is_backtest:
            if (total_candles - end_pos) > CONFIG["LIVE_MAX_BREAKOUT_CANDLES"]:
                continue

        l1_idx, l2_idx = p[2]["idx"], p[4]["idx"]
        neckline_avg = (l1 + l2) / 2.0
        actual_head_length = h2 - neckline_avg

        entry = neckline_avg
        sl = h2
        tp = entry - actual_head_length

        nodes = [(x["idx"], x["val"]) for x in p]
        nodes.append((end_idx, float(end_val)))

        neckline_nodes = [(l1_idx, l1), (l2_idx, l2)]
        target_nodes = [
            (end_idx, float(round(entry, 5))),
            (end_idx, float(round(tp, 5)))
        ]

        pattern = {
            "name": "Head and Shoulders",
            "pattern": "Head and Shoulders",
            "bias": "Bearish",
            "match": 100.0,
            "nodes": nodes,
            "entry": float(round(entry, 5)),
            "entry_trigger": float(round(entry, 5)),
            "sl": float(round(sl, 5)),
            "tp": float(round(tp, 5)),
            "neckline_start_idx": l1_idx,
            "neckline_end_idx": end_idx,
            "neckline_nodes": neckline_nodes,
            "target_nodes": target_nodes,
            "end_pos": p[5]["pos"],
            "SL": float(round(sl, 5)),
            "TP": float(round(tp, 5)),
            "Entry": float(round(entry, 5)),
            "Pattern": "Head and Shoulders",
            "Entry Conditions": "Strict Trend + RSI + Breakout",
        }

        sim = simulate_trade_outcome(pattern, df)
        pattern.update(sim)
        patterns.append(pattern)

    return patterns


# ==============================================================================
# [8] كشف Inverse H&S الصاعد
# ==============================================================================
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

        if l2 >= l1 or l2 >= l3:
            continue

        neckline_max = max(h1, h2)
        head_depth = neckline_max - l2

        if head_depth <= 0:
            continue

        if abs(l1 - l3) > (head_depth * CONFIG["SHOULDER_DIFF_MAX_RATIO"]):
            continue

        min_shoulder = min(l1, l3)
        if (min_shoulder - l2) < (head_depth * CONFIG["HEAD_PROPORTION_MIN_RATIO"]):
            continue

        if abs(h1 - h2) > (head_depth * CONFIG["NECKLINE_DIFF_MAX_RATIO"]):
            continue

        positions = [x["pos"] for x in p]
        if any((positions[j+1] - positions[j]) < CONFIG["MIN_WAVE_CANDLES"]
               for j in range(len(positions) - 1)):
            continue

        h0_pos = p[0]["pos"]
        l3_pos = p[5]["pos"]
        pattern_size = l3_pos - h0_pos
        if pattern_size > max_pattern_duration:
            continue

        idx_l2 = p[3]["idx"]
        post_head_df = df.loc[idx_l2:]
        if not post_head_df.empty and post_head_df["Low"].min() < l2:
            continue

        passed, end_idx, end_val = validator.run(p)
        if not passed:
            continue

        if end_idx not in df.index:
            continue

        end_pos = df.index.get_loc(end_idx)

        if (end_pos - l3_pos) > max_gap:
            continue

        if not is_backtest:
            if (total_candles - end_pos) > CONFIG["LIVE_MAX_BREAKOUT_CANDLES"]:
                continue

        h1_idx, h2_idx = p[2]["idx"], p[4]["idx"]
        neckline_avg = (h1 + h2) / 2.0
        actual_head_length = neckline_avg - l2

        entry = neckline_avg
        sl = l2
        tp = entry + actual_head_length

        nodes = [(x["idx"], x["val"]) for x in p]
        nodes.append((end_idx, end_val))

        neckline_nodes = [(h1_idx, h1), (h2_idx, h2)]
        target_nodes = [
            (end_idx, float(round(entry, 5))),
            (end_idx, float(round(tp, 5)))
        ]

        pattern = {
            "name": "Inverse Head and Shoulders",
            "pattern": "Inverse Head and Shoulders",
            "bias": "Bullish",
            "match": 100.0,
            "nodes": nodes,
            "entry": float(round(entry, 5)),
            "entry_trigger": float(round(entry, 5)),
            "sl": float(round(sl, 5)),
            "tp": float(round(tp, 5)),
            "neckline_start_idx": h1_idx,
            "neckline_end_idx": end_idx,
            "neckline_nodes": neckline_nodes,
            "target_nodes": target_nodes,
            "end_pos": p[5]["pos"],
            "SL": float(round(sl, 5)),
            "TP": float(round(tp, 5)),
            "Entry": float(round(entry, 5)),
            "Pattern": "Inverse Head and Shoulders",
            "Entry Conditions": "Strict Trend + RSI + Breakout",
        }

        sim = simulate_trade_outcome(pattern, df)
        pattern.update(sim)
        patterns.append(pattern)

    return patterns


# ==============================================================================
# [9] دمج الاتجاهين
# ==============================================================================
def detect_all_head_shoulders(pivots, df, is_backtest=False,
                               max_gap=50, max_pattern_duration=200):
    normal_patterns = detect_all_head_shoulders_base(
        pivots, df, is_backtest, max_gap, max_pattern_duration
    )
    inverse_patterns = detect_all_inverse_head_shoulders(
        pivots, df, is_backtest, max_gap, max_pattern_duration
    )

    all_patterns = normal_patterns + inverse_patterns
    all_patterns.sort(key=lambda x: x.get("end_pos", -1))
    return all_patterns


# ==============================================================================
# [10] التحليل الحي
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
        max_gap=max_gap, max_pattern_duration=max_pattern_dur
    )

    if not all_patterns:
        default_empty["df"] = df_active
        return default_empty

    latest = all_patterns[-1]
    signal = "STRONG BUY" if latest["bias"] == "Bullish" else "STRONG SELL"

    return {
        "df": df_active, "symbol": symbol or "N/A",
        "signal": signal, "pattern": latest["pattern"],
        "bias": latest["bias"],
        "entry": latest["entry"], "entry_trigger": latest["entry_trigger"],
        "sl": latest["sl"], "tp": latest["tp"],
        "nodes": latest["nodes"], "pattern_nodes": latest["nodes"],
        "neckline_nodes": latest.get("neckline_nodes", []),
        "target_nodes": latest.get("target_nodes", []),
        "all_patterns": all_patterns,
        "match": latest.get("match", 100.0),
        "Result": latest.get("Result", "OPEN"),
        "Entry Date": latest.get("Entry Date"),
        "Exit Date": latest.get("Exit Date"),
        "error": None,
    }


# ==============================================================================
# [10.b] ✅ دالة التشخيص الشاملة
# ==============================================================================
def diagnose_filters(df, interval="5m", symbol=None, sample_size=50):
    diagnostics = {
        "symbol": symbol or "N/A",
        "interval": interval,
        "total_raw_candidates": 0,
        "stages": {},
        "rejection_samples": {},
        "recommendations": [],
        "final_count": 0,
        "error": None,
    }

    if df is None or df.empty:
        diagnostics["error"] = "DataFrame فارغ"
        return diagnostics

    df_calc = df.copy()
    required = ["Open", "High", "Low", "Close"]
    for col in required:
        if col not in df_calc.columns:
            diagnostics["error"] = f"عمود مفقود: {col}"
            return diagnostics
        df_calc[col] = pd.to_numeric(df_calc[col], errors="coerce")

    df_calc = df_calc.dropna(subset=required)
    if len(df_calc) < 30:
        diagnostics["error"] = f"بيانات غير كافية: {len(df_calc)}"
        return diagnostics

    df_calc = calculate_indicators(df_calc)
    df_calc = calculate_zigzag(
        df_calc,
        CONFIG["ZIGZAG_DEPTH"],
        CONFIG["ZIGZAG_BACKSTEP"]
    )

    pivots = get_chronological_pivots(df_calc)

    max_gap = _get_max_gap(interval)
    max_pattern_dur = _get_max_pattern_duration(interval)

    # ─── المرحلة 0: كل الأنماط الخام ───
    raw_candidates = []

    for i in range(len(pivots) - 5):
        p = pivots[i:i + 6]
        types = [x["type"] for x in p]

        if types == ["L", "H", "L", "H", "L", "H"]:
            raw_candidates.append({"pivots": p, "bias": "Bearish"})
        elif types == ["H", "L", "H", "L", "H", "L"]:
            raw_candidates.append({"pivots": p, "bias": "Bullish"})

    diagnostics["total_raw_candidates"] = len(raw_candidates)

    # ─── المرحلة 1: الفلترة الهندسية ───
    geo_passed = []

    for cand in raw_candidates:
        p = cand["pivots"]
        is_bearish = cand["bias"] == "Bearish"

        try:
            if is_bearish:
                l0, h1, l1, h2, l2, h3 = [x["val"] for x in p]
                if h1 <= l0 or l1 <= l0:
                    continue
                if h2 <= h1 or h2 <= h3:
                    continue
                neckline_min = min(l1, l2)
                head_height = h2 - neckline_min
                if head_height <= 0:
                    continue
                if abs(h1 - h3) > (head_height * CONFIG["SHOULDER_DIFF_MAX_RATIO"]):
                    continue
                max_shoulder = max(h1, h3)
                if (h2 - max_shoulder) < (head_height * CONFIG["HEAD_PROPORTION_MIN_RATIO"]):
                    continue
                if abs(l1 - l2) > (head_height * CONFIG["NECKLINE_DIFF_MAX_RATIO"]):
                    continue
            else:
                h0, l1, h1, l2, h2, l3 = [x["val"] for x in p]
                if l2 >= l1 or l2 >= l3:
                    continue
                neckline_max = max(h1, h2)
                head_depth = neckline_max - l2
                if head_depth <= 0:
                    continue
                if abs(l1 - l3) > (head_depth * CONFIG["SHOULDER_DIFF_MAX_RATIO"]):
                    continue
                min_shoulder = min(l1, l3)
                if (min_shoulder - l2) < (head_depth * CONFIG["HEAD_PROPORTION_MIN_RATIO"]):
                    continue
                                if abs(h1 - h2) > (head_depth * CONFIG["NECKLINE_DIFF_MAX_RATIO"]):
                    continue

            geo_passed.append(cand)
        except (ValueError, IndexError, KeyError):
            continue

    diagnostics["stages"]["geometry"] = {
        "before": len(raw_candidates),
        "after": len(geo_passed),
        "rejected": len(raw_candidates) - len(geo_passed),
        "pass_rate": round(len(geo_passed) / max(len(raw_candidates), 1) * 100, 1),
    }

    # ─── المرحلة 2: MAX_PATTERN_DURATION ───
    size_passed = []
    size_rejected = []

    for cand in geo_passed:
        p = cand["pivots"]
        start_pos = p[0]["pos"]
        end_pos = p[5]["pos"]
        pattern_size = end_pos - start_pos

        if pattern_size <= max_pattern_dur:
            size_passed.append(cand)
        else:
            size_rejected.append({
                "size": pattern_size,
                "max_allowed": max_pattern_dur,
                "bias": cand["bias"],
            })

    diagnostics["stages"]["max_pattern_duration"] = {
        "before": len(geo_passed),
        "after": len(size_passed),
        "rejected": len(size_rejected),
        "pass_rate": round(len(size_passed) / max(len(geo_passed), 1) * 100, 1),
        "max_allowed": max_pattern_dur,
    }

    # ─── المرحلة 3: STRICT_TREND ───
    trend_passed = []
    trend_rejected = []

    if CONFIG.get("REQUIRE_STRICT_TREND", True):
        for cand in size_passed:
            p = cand["pivots"]
            idx_end = p[5]["idx"]
            if idx_end not in df_calc.index:
                continue

            row = df_calc.loc[idx_end]
            ema50 = row.get("EMA50", None)
            ema200 = row.get("EMA200", None)
            price = row.get("Close", None)

            if pd.isna(ema50) or pd.isna(ema200) or pd.isna(price):
                continue

            ema50 = float(ema50)
            ema200 = float(ema200)
            price = float(price)
            is_bearish = cand["bias"] == "Bearish"

            if is_bearish:
                ok = price < ema50 < ema200
            else:
                ok = price > ema50 > ema200

            if ok:
                trend_passed.append(cand)
            else:
                trend_rejected.append({
                    "bias": cand["bias"],
                    "price": round(price, 5),
                    "ema50": round(ema50, 5),
                    "ema200": round(ema200, 5),
                    "expected": "< EMA50 < EMA200" if is_bearish else "> EMA50 > EMA200",
                })
    else:
        trend_passed = size_passed

    diagnostics["stages"]["strict_trend"] = {
        "enabled": CONFIG.get("REQUIRE_STRICT_TREND", True),
        "before": len(size_passed),
        "after": len(trend_passed),
        "rejected": len(size_passed) - len(trend_passed),
        "pass_rate": round(len(trend_passed) / max(len(size_passed), 1) * 100, 1),
    }
    if trend_rejected:
        diagnostics["rejection_samples"]["strict_trend"] = trend_rejected[:sample_size]

    # ─── المرحلة 4: RSI ───
    rsi_passed = []
    rsi_rejected = []

    for cand in trend_passed:
        p = cand["pivots"]
        idx_end = p[5]["idx"]
        if idx_end not in df_calc.index:
            continue

        rsi_val = df_calc.loc[idx_end, "RSI"]
        if pd.isna(rsi_val):
            continue
        rsi_val = float(rsi_val)
        is_bearish = cand["bias"] == "Bearish"

        if is_bearish:
            ok = CONFIG["RSI_MIN_BEARISH"] <= rsi_val <= CONFIG["RSI_MAX_BEARISH"]
        else:
            ok = CONFIG["RSI_MIN_BULLISH"] <= rsi_val <= CONFIG["RSI_MAX_BULLISH"]

        if ok:
            rsi_passed.append(cand)
        else:
            rsi_rejected.append({
                "bias": cand["bias"],
                "rsi": round(rsi_val, 1),
            })

    diagnostics["stages"]["rsi"] = {
        "before": len(trend_passed),
        "after": len(rsi_passed),
        "rejected": len(rsi_rejected),
        "pass_rate": round(len(rsi_passed) / max(len(trend_passed), 1) * 100, 1),
    }
    if rsi_rejected:
        diagnostics["rejection_samples"]["rsi"] = rsi_rejected[:sample_size]

    # ─── المرحلة 5: BREAKOUT ───
    breakout_passed = []
    breakout_rejected = []

    for cand in rsi_passed:
        p = cand["pivots"]
        idx_h3 = p[5]["idx"]
        is_bearish = cand["bias"] == "Bearish"

        l1, l2 = p[2]["val"], p[4]["val"]
        neckline = (l1 + l2) / 2.0

        post_h3 = df_calc.loc[idx_h3:]
        if is_bearish:
            breakout = post_h3[post_h3["Close"] < neckline]
        else:
            breakout = post_h3[post_h3["Close"] > neckline]

        if not breakout.empty:
            breakout_passed.append({
                "pivots": p,
                "bias": cand["bias"],
                "breakout_idx": breakout.index[0],
                "breakout_price": float(breakout["Close"].iloc[0]),
                "neckline": neckline,
            })
        else:
            breakout_rejected.append({
                "bias": cand["bias"],
                "neckline": round(neckline, 5),
            })

    diagnostics["stages"]["breakout"] = {
        "before": len(rsi_passed),
        "after": len(breakout_passed),
        "rejected": len(breakout_rejected),
        "pass_rate": round(len(breakout_passed) / max(len(rsi_passed), 1) * 100, 1),
    }

    # ─── المرحلة 6: BREAKOUT_CONFIRM ───
    confirm_passed = []
    confirm_rejected = []

    for cand in breakout_passed:
        neckline = cand["neckline"]
        breakout_price = cand["breakout_price"]
        is_bearish = cand["bias"] == "Bearish"
        min_pct = CONFIG.get("BREAKOUT_MIN_PCT", 0.001)

        if is_bearish:
            ok = breakout_price <= neckline * (1 - min_pct)
        else:
            ok = breakout_price >= neckline * (1 + min_pct)

        if ok:
            confirm_passed.append(cand)
        else:
            confirm_rejected.append({
                "bias": cand["bias"],
                "neckline": round(neckline, 5),
                "breakout_price": round(breakout_price, 5),
            })

    diagnostics["stages"]["breakout_confirm"] = {
        "before": len(breakout_passed),
        "after": len(confirm_passed),
        "rejected": len(confirm_rejected),
        "pass_rate": round(len(confirm_passed) / max(len(breakout_passed), 1) * 100, 1),
    }
    if confirm_rejected:
        diagnostics["rejection_samples"]["breakout_confirm"] = confirm_rejected[:sample_size]

    # ─── المرحلة 7: MAX_GAP ───
    gap_passed = []
    gap_rejected = []

    for cand in confirm_passed:
        p = cand["pivots"]
        h3_pos = p[5]["pos"]
        breakout_idx = cand["breakout_idx"]

        if breakout_idx not in df_calc.index:
            continue
        breakout_pos = df_calc.index.get_loc(breakout_idx)
        gap_size = breakout_pos - h3_pos

        if gap_size <= max_gap:
            cand["gap_size"] = gap_size
            gap_passed.append(cand)
        else:
            gap_rejected.append({
                "bias": cand["bias"],
                "gap_size": gap_size,
                "max_allowed": max_gap,
            })

    diagnostics["stages"]["max_gap"] = {
        "before": len(confirm_passed),
        "after": len(gap_passed),
        "rejected": len(gap_rejected),
        "pass_rate": round(len(gap_passed) / max(len(confirm_passed), 1) * 100, 1),
        "max_allowed": max_gap,
    }

    # ─── النتيجة النهائية ───
    diagnostics["final_count"] = len(gap_passed)

    # ─── الاقتراحات التلقائية ───
    rec = diagnostics["recommendations"]
    for stage_name, stage_data in diagnostics["stages"].items():
        if stage_name == "geometry":
            continue
        pass_rate = stage_data.get("pass_rate", 100)
        before = stage_data.get("before", 0)
        rejected = stage_data.get("rejected", 0)

        if before > 0 and pass_rate < 20:
            rec.append({
                "filter": stage_name,
                "severity": "🔴 حرج",
                "pass_rate": pass_rate,
                "rejected": rejected,
                "message": f"الفلتر '{stage_name}' يرفض {100 - pass_rate:.0f}% — صارم جداً",
            })
        elif before > 0 and pass_rate < 50:
            rec.append({
                "filter": stage_name,
                "severity": "🟡 متوسط",
                "pass_rate": pass_rate,
                "rejected": rejected,
                "message": f"الفلتر '{stage_name}' يرفض {100 - pass_rate:.0f}% — يستحق المراجعة",
            })

    return diagnostics


# ==============================================================================
# [11] الباكتيست
# ==============================================================================
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
    all_patterns = detect_all_head_shoulders(
        pivots, df, is_backtest=True,
        max_gap=max_gap, max_pattern_duration=max_pattern_dur
    )

    trades = []
    for p in all_patterns:
        trade = {
            "Symbol": symbol or "N/A",
            "Pattern": p["pattern"],
            "pattern": p["pattern"],
            "Bias": p["bias"],
            "Result": p.get("Result", "OPEN"),
            "Head Result": p.get("Head Result", "OPEN"),
            "Entry": p["entry"],
            "SL": p["sl"],
            "TP": p["tp"],
            "Entry Date": p.get("Entry Date"),
            "Exit Date": p.get("Exit Date"),
            "time": p.get("Entry Date"),
            "close_time": p.get("Exit Date"),
            "Max Reach %": p.get("Max Reach %", 0.0),
            "SL Safety %": p.get("SL Safety %", 0.0),
            "Entry Conditions": p.get("Entry Conditions", ""),
            "nodes": p["nodes"],
            "candles_to_exit": p.get("candles_to_exit", 0),
            "progress_ratio": p.get("progress_ratio", 0.0),
            "neckline_end_idx": p["neckline_end_idx"],
            "Pattern Duration": p.get("Pattern Duration", 0),
            "Timeout Used": p.get("Timeout Used", 0),
        }
        trades.append(trade)

    return trades


# ==============================================================================
# [12] منفذ الاختبار
# ==============================================================================
if __name__ == "__main__":
    print("ENGINE.PY - Head & Shoulders Detector")
    print("Filters:")
    print("  1. max_gap (H3 to Breakout)")
    print("  2. max_pattern_duration (L0 to H3)")
    print("  3. Time Stop = max(300, pattern_duration x 3)")
    print("  4. Strict Trend: Price vs EMA50 vs EMA200")
    print("  5. RSI")
    print("  6. Breakout confirm")
    print("Functions:")
    print("  - run_full_analysis(df, interval, symbol)")
    print("  - backtest_strategy(df, interval, symbol)")
    print("  - diagnose_filters(df, interval, symbol)  <-- جديد")
