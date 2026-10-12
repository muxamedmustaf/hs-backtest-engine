# -*- coding: utf-8 -*-
"""
ENGINE.PY — S/R Horizontal Breakout Strategy (v3)
==================================================
- Detect S/R levels from swing highs/lows over the last N days (default 14).
- A level is "strong" if price respected it >= MIN_TOUCHES times.
- Signal is fired ONLY after a candle CLOSES beyond the level (with buffer).
- SL just beyond the broken level, TP >= 1:2 (2× risk), optionally extended
  to the next opposing S/R zone.
"""
import pandas as pd
import numpy as np


CONFIG = {
    "ZIGZAG_DEPTH": 8,
    "ZIGZAG_BACKSTEP": 4,
    # ── S/R level detection ──────────────────────────────────────────────
    "LOOKBACK_DAYS": 14,             # сколько days of pivots define the levels
    "LEVEL_TOLERANCE_PCT": 0.20,     # pivots within this % cluster together
    "MIN_TOUCHES": 2,                # how many times price must respect a level
    "MAX_LOOKBACK_BARS": 500,        # hard cap for perf
    # ── Breakout confirmation ────────────────────────────────────────────
    "BREAKOUT_BUFFER_PCT": 0.03,     # close must be >= level*(1+buffer)
    "MIN_BREAKOUT_BODY_PCT": 0.05,   # candle body as % of price
    # ── SL / TP ──────────────────────────────────────────────────────────
    "SL_BUFFER_PCT": 0.10,           # SL sits this % beyond the broken level
    "MIN_RR": 2.0,                   # target the next S/R if >= 1:2, else 1:2
    # ── Filters ──────────────────────────────────────────────────────────
    "MIN_BARS_BETWEEN": 5,           # min bars between two signals
    "MAX_TIMEOUT_BARS": 200,
    "VOLUME_MA_PERIOD": 20,
    "MIN_BARS_REQUIRED": 60,
}

TIMEOUT_STATISTICAL_FLOOR = 200
TIMEOUT_DURATION_MULTIPLIER = 3

REASON_MAP = {
    "immediate_rejection": {"reason": "رفض فوري.", "action": "انتظر.", "prevention": "—"},
    "early_reversal":      {"reason": "انعكاس مبكر.", "action": "SL للتعادل.", "prevention": "Trailing."},
    "mid_reversal":        {"reason": "انعكاس متوسط.", "action": "خروج 50%.", "prevention": "TP جزئي."},
    "late_reversal":       {"reason": "انعكاس متأخر.", "action": "Trailing.", "prevention": "راقب."},
    "timeout":             {"reason": "انتهى الوقت.", "action": "أغلق.", "prevention": "ADX."},
    "breakeven":           {"reason": "تعادل.", "action": "—", "prevention": "—"},
    "success":             {"reason": "وصل الهدف.", "action": "كرر.", "prevention": "—"},
    "open":                {"reason": "مفتوحة.", "action": "راقب.", "prevention": "—"},
}


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════
def _get_max_gap(interval):
    return {"1m": 120, "5m": 50, "15m": 30, "30m": 25, "1h": 20,
            "4h": 15, "1d": 10}.get(interval, 50)


def _get_max_pattern_duration(interval):
    return {"1m": 600, "5m": 200, "15m": 150, "30m": 120, "1h": 100,
            "4h": 80, "1d": 60}.get(interval, 200)


def _lookback_bars(interval):
    """Bars that approximate CONFIG['LOOKBACK_DAYS'] trading days for the TF."""
    bars_per_day = {
        "1m": 1440, "2m": 720, "3m": 480, "4m": 360, "5m": 288, "10m": 144,
        "15m": 96, "30m": 48, "45m": 32, "1h": 24, "2h": 12, "3h": 8,
        "4h": 6, "6h": 4, "8h": 3, "12h": 2, "1d": 1, "2d": 0.5, "3d": 0.33,
        "1wk": 0.2, "1mo": 0.05,
    }
    bpd = bars_per_day.get(interval, 24)
    bars = int(bpd * CONFIG["LOOKBACK_DAYS"])
    return min(max(bars, 20), CONFIG["MAX_LOOKBACK_BARS"])


# ══════════════════════════════════════════════════════════════════════════════
# 🛠️ INDICATORS
# ══════════════════════════════════════════════════════════════════════════════
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


def calculate_zigzag(df, depth=8, backstep=4):
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


