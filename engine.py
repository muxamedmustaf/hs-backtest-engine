# -*- coding: utf-8 -*-
"""
ENGINE.PY — Reversal After Consolidation
=========================================
1. Downtrend (اتجاه سابق)
2. Consolidation (تجميع)
3. Breakout (كسر الحاجز)
4. Confirmed close (شمعة اختراقية مغلقة)
5. SL inside consolidation (وقف داخل التجميع)
6. TP = 3× SL (الهدف 3 أضعاف الوقف)
"""
import pandas as pd
import numpy as np

# ══════════════════════════════════════════════════════════════════════════════
# ⚙️ CONFIG
# ══════════════════════════════════════════════════════════════════════════════
CONFIG = {
    "ZIGZAG_DEPTH": 8,
    "ZIGZAG_BACKSTEP": 4,
    "MIN_LOWER_HIGHS": 2,
    "MIN_LOWER_LOWS": 2,
    "MIN_CONSOL_BARS": 5,
    "MAX_CONSOL_BARS": 40,
    "MAX_CONSOL_RANGE_PCT": 0.30,
    "MIN_BREAKOUT_BODY_PCT": 0.15,
    "BREAKOUT_BUFFER_PCT": 0.02,
    "SL_INSIDE_PCT": 0.40,
    "TP_RR": 3.0,
    "MIN_BARS_BETWEEN": 5,
    "MAX_TIMEOUT_BARS": 200,
    "VOLUME_MA_PERIOD": 20,
}

TIMEOUT_STATISTICAL_FLOOR = 200
TIMEOUT_DURATION_MULTIPLIER = 3

REASON_MAP = {
    "immediate_rejection": {"reason": "رفض فوري", "action": "انتظر", "prevention": "—"},
    "early_reversal": {"reason": "انعكاس مبكر", "action": "SL للتعادل", "prevention": "Trailing"},
    "mid_reversal": {"reason": "انعكاس متوسط", "action": "خروج 50%", "prevention": "TP جزئي"},
    "late_reversal": {"reason": "انعكاس متأخر", "action": "Trailing", "prevention": "راقب"},
    "timeout": {"reason": "انتهى الوقت", "action": "أغلق", "prevention": "ADX"},
    "success": {"reason": "وصل الهدف", "action": "كرر", "prevention": "—"},
    "open": {"reason": "مفتوحة", "action": "راقب", "prevention": "—"},
}


def _get_max_gap(interval):
    return {"1m": 120, "5m": 50, "15m": 30, "30m": 25, "1h": 20,
            "4h": 15, "1d": 10}.get(interval, 50)


def _get_max_pattern_duration(interval):
    return {"1m": 600, "5m": 200, "15m": 150, "30m": 120, "1h": 100,
            "4h": 80, "1d": 60}.get(interval, 200)


# ══════════════════════════════════════════════════════════════════════════════
# 🛠️ INDICATORS (sida hore — loo baahan yahay)
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
# 1️⃣ DOWNTREND
# ══════════════════════════════════════════════════════════════════════════════
def detect_downtrend(pivots, end_idx):
    relevant = [p for p in pivots if p["pos"] <= end_idx]
    if len(relevant) < 4:
        return False, None
    last4 = relevant[-4:]
    highs = [p for p in last4 if p["type"] == "H"]
    lows = [p for p in last4 if p["type"] == "L"]
    if len(highs) < 2 or len(lows) < 2:
        return False, None
    lh = sum(1 for i in range(1, len(highs)) if highs[i]["val"] < highs[i-1]["val"])
    ll = sum(1 for i in range(1, len(lows)) if lows[i]["val"] < lows[i-1]["val"])
    is_down = (lh >= CONFIG["MIN_LOWER_HIGHS"] and ll >= CONFIG["MIN_LOWER_LOWS"])
    return is_down, {
        "lower_highs": lh, "lower_lows": ll,
        "last_low_pos": lows[-1]["pos"],
        "last_high_pos": highs[-1]["pos"],
    }


# ══════════════════════════════════════════════════════════════════════════════
# 2️⃣ CONSOLIDATION
# ══════════════════════════════════════════════════════════════════════════════
def detect_consolidation(df, start_idx, end_idx):
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
    return True, {
        "high": high, "low": low,
        "range_pct": round(range_pct, 3),
        "bars": n, "start_idx": start_idx, "end_idx": end_idx,
    }


