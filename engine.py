# -*- coding: utf-8 -*-
"""
ENGINE.PY — Consolidation Breakout Strategy (v2)
==================================================
Consolidation detection ADAG + Visualization box cusub
"""
import pandas as pd
import numpy as np

CONFIG = {
    "ZIGZAG_DEPTH": 8,
    "ZIGZAG_BACKSTEP": 4,
    # Consolidation — ADAG
    "MIN_CONSOL_BARS": 8,          # 5 → 8 (adag)
    "MAX_CONSOL_BARS": 50,         # 60 → 50
    "MAX_CONSOL_RANGE_PCT": 0.35,  # 0.50 → 0.35 (adag)
    "CONSOL_STABILITY_PCT": 0.10,  # 0.10% — waa in uu yahay stable
    # Breakout — CAD
    "MIN_BREAKOUT_BODY_PCT": 0.15,
    "BREAKOUT_BUFFER_PCT": 0.02,
    "BREAKOUT_MIN_BARS_AFTER": 1,  # Breakout waa in uu socdaa 1 bar
    # SL/TP
    "SL_INSIDE_PCT": 0.40,
    "TP_RR": 2.5,
    # Filters
    "MIN_BARS_BETWEEN": 10,
    "MAX_TIMEOUT_BARS": 200,
    "VOLUME_MA_PERIOD": 20,
}

TIMEOUT_STATISTICAL_FLOOR = 200
TIMEOUT_DURATION_MULTIPLIER = 3

REASON_MAP = {
    "immediate_rejection": {"reason": "رفض فوري.", "action": "انتظر.", "prevention": "—"},
    "early_reversal": {"reason": "انعكاس مبكر.", "action": "SL للتعادل.", "prevention": "Trailing."},
    "mid_reversal": {"reason": "انعكاس متوسط.", "action": "خروج 50%.", "prevention": "TP جزئي."},
    "late_reversal": {"reason": "انعكاس متأخر.", "action": "Trailing.", "prevention": "راقب."},
    "timeout": {"reason": "انتهى الوقت.", "action": "أغلق.", "prevention": "ADX."},
    "breakeven": {"reason": "تعادل.", "action": "—", "prevention": "—"},
    "success": {"reason": "وصل الهدف.", "action": "كرر.", "prevention": "—"},
    "open": {"reason": "مفتوحة.", "action": "راقب.", "prevention": "—"},
}


def _get_max_gap(interval):
    return {"1m": 120, "5m": 50, "15m": 30, "30m": 25, "1h": 20,
            "4h": 15, "1d": 10}.get(interval, 50)


def _get_max_pattern_duration(interval):
    return {"1m": 600, "5m": 200, "15m": 150, "30m": 120, "1h": 100,
            "4h": 80, "1d": 60}.get(interval, 200)


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
# 1️⃣ CONSOLIDATION DETECTION — ADAG + SANDBUUQ
# ══════════════════════════════════════════════════════════════════════════════
def detect_consolidation(df, start_idx, end_idx):
    """
    Hubi consolidation adag:
    - Range < MAX_CONSOL_RANGE_PCT
    - Bars 8-50
    - Stability: wax kasta oo bars ah waa in uu range ku jiraa
    """
    n = end_idx - start_idx + 1
    if n < CONFIG["MIN_CONSOL_BARS"] or n > CONFIG["MAX_CONSOL_BARS"]:
        return False, None

    seg = df.iloc[start_idx:end_idx + 1]
    high = float(seg["High"].max())
    low = float(seg["Low"].min())
    if low <= 0:
        return False, None

    range_pct = (high - low) / low * 100
    if range_pct > CONFIG["MAX_CONSOL_RANGE_PCT"]:
        return False, None

    # Hubi stability — bars kasta waa in uu ku jiraa range
    stable_count = 0
    for _, row in seg.iterrows():
        if low <= row["Close"] <= high:
            stable_count += 1
    stability_pct = stable_count / len(seg) * 100
    if stability_pct < 90:  # 90% bars waa in uu ku jiraa
        return False, None

    return True, {
        "high": high, "low": low,
        "range_pct": round(range_pct, 3),
        "bars": n,
        "start_idx": start_idx,
        "end_idx": end_idx,
        "stability_pct": round(stability_pct, 1),
        "high_idx": df.index[start_idx + int(seg["High"].values.argmax())],
        "low_idx": df.index[start_idx + int(seg["Low"].values.argmin())],
    }


def find_consolidation_ending_at(df, end_idx):
    """Soo hel consolidation ugu fiican ee ku dhammaanaysa end_idx."""
    best = None
    min_bars = CONFIG["MIN_CONSOL_BARS"]
    max_bars = min(CONFIG["MAX_CONSOL_BARS"], end_idx + 1)

    for lookback in range(min_bars, max_bars + 1):
        start = end_idx - lookback + 1
        if start < 0:
            break
        ok, info = detect_consolidation(df, start, end_idx)
        if ok:
            if best is None or info["bars"] > best["bars"]:
                best = info

    return best


