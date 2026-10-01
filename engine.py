# -*- coding: utf-8 -*-
"""
ENGINE.PY - Head & Shoulders Detector
Merged: v4.6 pattern logic + strict filters + diagnostics + breakeven
UPDATED: Realistic entry (end_val) + Equal Shoulders/Neckline + Correct RSI
"""
import pandas as pd
import numpy as np

CONFIG = {
    "ZIGZAG_DEPTH": 8,
    "ZIGZAG_BACKSTEP": 3,
    "MIN_WAVE_CANDLES": 3,
    "SHOULDER_DIFF_MAX_RATIO": 0.10,
    "HEAD_PROPORTION_MIN_RATIO": 0.20,
    "NECKLINE_DIFF_MAX_RATIO": 0.10,
    "LIVE_MAX_BREAKOUT_CANDLES": 15,
    "RSI_MIN_BEARISH": 25.0,
    "RSI_MAX_BEARISH": 50.0,
    "RSI_MIN_BULLISH": 35.0,
    "RSI_MAX_BULLISH": 75.0,
    "EMA_FAST_SPAN": 50,
    "EMA_SLOW_SPAN": 200,
    "REQUIRE_STRICT_TREND": False,
    "BREAKOUT_MIN_PCT": 0.0002,
    "REQUIRE_VOLUME_BREAKOUT": False,
    "VOLUME_FACTOR": 1.2,
    "VOLUME_MA_PERIOD": 20,
    "BREAKEVEN_ACTIVATION_PCT": 0.50,
}

TIMEOUT_STATISTICAL_FLOOR = 700
TIMEOUT_DURATION_MULTIPLIER = 3


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


def simulate_trade_outcome(pattern, df):
    """محاكاة نتيجة الصفقة مع Break-even Stop"""
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

    BE_ACTIVATION = CONFIG.get("BREAKEVEN_ACTIVATION_PCT", 0.50)
    original_sl = sl
    breakeven_activated = False

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

        if (not breakeven_activated) and total_tp_dist > 0:
            if bias == "Bearish":
                if low <= entry - BE_ACTIVATION * total_tp_dist:
                    sl = entry
                    breakeven_activated = True
                    stats["Breakeven Activated"] = True
            else:
                if high >= entry + BE_ACTIVATION * total_tp_dist:
                    sl = entry
                    breakeven_activated = True
                    stats["Breakeven Activated"] = True

        if bias == "Bearish":
            hit_sl = high >= sl
            hit_tp = low <= tp
        else:
            hit_sl = low <= sl
            hit_tp = high >= tp

        if hit_sl:
            if breakeven_activated:
                stats["Result"] = "BREAKEVEN"
                stats["Head Result"] = "BREAKEVEN"
                stats["Breakeven Exit"] = True
            else:
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
            if breakeven_activated:
                stats["Result"] = "BREAKEVEN"
                stats["Head Result"] = "BREAKEVEN"
                stats["Breakeven Exit"] = True
                stats["exit_price"] = entry
            else:
                stats["Result"] = "TIMEOUT"
                stats["Head Result"] = "TIMEOUT"
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
            return price < ema50 and price < ema200
        else:
            return price > ema50 and price > ema200

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

        entry = float(end_val)
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
            "Entry Conditions": "Strict Trend + RSI(25-50) + Breakout + Equal Shoulders/Neckline",
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

        entry = float(end_val)
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
            "Entry Conditions": "Strict Trend + RSI(35-75) + Breakout + Equal Shoulders/Neckline",
        }

        sim = simulate_trade_outcome(pattern, df)
        pattern.update(sim)
        patterns.append(pattern)

    return patterns


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
            "Breakeven Activated": p.get("Breakeven Activated", False),
            "Breakeven Exit": p.get("Breakeven Exit", False),
        }
        trades.append(trade)

    return trades