def find_consolidation(df, downtrend_info):
    if not downtrend_info:
        return None
    start = downtrend_info["last_low_pos"] + 1
    if start >= len(df) - 5:
        return None
    best = None
    for end in range(start + CONFIG["MIN_CONSOL_BARS"], min(start + 60, len(df))):
        ok, info = detect_consolidation(df, start, end)
        if ok and (best is None or info["bars"] > best["bars"]):
            best = info
    return best


# ══════════════════════════════════════════════════════════════════════════════
# 3️⃣ + 4️⃣ BREAKOUT + CONFIRMED
# ══════════════════════════════════════════════════════════════════════════════
def detect_breakout(df, consol, idx):
    if consol is None or idx < 1 or idx >= len(df):
        return False, None
    candle = df.iloc[idx]
    consol_high = consol["high"]
    consol_low = consol["low"]
    buffer = consol_high * (CONFIG["BREAKOUT_BUFFER_PCT"] / 100)
    if candle["Close"] <= consol_high + buffer:
        return False, None
    if candle["Close"] <= candle["Open"]:
        return False, None
    body = abs(candle["Close"] - candle["Open"])
    body_pct = (body / consol_low * 100) if consol_low > 0 else 0
    if body_pct < CONFIG["MIN_BREAKOUT_BODY_PCT"]:
        return False, None
    return True, {
        "entry": float(candle["Close"]),
        "consol_high": consol_high,
        "consol_low": consol_low,
        "body_pct": round(body_pct, 3),
    }


# ══════════════════════════════════════════════════════════════════════════════
# 5️⃣ + 6️⃣ SL + TP
# ══════════════════════════════════════════════════════════════════════════════
def compute_sl_tp(entry, consol):
    consol_high = consol["high"]
    consol_low = consol["low"]
    range_size = consol_high - consol_low
    # 5️⃣ SL inside consolidation
    sl = consol_low + CONFIG["SL_INSIDE_PCT"] * range_size
    if sl >= entry:
        return None
    risk = entry - sl
    if risk <= 0:
        return None
    # 6️⃣ TP = 3× risk
    tp = entry + CONFIG["TP_RR"] * risk
    return {
        "sl": round(sl, 5),
        "tp": round(tp, 5),
        "risk": round(risk, 5),
        "reward": round(tp - entry, 5),
        "rr": CONFIG["TP_RR"],
    }


# ══════════════════════════════════════════════════════════════════════════════
# 🧪 SIMULATE
# ══════════════════════════════════════════════════════════════════════════════
def simulate_trade_outcome(pattern, df):
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
        "Trailing Stage": 0, "Initial SL": sl, "Final SL": sl,
        "Loss Category": None,
        "Pattern Duration": 50, "Timeout Used": CONFIG["MAX_TIMEOUT_BARS"],
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

        fav = max(0.0, high - entry)
        adv = max(0.0, entry - low)

        if total_tp > 0:
            max_fav = max(max_fav, fav / total_tp * 100)
        if total_sl > 0:
            max_adv = max(max_adv, adv / total_sl * 100)

        if low <= sl:
            stats["Result"] = "LOSS"; stats["Head Result"] = "LOSS"
            r = max_fav
            if r < 5: stats["Loss Category"] = "immediate_rejection"
            elif r < 30: stats["Loss Category"] = "early_reversal"
            elif r < 70: stats["Loss Category"] = "mid_reversal"
            else: stats["Loss Category"] = "late_reversal"
            stats["exit_idx"] = idx; stats["exit_price"] = sl
            stats["candles_to_exit"] = i; stats["Exit Date"] = str(idx)
            break
        if high >= tp:
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
            moved = max(0.0, float(row["Close"]) - entry)
            if total_tp > 0:
                stats["progress_ratio"] = round(moved / total_tp * 100, 2)
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
    return stats