# ══════════════════════════════════════════════════════════════════════════════
# 📐 S/R LEVEL CLUSTERING
# ══════════════════════════════════════════════════════════════════════════════
def cluster_levels(pivots, tolerance):
    """
    Group pivots whose prices lie within `tolerance` (fraction).
    Returns list of dicts:
        {price, touches, first_pos, last_pos, values}
    """
    if not pivots:
        return []
    sorted_p = sorted(pivots, key=lambda p: p["val"])
    levels = []
    for p in sorted_p:
        merged = False
        for lvl in levels:
            if abs(p["val"] - lvl["price"]) / max(lvl["price"], 1e-9) <= tolerance:
                lvl["values"].append(p["val"])
                lvl["price"] = float(np.mean(lvl["values"]))
                lvl["touches"] += 1
                lvl["first_pos"] = min(lvl["first_pos"], p["pos"])
                lvl["last_pos"]  = max(lvl["last_pos"],  p["pos"])
                merged = True
                break
        if not merged:
            levels.append({
                "price":     p["val"],
                "values":    [p["val"]],
                "touches":   1,
                "first_pos": p["pos"],
                "last_pos":  p["pos"],
            })
    return levels


# ══════════════════════════════════════════════════════════════════════════════
# 🎯 MAIN DETECTOR — S/R CLOSE-BREAKOUT
# ══════════════════════════════════════════════════════════════════════════════
def detect_all_patterns(df, interval="1h", symbol=None, **kwargs):
    if df is None or df.empty or len(df) < CONFIG["MIN_BARS_REQUIRED"]:
        return []

    df = df.copy()
    for c in ["Open", "High", "Low", "Close"]:
        if c not in df.columns:
            return []
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["Open", "High", "Low", "Close"])
    if len(df) < CONFIG["MIN_BARS_REQUIRED"]:
        return []

    df = calculate_indicators(df)
    df = calculate_zigzag(df, CONFIG["ZIGZAG_DEPTH"], CONFIG["ZIGZAG_BACKSTEP"])
    pivots = get_chronological_pivots(df)
    if len(pivots) < 2:
        return []

    lookback  = _lookback_bars(interval)
    backstep  = CONFIG["ZIGZAG_BACKSTEP"]
    tolerance = CONFIG["LEVEL_TOLERANCE_PCT"] / 100.0
    buf       = CONFIG["BREAKOUT_BUFFER_PCT"] / 100.0

    n = len(df)
    patterns = []
    last_signal_pos = -10**9
    broken_prices = []   # avoid re-signaling the same zone

    for i in range(CONFIG["MIN_BARS_REQUIRED"], n):
        # ── active pivots (confirmed & within lookback window) ──────────
        active = [p for p in pivots
                  if (p["pos"] + backstep) <= i and (i - p["pos"]) <= lookback]
        if len(active) < 2:
            continue

        levels = cluster_levels(active, tolerance)
        if not levels:
            continue

        candle     = df.iloc[i]
        prev       = df.iloc[i - 1]
        close      = float(candle["Close"])
        open_      = float(candle["Open"])
        prev_close = float(prev["Close"])

        # candle body filter
        body_pct = abs(close - open_) / max(close, 1e-9) * 100
        if body_pct < CONFIG["MIN_BREAKOUT_BODY_PCT"]:
            continue

        # prefer strongest level
        levels.sort(key=lambda l: -l["touches"])

        for lvl in levels:
            if lvl["touches"] < CONFIG["MIN_TOUCHES"]:
                continue
            price = lvl["price"]

            # skip if we already broke this zone
            if any(abs(price - bp) / max(price, 1e-9) < tolerance for bp in broken_prices):
                continue

            up_thr   = price * (1 + buf)
            down_thr = price * (1 - buf)

            # ── Bullish close-breakout ─────────────────────────────────
            if prev_close <= up_thr and close > up_thr and close > open_:
                if i - last_signal_pos < CONFIG["MIN_BARS_BETWEEN"]:
                    continue
                pattern = _build_pattern(df, i, lvl, levels, "BUY", interval)
                if pattern:
                    patterns.append(pattern)
                    last_signal_pos = i
                    broken_prices.append(price)
                    break

            # ── Bearish close-breakout ─────────────────────────────────
            elif prev_close >= down_thr and close < down_thr and close < open_:
                if i - last_signal_pos < CONFIG["MIN_BARS_BETWEEN"]:
                    continue
                pattern = _build_pattern(df, i, lvl, levels, "SELL", interval)
                if pattern:
                    patterns.append(pattern)
                    last_signal_pos = i
                    broken_prices.append(price)
                    break

    return patterns