# ==============================================================================
# 🔬 DIAGNOSE FILTERS — تقرير تشخيصي ذكي (بدون Streamlit)
# ==============================================================================
def diagnose_filters(df, interval="1h", symbol=None):
    """
    تقرير تشخيصي كامل:
      - أي فلتر يرفض أكثر
      - عينات من الأنماط المرفوضة
      - توصيات ذكية
      - تحليل كل صفقة: نجاح / فشل / لا مفر منه
    """
    result = {
        "total_raw_candidates": 0,
        "final_count": 0,
        "stages": {},
        "recommendations": [],
        "rejection_samples": {},
        "error": None,
        "trade_analysis": [],
        "smart_diagnosis": {},
    }

    if df is None or df.empty:
        result["error"] = "بيانات فارغة"
        return result

    try:
        df = df.copy()
        df = calculate_indicators(df)
        df = calculate_zigzag(df, CONFIG["ZIGZAG_DEPTH"], CONFIG["ZIGZAG_BACKSTEP"])
        pivots = get_chronological_pivots(df)

        if len(pivots) < 6:
            result["error"] = f"عدد القمم/القيعان غير كافٍ ({len(pivots)})"
            return result

        # ─── المرشحون الخام ───
        raw_candidates = []
        for i in range(len(pivots) - 5):
            p = pivots[i:i + 6]
            if [x["type"] for x in p] == ["L", "H", "L", "H", "L", "H"]:
                raw_candidates.append({"type": "Bearish", "pivots": p})
            elif [x["type"] for x in p] == ["H", "L", "H", "L", "H", "L"]:
                raw_candidates.append({"type": "Bullish", "pivots": p})

        result["total_raw_candidates"] = len(raw_candidates)

        # ─── تشغيل الفلاتر مرحلة بمرحلة ───
        validator = PatternValidatorPipeline(df)
        stages = {
            "1. Time Filter (MIN_WAVE_CANDLES)": {"before": 0, "after": 0, "rejected": []},
            "2. Strict Trend (EMA50/200)": {"before": 0, "after": 0, "rejected": []},
            "3. RSI Filter": {"before": 0, "after": 0, "rejected": []},
            "4. Breakout + Confirm": {"before": 0, "after": 0, "rejected": []},
            "5. Volume Filter": {"before": 0, "after": 0, "rejected": []},
        }

        for cand in raw_candidates:
            p = cand["pivots"]
            bias = cand["type"]

            # 1) Time
            stages["1. Time Filter (MIN_WAVE_CANDLES)"]["before"] += 1
            if not validator.time_filter(p):
                stages["1. Time Filter (MIN_WAVE_CANDLES)"]["rejected"].append({
                    "bias": bias, "head_val": p[3]["val"],
                    "reason": "موجات قصيرة جداً"
                })
                continue
            stages["1. Time Filter (MIN_WAVE_CANDLES)"]["after"] += 1

            # 2) Trend
            stages["2. Strict Trend (EMA50/200)"]["before"] += 1
            if not validator.strict_trend_filter(p):
                stages["2. Strict Trend (EMA50/200)"]["rejected"].append({
                    "bias": bias, "head_val": p[3]["val"],
                    "reason": "السعر ليس في الاتجاه الصحيح مقابل EMA50/EMA200"
                })
                continue
            stages["2. Strict Trend (EMA50/200)"]["after"] += 1

            # 3) RSI
            stages["3. RSI Filter"]["before"] += 1
            if not validator.indicator_filter(p):
                idx_end = p[5]["idx"]
                rsi_val = float(df.loc[idx_end, "RSI"]) if idx_end in df.index else None
                stages["3. RSI Filter"]["rejected"].append({
                    "bias": bias, "head_val": p[3]["val"],
                    "reason": f"RSI={round(rsi_val,1) if rsi_val else 'N/A'} خارج النطاق"
                })
                continue
            stages["3. RSI Filter"]["after"] += 1

            # 4) Breakout
            stages["4. Breakout + Confirm"]["before"] += 1
            br = validator.breakout_filter(p)
            if br is None:
                stages["4. Breakout + Confirm"]["rejected"].append({
                    "bias": bias, "head_val": p[3]["val"],
                    "reason": "لم يحدث كسر لخط العنق"
                })
                continue
            br_idx, br_price = br
            if not validator.breakout_confirm_filter(p, br_price):
                stages["4. Breakout + Confirm"]["rejected"].append({
                    "bias": bias, "head_val": p[3]["val"],
                    "reason": "كسر ضعيف (< BREAKOUT_MIN_PCT)"
                })
                continue
            stages["4. Breakout + Confirm"]["after"] += 1

            # 5) Volume
            stages["5. Volume Filter"]["before"] += 1
            if not validator.volume_filter(br_idx):
                stages["5. Volume Filter"]["rejected"].append({
                    "bias": bias, "head_val": p[3]["val"],
                    "reason": "حجم الكسر أقل من المتوسط"
                })
                continue
            stages["5. Volume Filter"]["after"] += 1

        # ─── تجميع نتائج المراحل ───
        for name, data in stages.items():
            before = data["before"]
            after = data["after"]
            result["stages"][name] = {
                "before": before,
                "after": after,
                "rejected": before - after,
                "pass_rate": f"{round(after / max(before, 1) * 100, 1)}%" if before else "0%",
            }
            if data["rejected"]:
                result["rejection_samples"][name] = data["rejected"][:5]

        # ─── التشغيل النهائي ───
        max_gap = _get_max_gap(interval)
        max_dur = _get_max_pattern_duration(interval)
        patterns = detect_all_head_shoulders(
            pivots, df, is_backtest=True,
            max_gap=max_gap, max_pattern_duration=max_dur
        )
        result["final_count"] = len(patterns)

        # ─── تحليل كل صفقة ───
        result["trade_analysis"] = _analyze_trades(patterns, df)

        # ─── التشخيص الذكي الشامل ───
        result["smart_diagnosis"] = _build_smart_diagnosis(
            result, patterns, df, raw_candidates
        )

        # ─── توصيات عامة ───
        result["recommendations"] = _build_recommendations(result)

    except Exception as e:
        import traceback
        result["error"] = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"

    return result