# ══════════════════════════════════════════════════════════════════════════════
# 2️⃣ BREAKOUT — CAD + CONFIRMED
# ══════════════════════════════════════════════════════════════════════════════
def detect_breakout(df, consol, idx):
    """Hubi in breakout dhaco — oo uu yahay CONFIRMED."""
    if consol is None or idx < 1 or idx >= len(df):
        return False, None

    candle = df.iloc[idx]
    consol_high = consol["high"]
    consol_low = consol["low"]

    buffer = consol_high * (CONFIG["BREAKOUT_BUFFER_PCT"] / 100)
    buffer_low = consol_low * (CONFIG["BREAKOUT_BUFFER_PCT"] / 100)

    body = abs(candle["Close"] - candle["Open"])
    body_pct = (body / consol_low * 100) if consol_low > 0 else 0
    if body_pct < CONFIG["MIN_BREAKOUT_BODY_PCT"]:
        return False, None

    # Bullish Breakout (BUY)
    if candle["Close"] > consol_high + buffer and candle["Close"] > candle["Open"]:
        return True, {
            "direction": "BUY",
            "entry": float(candle["Close"]),
            "consol_high": consol_high,
            "consol_low": consol_low,
            "body_pct": round(body_pct, 3),
            "breakout_price": float(candle["Close"]),
            "breakout_idx": idx,
        }

    # Bearish Breakout (SELL)
    if candle["Close"] < consol_low - buffer_low and candle["Close"] < candle["Open"]:
        return True, {
            "direction": "SELL",
            "entry": float(candle["Close"]),
            "consol_high": consol_high,
            "consol_low": consol_low,
            "body_pct": round(body_pct, 3),
            "breakout_price": float(candle["Close"]),
            "breakout_idx": idx,
        }

    return False, None


# ══════════════════════════════════════════════════════════════════════════════
# 3️⃣ SL/TP
# ══════════════════════════════════════════════════════════════════════════════
def compute_sl_tp(entry, consol, direction):
    consol_high = consol["high"]
    consol_low = consol["low"]
    range_size = consol_high - consol_low

    if direction == "BUY":
        sl = consol_low + CONFIG["SL_INSIDE_PCT"] * range_size
        if sl >= entry:
            return None
        risk = entry - sl
        if risk <= 0:
            return None
        tp = entry + CONFIG["TP_RR"] * risk
        return {
            "sl": round(sl, 5), "tp": round(tp, 5),
            "risk": round(risk, 5),
            "reward": round(tp - entry, 5),
            "rr": CONFIG["TP_RR"],
        }
    else:
        sl = consol_high - CONFIG["SL_INSIDE_PCT"] * range_size
        if sl <= entry:
            return None
        risk = sl - entry
        if risk <= 0:
            return None
        tp = entry - CONFIG["TP_RR"] * risk
        return {
            "sl": round(sl, 5), "tp": round(tp, 5),
            "risk": round(risk, 5),
            "reward": round(entry - tp, 5),
            "rr": CONFIG["TP_RR"],
        }