def _build_pattern(df, idx, lvl, all_levels, direction, interval):
    candle = df.iloc[idx]
    entry  = float(candle["Close"])
    level_price = float(lvl["price"])
    sl_buf = CONFIG["SL_BUFFER_PCT"] / 100.0

    # ── SL: just beyond the broken level ─────────────────────────────────
    if direction == "BUY":
        sl = level_price * (1 - sl_buf)
        if sl >= entry:
            return None
        risk = entry - sl
        min_rr_tp = entry + CONFIG["MIN_RR"] * risk
    else:
        sl = level_price * (1 + sl_buf)
        if sl <= entry:
            return None
        risk = sl - entry
        min_rr_tp = entry - CONFIG["MIN_RR"] * risk

    if risk <= 0:
        return None

    # ── TP: prefer next opposing S/R zone if it satisfies min R:R ────────
    tp = min_rr_tp
    if direction == "BUY":
        candidates = [l["price"] for l in all_levels
                      if l["price"] >= min_rr_tp and l["price"] > entry]
        if candidates:
            tp = min(candidates)
    else:
        candidates = [l["price"] for l in all_levels
                      if l["price"] <= min_rr_tp and l["price"] < entry]
        if candidates:
            tp = max(candidates)

    rr = abs(tp - entry) / risk
    if rr < CONFIG["MIN_RR"] - 0.05:
        return None

    bias = "Bullish" if direction == "BUY" else "Bearish"
    body_pct = abs(float(candle["Close"]) - float(candle["Open"])) / max(entry, 1e-9) * 100

    # ── chart nodes (level line + breakout) ──────────────────────────────
    nodes = [
        (df.index[lvl["first_pos"]], level_price),
        (df.index[lvl["last_pos"]],  level_price),
        (df.index[max(0, idx - 1)],  level_price),
        (df.index[idx],              entry),
    ]

    # thin horizontal "box" so the app's Consolidation rect renders the level
    box_high = level_price * (1 + CONFIG["LEVEL_TOLERANCE_PCT"] / 100.0)
    box_low  = level_price * (1 - CONFIG["LEVEL_TOLERANCE_PCT"] / 100.0)

    pattern = {
        "name": "S/R Breakout",
        "pattern": f"S/R {direction} Breakout ({lvl['touches']} touches)",
        "bias": bias,
        "direction": direction,
        "match": float(min(100, 50 + lvl["touches"] * 10)),
        "entry": round(entry, 5),
        "entry_trigger": round(entry, 5),
        "sl": round(sl, 5),
        "tp": round(tp, 5),
        "SL": round(sl, 5),
        "TP": round(tp, 5),
        "Entry": round(entry, 5),
        "nodes": nodes,
        "consolidation_box": {
            "x_start": lvl["first_pos"],
            "x_end":   idx,
            "high":    round(box_high, 5),
            "low":     round(box_low, 5),
        },
        "level_price":  round(level_price, 5),
        "level_touches": lvl["touches"],
        "neckline_start_idx": df.index[lvl["first_pos"]],
        "neckline_end_idx":   df.index[idx],
        "end_pos": idx,
        "Entry Conditions": f"S/R level ({lvl['touches']} touches) broken by close",
        "consol_high": round(box_high, 5),
        "consol_low":  round(box_low, 5),
        "consol_bars": int(lvl["last_pos"] - lvl["first_pos"] + 1),
        "consol_range_pct": round((box_high - box_low) / max(level_price, 1e-9) * 100, 3),
        "consol_stability_pct": 100.0,
        "breakout_body_pct": round(body_pct, 3),
    }

    pattern.update(simulate_trade_outcome(pattern, df))
    return pattern