def _analyze_trades(patterns, df):
    analysis = []
    for i, pat in enumerate(patterns):
        entry = float(pat["entry"])
        sl = float(pat["sl"])
        tp = float(pat["tp"])
        bias = pat["bias"]
        result_status = pat.get("Result", "OPEN")

        max_reach = pat.get("Max Reach %", 0.0)
        sl_safety = pat.get("SL Safety %", 100.0)

        failure_category = None
        failure_reason = None
        is_unavoidable = False
        recommendation = None

        if result_status == "WIN":
            failure_category = "success"
            failure_reason = f"✅ تحقق الهدف (وصل السعر إلى {max_reach}% من الطريق)"
            recommendation = "استمر بنفس الإعدادات"

        elif result_status == "LOSS":
            if max_reach < 20:
                failure_category = "immediate_rejection"
                failure_reason = (
                    f"❌ رفض فوري: السعر لم يتحرك سوى {max_reach}% "
                    f"ثم انعكس مباشرة إلى SL (Fake Breakout)."
                )
                recommendation = "ارفع BREAKOUT_MIN_PCT إلى 0.0005 + ألزم فلتر الحجم"
                is_unavoidable = False

            elif max_reach >= 70:
                failure_category = "late_reversal"
                failure_reason = (
                    f"❌ انعكاس متأخر: السعر وصل إلى {max_reach}% "
                    f"ثم انعكس إلى SL (إحصائي طبيعي)."
                )
                recommendation = "Break-even مُفعّل — لا تغيير مطلوب"
                is_unavoidable = True

            elif max_reach >= 40:
                failure_category = "mid_reversal"
                failure_reason = (
                    f"⚠️ انعكاس متوسط: السعر وصل إلى {max_reach}% ثم ارتد."
                )
                recommendation = "استخدم Trailing Stop بدل TP ثابت"
                is_unavoidable = True

            else:
                failure_category = "early_reversal"
                failure_reason = (
                    f"❌ انعكاس مبكر: السعر وصل إلى {max_reach}% فقط."
                )
                recommendation = "شدّد فلتر Trend + انتظر إعادة اختبار خط العنق"
                is_unavoidable = False

        elif result_status == "BREAKEVEN":
            failure_category = "breakeven"
            failure_reason = (
                f"⚖️ تعادل: تم تفعيل Break-even عند 50% "
                f"(وصل السعر إلى {max_reach}% قبل الانعكاس)."
            )
            recommendation = "أداء ممتاز — تم حماية رأس المال"
            is_unavoidable = True

        elif result_status == "TIMEOUT":
            failure_category = "timeout"
            failure_reason = (
                f"⏰ انتهاء الوقت: لم يصل للهدف ولا لـ SL خلال "
                f"{pat.get('Timeout Used', 0)} شمعة (وصل إلى {max_reach}%)."
            )
            recommendation = "زد TIMEOUT_DURATION_MULTIPLIER أو تصفية يدوية"
            is_unavoidable = False

        else:
            failure_category = "open"
            failure_reason = "⏳ صفقة مفتوحة — لم تُحسم بعد"
            recommendation = None

        risk = abs(entry - sl)
        reward = abs(tp - entry)
        rr_ratio = round(reward / risk, 2) if risk > 0 else 0

        analysis.append({
            "trade_num": i + 1,
            "bias": bias,
            "result": result_status,
            "category": failure_category,
            "reason": failure_reason,
            "is_unavoidable": is_unavoidable,
            "recommendation": recommendation,
            "entry": entry,
            "sl": sl,
            "tp": tp,
            "rr_ratio": rr_ratio,
            "max_reach_%": max_reach,
            "sl_safety_%": sl_safety,
            "breakeven_activated": pat.get("Breakeven Activated", False),
            "candles_to_exit": pat.get("candles_to_exit", 0),
            "pattern_duration": pat.get("Pattern Duration", 0),
        })

    return analysis