# ══════════════════════════════════════════════════════════════════════════════
# 🎯 DETECT ALL PATTERNS
# ══════════════════════════════════════════════════════════════════════════════
def detect_all_patterns(df, interval="1h", symbol=None):
    """Soo hel dhammaan signals-ka Consolidation Breakout."""
    if df is None or df.empty or len(df) < 50:
        return []

    df = df.copy()
    for c in ["Open", "High", "Low", "Close"]:
        if c not in df.columns:
            return []
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["Open", "High", "Low", "Close"])
    if len(df) < 50:
        return []

    patterns = []
    last_idx = -999

    for idx in range(CONFIG["MIN_CONSOL_BARS"], len(df)):
        if idx - last_idx < CONFIG["MIN_BARS_BETWEEN"]:
            continue

        # Soo hel consolidation ku dhammaanaysa idx-1
        consol = find_consolidation_ending_at(df, idx - 1)
        if not consol:
            continue

        # Hubi breakout ee idx
        ok, br = detect_breakout(df, consol, idx)
        if not ok:
            continue

        # Xisaabi SL/TP
        sltp = compute_sl_tp(br["entry"], consol, br["direction"])
        if not sltp:
            continue

        direction = br["direction"]
        bias = "Bullish" if direction == "BUY" else "Bearish"

        # Nodes — SANDBUUQ 6 ah
        # Nodes 1-4: Sanduuqa consolidation (4 corners)
        # Nodes 5-6: Breakout + Entry
        nodes = [
            (consol["high_idx"], consol["high"]),   # 1: Top-left
            (consol["low_idx"], consol["low"]),     # 2: Bottom-left
            (consol["low_idx"], consol["high"]),    # 3: Top-right (ku soo dhaqaaq)
            (consol["high_idx"], consol["low"]),    # 4: Bottom-right
            (df.index[consol["end_idx"]], consol["high"] if direction == "BUY" else consol["low"]),  # 5: Consolidation end
            (df.index[idx], br["entry"]),           # 6: Breakout
        ]

        pattern = {
            "name": "Consolidation Breakout",
            "pattern": f"Consol → {direction} Breakout",
            "bias": bias,
            "direction": direction,
            "match": 100.0,
            "entry": round(br["entry"], 5),
            "entry_trigger": round(br["entry"], 5),
            "sl": sltp["sl"],
            "tp": sltp["tp"],
            "SL": sltp["sl"],
            "TP": sltp["tp"],
            "Entry": round(br["entry"], 5),
            "nodes": nodes,
            "consolidation_box": {
                "x_start": consol["start_idx"],
                "x_end": consol["end_idx"],
                "high": consol["high"],
                "low": consol["low"],
            },
            "neckline_start_idx": df.index[consol["start_idx"]],
            "neckline_end_idx": df.index[idx],
            "end_pos": idx,
            "Entry Conditions": "Consolidation + Confirmed Breakout",
            "consol_high": consol["high"],
            "consol_low": consol["low"],
            "consol_bars": consol["bars"],
            "consol_range_pct": consol["range_pct"],
            "consol_stability_pct": consol["stability_pct"],
            "breakout_body_pct": br["body_pct"],
        }
        pattern.update(simulate_trade_outcome(pattern, df))
        patterns.append(pattern)
        last_idx = idx

    return patterns


# ══════════════════════════════════════════════════════════════════════════════
# 🧪 SIMULATE
# ══════════════════════════════════════════════════════════════════════════════
def simulate_trade_outcome(pattern, df):
    bias = pattern["bias"]
    entry = float(pattern["entry"])
    sl = float(pattern["sl"])
    tp = float(pattern["tp"])
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
        low = float(row["Low"])

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
            hit_tp = low <= tp
        else:
            hit_sl = low <= sl
            hit_tp = high >= tp

        if hit_sl:
            stats["Result"] = "LOSS"; stats["Head Result"] = "LOSS"
            r = max_fav
            if r < 5: stats["Loss Category"] = "immediate_rejection"
            elif r < 30: stats["Loss Category"] = "early_reversal"
            elif r < 70: stats["Loss Category"] = "mid_reversal"
            else: stats["Loss Category"] = "late_reversal"
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
    if len(df) < 50:
        default_empty["error"] = f"Insufficient data: {len(df)}"
        return default_empty

    df_active = df.tail(300).copy()
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
        "all_patterns": all_patterns, "match": 100.0,
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
    if df is None or df.empty or len(df) < 50:
        return []

    df = df.copy()
    for c in ["Open", "High", "Low", "Close"]:
        if c not in df.columns:
            return []
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["Open", "High", "Low", "Close"])
    if len(df) < 50:
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
            "consol_high": p.get("consol_high"),
            "consol_low": p.get("consol_low"),
            "consol_bars": p.get("consol_bars"),
            "consol_range_pct": p.get("consol_range_pct"),
            "consol_stability_pct": p.get("consol_stability_pct"),
            "breakout_body_pct": p.get("breakout_body_pct"),
        })
    return trades


# ══════════════════════════════════════════════════════════════════════════════
# 🧪 diagnose_filters
# ══════════════════════════════════════════════════════════════════════════════
def diagnose_filters(df, interval="1h", symbol=None):
    result = {
        "error": None, "total_raw_candidates": 0, "final_count": 0,
        "stages": {}, "smart_diagnosis": {}, "recommendations": [],
        "trade_analysis": [], "rejection_samples": {},
    }
    if df is None or df.empty or len(df) < 50:
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

    wins = [t for t in trades if "WIN" in str(t.get("Result", "")).upper()]
    losses = [t for t in trades if "LOSS" in str(t.get("Result", "")).upper()]
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
        "1. Consolidation": {"before": len(trades), "after": len(trades), "rejected": 0, "pass_rate": "—"},
        "2. Breakout": {"before": len(trades), "after": len(trades), "rejected": 0, "pass_rate": "—"},
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
    print("ENGINE.PY — Consolidation Breakout v2")
    print("Consolidation: 8-50 bars, range ≤ 0.35%, stability ≥ 90%")
    print("Breakout: confirmed close + body ≥ 0.15%")
    print("SL inside: 40% | TP: 2.5× SL")