# ══════════════════════════════════════════════════════════════════════════════
# 🧪 SIMULATE
# ══════════════════════════════════════════════════════════════════════════════
def simulate_trade_outcome(pattern, df):
    bias    = pattern["bias"]
    entry   = float(pattern["entry"])
    sl      = float(pattern["sl"])
    tp      = float(pattern["tp"])
    end_idx = pattern["neckline_end_idx"]

    stats = {
        "Result": "OPEN", "Head Result": "OPEN",
        "progress_ratio": 0.0, "candles_to_exit": 0,
        "exit_idx": None, "exit_price": None,
        "Entry Date": None, "Exit Date": None,
        "Max Reach %": 0.0, "SL Safety %": 0.0,
        "Breakeven Activated": False, "Breakeven Exit": False,
        "Trailing Stage": 0,
        "Initial SL": sl, "Final SL": sl,
        "Loss Category": None,
        "Pattern Duration": 50,
        "Timeout Used": CONFIG["MAX_TIMEOUT_BARS"],
    }

    if end_idx not in df.index:
        return stats

    post = df.loc[end_idx:]
    if len(post) <= 1:
        return stats

    stats["Entry Date"] = str(end_idx)
    total_tp = abs(tp - entry)
    total_sl = abs(sl - entry)
    max_fav = 0.0
    max_adv = 0.0

    for i, (idx, row) in enumerate(post.iloc[1:].iterrows(), start=1):
        high = float(row["High"])
        low  = float(row["Low"])

        if bias == "Bearish":
            fav = max(0.0, entry - low)
            adv = max(0.0, high - entry)
        else:
            fav = max(0.0, high - entry)
            adv = max(0.0, entry - low)

        if total_tp > 0:
            max_fav = max(max_fav, fav / total_tp * 100)
        if total_sl > 0:
            max_adv = max(max_adv, adv / total_sl * 100)

        if bias == "Bearish":
            hit_sl = high >= sl
            hit_tp = low  <= tp
        else:
            hit_sl = low  <= sl
            hit_tp = high >= tp

        if hit_sl:
            stats["Result"] = "LOSS"; stats["Head Result"] = "LOSS"
            r = max_fav
            if r < 5:      stats["Loss Category"] = "immediate_rejection"
            elif r < 30:   stats["Loss Category"] = "early_reversal"
            elif r < 70:   stats["Loss Category"] = "mid_reversal"
            else:          stats["Loss Category"] = "late_reversal"
            stats["exit_idx"] = idx; stats["exit_price"] = sl
            stats["candles_to_exit"] = i; stats["Exit Date"] = str(idx)
            break

        if hit_tp:
            stats["Result"] = "WIN"; stats["Head Result"] = "WIN"
            stats["Loss Category"] = "success"
            stats["exit_idx"] = idx; stats["exit_price"] = tp
            stats["candles_to_exit"] = i; stats["Exit Date"] = str(idx)
            break

        if i >= CONFIG["MAX_TIMEOUT_BARS"]:
            stats["Result"] = "TIMEOUT"; stats["Head Result"] = "TIMEOUT"
            stats["Loss Category"] = "timeout"
            stats["exit_idx"] = idx; stats["exit_price"] = float(row["Close"])
            stats["candles_to_exit"] = i; stats["Exit Date"] = str(idx)
            break
    else:
        stats["candles_to_exit"] = max(0, len(post) - 1)
        stats["Exit Date"] = str(df.index[-1])
        stats["Loss Category"] = "open"

    stats["Max Reach %"] = round(max_fav, 1)
    stats["SL Safety %"] = round(100 - max_adv, 1) if max_adv <= 100 else 0.0
    stats["Final SL"] = sl

    if stats["Result"] == "WIN":
        stats["progress_ratio"] = 100.0
    elif stats["Result"] in ["LOSS", "BREAKEVEN"]:
        stats["progress_ratio"] = 0.0

    return stats


# ══════════════════════════════════════════════════════════════════════════════
# 🎯 run_full_analysis
# ══════════════════════════════════════════════════════════════════════════════
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
    for c in ["Open", "High", "Low", "Close"]:
        if c not in df.columns:
            default_empty["error"] = f"Missing column: {c}"
            return default_empty
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["Open", "High", "Low", "Close"])
    if len(df) < CONFIG["MIN_BARS_REQUIRED"]:
        default_empty["error"] = f"Insufficient data: {len(df)}"
        return default_empty

    df_active = df.tail(600).copy()
    all_patterns = detect_all_patterns(df_active, interval=interval, symbol=symbol)

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
        "consolidation_box": latest.get("consolidation_box"),
        "all_patterns": all_patterns, "match": latest.get("match", 100.0),
        "Result": latest.get("Result", "OPEN"),
        "Entry Date": latest.get("Entry Date"),
        "Exit Date": latest.get("Exit Date"),
        "Max Reach %": latest.get("Max Reach %", 0),
        "error": None,
    }