def _build_smart_diagnosis(result, patterns, df, raw_candidates):
    diag = {
        "verdict": "",
        "win_breakdown": {},
        "loss_breakdown": {},
        "unavoidable_losses": 0,
        "avoidable_losses": 0,
        "top_blocker": None,
        "action_plan": [],
    }

    trades = result.get("trade_analysis", [])
    if not trades:
        diag["verdict"] = "لا توجد صفقات لتحليلها"
        return diag

    wins = [t for t in trades if t["result"] == "WIN"]
    losses = [t for t in trades if t["result"] == "LOSS"]
    breakevens = [t for t in trades if t["result"] == "BREAKEVEN"]
    timeouts = [t for t in trades if t["result"] == "TIMEOUT"]

    closed = len(wins) + len(losses)
    win_rate = round(len(wins) / closed * 100, 1) if closed else 0

    unavoidable = [t for t in losses if t["is_unavoidable"]]
    avoidable = [t for t in losses if not t["is_unavoidable"]]

    diag["unavoidable_losses"] = len(unavoidable)
    diag["avoidable_losses"] = len(avoidable)

    diag["win_breakdown"] = {
        "total_wins": len(wins),
        "win_rate_%": win_rate,
        "avg_max_reach": round(sum(t["max_reach_%"] for t in wins) / max(len(wins), 1), 1),
    }

    diag["loss_breakdown"] = {
        "immediate_rejection": len([t for t in losses if t["category"] == "immediate_rejection"]),
        "early_reversal": len([t for t in losses if t["category"] == "early_reversal"]),
        "mid_reversal": len([t for t in losses if t["category"] == "mid_reversal"]),
        "late_reversal": len([t for t in losses if t["category"] == "late_reversal"]),
        "unavoidable": len(unavoidable),
        "avoidable": len(avoidable),
    }

    if win_rate >= 65:
        diag["verdict"] = f"🟢 ممتاز — نسبة نجاح {win_rate}% ({len(wins)}/{closed})"
    elif win_rate >= 50:
        diag["verdict"] = f"🟡 مقبول — نسبة نجاح {win_rate}% — يحتاج تحسين"
    else:
        diag["verdict"] = f"🔴 ضعيف — نسبة نجاح {win_rate}% — يحتاج مراجعة عاجلة"

    blockers = []
    for name, data in result["stages"].items():
        if data["rejected"] > 0:
            blockers.append((name, data["rejected"]))
    if blockers:
        top = max(blockers, key=lambda x: x[1])
        diag["top_blocker"] = {"name": top[0], "rejected": top[1]}

    plan = []
    if diag["loss_breakdown"]["immediate_rejection"] >= 2:
        plan.append("🔴 رفض فوري متكرر → ارفع BREAKOUT_MIN_PCT وألزم فلتر الحجم")
    if diag["loss_breakdown"]["early_reversal"] >= 2:
        plan.append("🟡 انعكاس مبكر متكرر → شدّد فلتر EMA")
    if diag["loss_breakdown"]["mid_reversal"] >= 2:
        plan.append("🟡 انعكاس متوسط → فعّل Trailing Stop عند 40% من الهدف")
    if len(unavoidable) > 0:
        plan.append(f"⚪ {len(unavoidable)} خسارة لا مفر منها إحصائياً — لا تحاول تجنبها")
    if len(breakevens) > len(losses) / 2:
        plan.append("🟢 Break-even يعمل بكفاءة — يستحق الإبقاء")
    if not plan:
        plan.append("✅ الأداء متوازن — لا توجد توصيات عاجلة")

    diag["action_plan"] = plan
    return diag