# ══════════════════════════════════════════════════════════════════════════════
# 🎯 DETECT ALL — Istiraatijiyada cusub
# ══════════════════════════════════════════════════════════════════════════════
def detect_all_patterns(df, interval="1h", symbol=None):
    """Soo hel dhammaan signals-ka istiraatijiyada cusub."""
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

    df_zz = calculate_indicators(df.copy())
    df_zz = calculate_zigzag(df_zz, CONFIG["ZIGZAG_DEPTH"], CONFIG["ZIGZAG_BACKSTEP"])
    pivots = get_chronological_pivots(df_zz)

    if not pivots:
        return []

    patterns = []
    last_idx = -999

    for idx in range(50, len(df)):
        if idx - last_idx < CONFIG["MIN_BARS_BETWEEN"]:
            continue

        # 1️⃣ Downtrend
        is_down, dt = detect_downtrend(pivots, idx)
        if not is_down:
            continue

        # 2️⃣ Consolidation
        consol = find_consolidation(df, dt)
        if not consol:
            continue

        # 3️⃣+4️⃣ Breakout + Confirmed
        ok, br = detect_breakout(df, consol, idx)
        if not ok:
            continue

        # 5️⃣+6️⃣ SL/TP
        sltp = compute_sl_tp(br["entry"], consol)
        if not sltp:
            continue

        pattern = {
            "name": "Reversal After Consolidation",
            "pattern": "Down→Consol→Breakout",
            "bias": "Bullish",
            "match": 100.0,
            "entry": round(br["entry"], 5),
            "entry_trigger": round(br["entry"], 5),
            "sl": sltp["sl"],
            "tp": sltp["tp"],
            "SL": sltp["sl"],
            "TP": sltp["tp"],
            "Entry": round(br["entry"], 5),
            "nodes": [
                (df.index[consol["start_idx"]], consol["high"]),
                (df.index[consol["start_idx"]], consol["low"]),
                (df.index[consol["end_idx"]], consol["high"]),
                (df.index[idx], br["entry"]),
            ],
            "neckline_start_idx": df.index[consol["start_idx"]],
            "neckline_end_idx": df.index[idx],
            "end_pos": idx,
            "Entry Conditions": "Downtrend + Consolidation + Breakout",
            "consol_high": consol["high"],
            "consol_low": consol["low"],
            "consol_bars": consol["bars"],
            "consol_range_pct": consol["range_pct"],
            "breakout_body_pct": br["body_pct"],
            "lower_highs": dt["lower_highs"],
            "lower_lows": dt["lower_lows"],
        }
        pattern.update(simulate_trade_outcome(pattern, df))
        patterns.append(pattern)
        last_idx = idx

    return patterns


# ══════════════════════════════════════════════════════════════════════════════
# 🎯 run_full_analysis — loo baahan yahay backtest.py
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
    signal = "STRONG BUY"

    return {
        "df": df_active, "symbol": symbol or "N/A",
        "signal": signal, "pattern": latest["pattern"], "bias": latest["bias"],
        "entry": latest["entry"], "entry_trigger": latest["entry_trigger"],
        "sl": latest["sl"], "tp": latest["tp"],
        "nodes": latest["nodes"], "pattern_nodes": latest["nodes"],
        "all_patterns": all_patterns, "match": 100.0,
        "Result": latest.get("Result", "OPEN"),
        "Entry Date": latest.get("Entry Date"),
        "Exit Date": latest.get("Exit Date"),
        "Max Reach %": latest.get("Max Reach %", 0),
        "error": None,
    }


# ══════════════════════════════════════════════════════════════════════════════
# 📤 backtest_strategy — loo baahan yahay backtest.py
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
            "breakout_body_pct": p.get("breakout_body_pct"),
            "lower_highs": p.get("lower_highs"),
            "lower_lows": p.get("lower_lows"),
        })
    return trades


# ══════════════════════════════════════════════════════════════════════════════
# 🧪 diagnose_filters — loo baahan yahay backtest.py
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
    skipped = [t for t in trades if "SKIPPED" in str(t.get("Result", "")).upper()]

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
            f"🟢 WIN: {len(wins)} | ❌ LOSS: {len(losses)} | ⏰ TIMEOUT: {len(timeouts)} | ⏭️ SKIPPED: {len(skipped)}"
        ],
    }

    result["stages"] = {
        "1. Downtrend": {"before": 0, "after": len(trades), "rejected": 0, "pass_rate": "—"},
        "2. Consolidation": {"before": len(trades), "after": len(trades), "rejected": 0, "pass_rate": "—"},
        "3. Breakout": {"before": len(trades), "after": len(trades), "rejected": 0, "pass_rate": "—"},
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
    print("ENGINE.PY — Reversal After Consolidation")
    print("1. Downtrend  2. Consolidation  3. Breakout")
    print("4. Confirmed Close  5. SL inside  6. TP = 3× SL")