# ══════════════════════════════════════════════════════════════════════════════
# 📤 backtest_strategy
# ══════════════════════════════════════════════════════════════════════════════
def backtest_strategy(df, interval="1h", symbol=None):
    if df is None or df.empty or len(df) < CONFIG["MIN_BARS_REQUIRED"]:
        return []

    df = df.copy()
    for c in ["Open", "High", "Low", "Close"]:
        if c not in df.columns:
            return []
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["Open", "High", "Low", "Close"])
    if len(df) < CONFIG["MIN_BARS_REQUIRED"]:
        return []

    patterns = detect_all_patterns(df, interval=interval, symbol=symbol)

    trades = []
    for p in patterns:
        trades.append({
            "Symbol": symbol or "N/A", "symbol": symbol or "N/A",
            "Pattern": p["pattern"], "pattern": p["pattern"],
            "Bias": p["bias"], "bias": p["bias"],
            "Direction": p.get("direction", "BUY"),
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
            "Initial SL": p.get("Initial SL"),
            "Final SL": p.get("Final SL"),
            "level_price": p.get("level_price"),
            "level_touches": p.get("level_touches"),
            "consol_high": p.get("consol_high"),
            "consol_low": p.get("consol_low"),
            "consol_bars": p.get("consol_bars"),
            "consol_range_pct": p.get("consol_range_pct"),
            "consol_stability_pct": p.get("consol_stability_pct"),
            "breakout_body_pct": p.get("breakout_body_pct"),
        })
    return trades


# ══════════════════════════════════════════════════════════════════════════════
# 🔁 BACKWARD-COMPAT ALIAS (used by app's detect_near_signals)
# ══════════════════════════════════════════════════════════════════════════════
def detect_all_head_shoulders(pivots=None, df=None, is_backtest=False, **kwargs):
    if df is None:
        return []
    return detect_all_patterns(df)


# ══════════════════════════════════════════════════════════════════════════════
# 🧪 diagnose_filters
# ══════════════════════════════════════════════════════════════════════════════
def diagnose_filters(df, interval="1h", symbol=None):
    result = {
        "error": None, "total_raw_candidates": 0, "final_count": 0,
        "stages": {}, "smart_diagnosis": {}, "recommendations": [],
        "trade_analysis": [], "rejection_samples": {},
    }
    if df is None or df.empty or len(df) < CONFIG["MIN_BARS_REQUIRED"]:
        result["error"] = "بيانات غير كافية"
        return result

    df = df.copy()
    for c in ["Open", "High", "Low", "Close"]:
        if c not in df.columns:
            result["error"] = f"مفقود: {c}"
            return result
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["Open", "High", "Low", "Close"])

    trades = backtest_strategy(df, interval=interval, symbol=symbol)
    result["final_count"] = len(trades)
    result["total_raw_candidates"] = len(trades)

    wins     = [t for t in trades if "WIN" in str(t.get("Result", "")).upper()]
    losses   = [t for t in trades if "LOSS" in str(t.get("Result", "")).upper()]
    timeouts = [t for t in trades if "TIMEOUT" in str(t.get("Result", "")).upper()]

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

    avg_reach = 0.0
    if wins:
        avg_reach = round(sum(t.get("Max Reach %", 0) for t in wins) / len(wins), 1)

    result["smart_diagnosis"] = {
        "verdict": verdict,
        "win_breakdown": {"total_wins": len(wins), "avg_max_reach": avg_reach},
        "loss_breakdown": {
            "immediate_rejection": 0, "early_reversal": len(losses),
            "mid_reversal": 0, "late_reversal": 0,
            "unavoidable": 0, "avoidable": len(losses),
        },
        "action_plan": [
            f"🟢 WIN: {len(wins)} | ❌ LOSS: {len(losses)} | ⏰ TIMEOUT: {len(timeouts)}"
        ],
    }

    result["stages"] = {
        "1. S/R Levels":     {"before": len(trades), "after": len(trades), "rejected": 0, "pass_rate": "—"},
        "2. Close Breakout": {"before": len(trades), "after": len(trades), "rejected": 0, "pass_rate": "—"},
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
    if len(timeouts) > len(wins):
        recommendations.append({"severity": "حرج", "message": "الصفقات المنتهية بالوقت كثيرة."})
    result["recommendations"] = recommendations
    return result


if __name__ == "__main__":
    print("ENGINE.PY — S/R Horizontal Breakout v3")
    print(f"Lookback: {CONFIG['LOOKBACK_DAYS']} days   |   tolerance: {CONFIG['LEVEL_TOLERANCE_PCT']}%   |   min touches: {CONFIG['MIN_TOUCHES']}")
    print(f"Breakout: close beyond level by {CONFIG['BREAKOUT_BUFFER_PCT']}%   |   body ≥ {CONFIG['MIN_BREAKOUT_BODY_PCT']}%")
    print(f"SL: {CONFIG['SL_BUFFER_PCT']}% beyond level   |   Min R:R = 1:{CONFIG['MIN_RR']}")