def _build_recommendations(result):
    recs = []
    total_raw = result["total_raw_candidates"]
    final = result["final_count"]
    acceptance = (final / total_raw * 100) if total_raw else 0

    if acceptance < 5:
        recs.append({
            "severity": "حرج",
            "message": f"نسبة القبول منخفضة جداً ({round(acceptance,1)}%) — الفلاتر صارمة أكثر من اللازم"
        })
    elif acceptance < 15:
        recs.append({
            "severity": "متوسط",
            "message": f"نسبة القبول منخفضة ({round(acceptance,1)}%) — قد تحتاج تخفيف فلتر"
        })

    for name, data in result["stages"].items():
        if data["before"] > 0:
            reject_rate = data["rejected"] / data["before"] * 100
            if reject_rate > 70:
                recs.append({
                    "severity": "حرج",
                    "message": f"الفلتر '{name}' يرفض {round(reject_rate,1)}% — أهم عائق"
                })
            elif reject_rate > 50:
                recs.append({
                    "severity": "متوسط",
                    "message": f"الفلتر '{name}' يرفض {round(reject_rate,1)}% — يستحق مراجعة"
                })

    return recs


if __name__ == "__main__":
    print("ENGINE.PY - Head & Shoulders Detector")
    print("Filters:")
    print("  1. max_gap (H3 to Breakout)")
    print("  2. max_pattern_duration (L0 to H3)")
    print("  3. Time Stop = max(300, pattern_duration x 3)")
    print("  4. Strict Trend: Price vs EMA50 vs EMA200")
    print("  5. RSI Bearish: 25-50 | RSI Bullish: 35-75")
    print("  6. Breakout confirm")
    print("  7. Break-even Stop: SL to Entry at 50% of TP")
    print("  8. Equal Shoulders (10%) + Equal Neckline (10%)")
    print("Functions:")
    print("  - run_full_analysis(df, interval, symbol)")
    print("  - backtest_strategy(df, interval, symbol)")
    print("  - diagnose_filters(df, interval, symbol)")
