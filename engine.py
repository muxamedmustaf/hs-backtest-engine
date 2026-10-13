# -*- coding: utf-8 -*-
"""
ENGINE.PY — Horizontal Channel Breakout (v6)
=============================================
منطق مطابق للصور:
  • صندوق تصحيح أفقي ≥ 5 أيام بقمم وقيعان متساوية.
  • القمة = أعلى High، القاع = أدنى Low في نافذة التصحيح.
  • الصندوق يمتد من أول بيفوت حتى شمعة الكسر (حافتان أفقيتان تامّتان).
  • الإشارة فقط بعد إغلاق شمعة تكسر المقاومة/الدعم.
  • الوقف تحت القاع / فوق القمة، الهدف = 3× الوقف (1:3).
  • zigzag نظيف + سهم من الدخول إلى الهدف.
"""
import pandas as pd
import numpy as np


CONFIG = {
    # ── ZigZag: عمق أكبر + فلتر تأرجح أقوى → خط نظيف ───────────────────
    "ZIGZAG_DEPTH": 6,
    "ZIGZAG_BACKSTEP": 4,
    "MIN_SWING_PCT": 0.30,           # ⬆ 0.20 → 0.30 (ضد الضجيج)

    # ── القناة الأفقية ──────────────────────────────────────────────────
    "MIN_CONSOL_DAYS": 5,
    "MAX_CONSOL_DAYS": 60,
    "LEVEL_TOLERANCE_PCT": 0.30,     # ⬆ 0.25 → 0.30 (قبول أكثر للقمم المتقاربة)
    "MIN_TOUCHES": 2,
    "MIN_RANGE_PCT": 0.30,           # ⬆ 0.25 → 0.30
    "MAX_RANGE_PCT": 5.0,

    # ── الكسر ────────────────────────────────────────────────────────────
    "BREAKOUT_BUFFER_PCT": 0.03,
    "MIN_BREAKOUT_BODY_PCT": 0.05,

    # ── SL / TP ──────────────────────────────────────────────────────────
    "SL_BUFFER_PCT": 0.05,
    "TP_RR": 3.0,

    # ── فلاتر ────────────────────────────────────────────────────────────
    "MIN_BARS_BETWEEN": 5,
    "MAX_TIMEOUT_BARS": 300,
    "VOLUME_MA_PERIOD": 20,
    "MIN_BARS_REQUIRED": 100,
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
# Helpers
# ══════════════════════════════════════════════════════════════════════════════
def _get_max_gap(interval):
    return {"1m": 120, "5m": 50, "15m": 30, "30m": 25, "1h": 20,
            "4h": 15, "1d": 10}.get(interval, 50)


def _get_max_pattern_duration(interval):
    return {"1m": 600, "5m": 200, "15m": 150, "30m": 120, "1h": 100,
            "4h": 80, "1d": 60}.get(interval, 200)


def _days_to_bars(days, interval):
    bars_per_day = {
        "1m": 1440, "2m": 720, "3m": 480, "4m": 360, "5m": 288,
        "10m": 144, "15m": 96, "30m": 48, "45m": 32,
        "1h": 24, "2h": 12, "3h": 8, "4h": 6, "6h": 4, "8h": 3, "12h": 2,
        "1d": 1, "2d": 0.5, "3d": 0.33, "1wk": 0.2, "1mo": 0.05,
    }
    bpd = bars_per_day.get(interval, 24)
    return max(3, int(round(bpd * days)))


# ══════════════════════════════════════════════════════════════════════════════
# Indicators
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


def calculate_zigzag(df, depth=None, backstep=None):
    if depth is None:    depth = CONFIG["ZIGZAG_DEPTH"]
    if backstep is None: backstep = CONFIG["ZIGZAG_BACKSTEP"]
    df = df.copy()
    df["Pivot_H"] = np.nan
    df["Pivot_L"] = np.nan
    highs = df["High"].astype(float).values
    lows  = df["Low"].astype(float).values
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


def get_chronological_pivots(df, min_swing_pct=None):
    if min_swing_pct is None:
        min_swing_pct = CONFIG["MIN_SWING_PCT"]

    raw = []
    for pos, (idx, row) in enumerate(df.iterrows()):
        if not pd.isna(row["Pivot_H"]):
            raw.append({"idx": idx, "pos": pos, "val": float(row["Pivot_H"]), "type": "H"})
        elif not pd.isna(row["Pivot_L"]):
            raw.append({"idx": idx, "pos": pos, "val": float(row["Pivot_L"]), "type": "L"})
    if not raw:
        return []

    # 1) دمج المتتاليات من نفس النوع
    collapsed = [raw[0]]
    for p in raw[1:]:
        if collapsed[-1]["type"] == p["type"]:
            if p["type"] == "H" and p["val"] > collapsed[-1]["val"]:
                collapsed[-1] = p
            elif p["type"] == "L" and p["val"] < collapsed[-1]["val"]:
                collapsed[-1] = p
        else:
            collapsed.append(p)

    # 2) فلتر أدنى تأرجح
    filtered = [collapsed[0]]
    for p in collapsed[1:]:
        last = filtered[-1]
        swing_pct = abs(p["val"] - last["val"]) / max(last["val"], 1e-9) * 100
        if swing_pct >= min_swing_pct:
            filtered.append(p)
        else:
            if p["type"] == last["type"]:
                if p["type"] == "H" and p["val"] > last["val"]:
                    filtered[-1] = p
                elif p["type"] == "L" and p["val"] < last["val"]:
                    filtered[-1] = p
    return filtered


# ══════════════════════════════════════════════════════════════════════════════
# Clustering
# ══════════════════════════════════════════════════════════════════════════════
def cluster_levels(pivots, tolerance):
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
                lvl["members"].append(p)
                merged = True
                break
        if not merged:
            levels.append({
                "price":     p["val"],
                "values":    [p["val"]],
                "touches":   1,
                "first_pos": p["pos"],
                "last_pos":  p["pos"],
                "members":   [p],
            })
    return levels


# ══════════════════════════════════════════════════════════════════════════════
# Find horizontal channel
# ══════════════════════════════════════════════════════════════════════════════
def _find_horizontal_channel(active, min_bars, max_bars, tol):
    highs = [p for p in active if p["type"] == "H"]
    lows  = [p for p in active if p["type"] == "L"]
    if len(highs) < CONFIG["MIN_TOUCHES"] or len(lows) < CONFIG["MIN_TOUCHES"]:
        return None

    h_levels = [l for l in cluster_levels(highs, tol) if l["touches"] >= CONFIG["MIN_TOUCHES"]]
    l_levels = [l for l in cluster_levels(lows,  tol) if l["touches"] >= CONFIG["MIN_TOUCHES"]]
    if not h_levels or not l_levels:
        return None

    best = None
    for h in h_levels:
        for l in l_levels:
            if h["price"] <= l["price"]:
                continue
            first = min(h["first_pos"], l["first_pos"])
            last  = max(h["last_pos"],  l["last_pos"])
            duration = last - first
            if duration < min_bars or duration > max_bars:
                continue
            range_pct = (h["price"] - l["price"]) / max(l["price"], 1e-9) * 100
            if range_pct < CONFIG["MIN_RANGE_PCT"] or range_pct > CONFIG["MAX_RANGE_PCT"]:
                continue

            # تغطية زمنية: لمسات في النصفين
            mid = first + duration * 0.4
            h_early = sum(1 for m in h["members"] if m["pos"] <= mid)
            l_early = sum(1 for m in l["members"] if m["pos"] <= mid)
            h_late  = sum(1 for m in h["members"] if m["pos"] >  mid)
            l_late  = sum(1 for m in l["members"] if m["pos"] >  mid)
            if (h_early + l_early) < 1 or (h_late + l_late) < 1:
                continue

            score = h["touches"] + l["touches"] + duration / 30.0 + range_pct
            if best is None or score > best["score"]:
                best = {
                    "resistance": h,
                    "support":    l,
                    "start_pos":  first,
                    "end_pos":    last,
                    "score":      score,
                    "range_pct":  range_pct,
                    "duration_bars": duration,
                }
    return best


# ══════════════════════════════════════════════════════════════════════════════
# 🎯 DETECTOR
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
    df = calculate_zigzag(df)
    pivots = get_chronological_pivots(df)
    if len(pivots) < 4:
        return []

    min_bars = _days_to_bars(CONFIG["MIN_CONSOL_DAYS"], interval)
    max_bars = _days_to_bars(CONFIG["MAX_CONSOL_DAYS"], interval)
    tol      = CONFIG["LEVEL_TOLERANCE_PCT"] / 100.0
    buf      = CONFIG["BREAKOUT_BUFFER_PCT"] / 100.0
    backstep = CONFIG["ZIGZAG_BACKSTEP"]

    n = len(df)
    patterns = []
    last_signal_pos = -10**9

    for i in range(CONFIG["MIN_BARS_REQUIRED"], n):
        active = [p for p in pivots
                  if (p["pos"] + backstep) <= i and (i - p["pos"]) <= max_bars]
        if len(active) < 4:
            continue

        channel = _find_horizontal_channel(active, min_bars, max_bars, tol)
        if channel is None:
            continue

        candle = df.iloc[i]
        prev   = df.iloc[i - 1]
        close      = float(candle["Close"])
        open_      = float(candle["Open"])
        prev_close = float(prev["Close"])

        body_pct = abs(close - open_) / max(close, 1e-9) * 100
        if body_pct < CONFIG["MIN_BREAKOUT_BODY_PCT"]:
            continue

        res = float(channel["resistance"]["price"])
        sup = float(channel["support"]["price"])
        up_thr   = res * (1 + buf)
        down_thr = sup * (1 - buf)

        direction = None
        if prev_close <= up_thr and close > up_thr and close > open_:
            direction = "BUY"
        elif prev_close >= down_thr and close < down_thr and close < open_:
            direction = "SELL"

        if direction is None:
            continue
        if i - last_signal_pos < CONFIG["MIN_BARS_BETWEEN"]:
            continue

        pattern = _build_channel_pattern(df, i, channel, direction, body_pct)
        if pattern:
            patterns.append(pattern)
            last_signal_pos = i

    return patterns


def _build_channel_pattern(df, idx, channel, direction, body_pct):
    candle = df.iloc[idx]
    entry  = float(candle["Close"])

    start_p = int(channel["start_pos"])
    end_p   = int(channel["end_pos"])

    # ═════════════════════════════════════════════════════════════════════
    #  الصندوق الفعلي: من أعلى High وأدنى Low في نافذة التصحيح
    #  (باستثناء شمعة الكسر نفسها)
    # ═════════════════════════════════════════════════════════════════════
    seg_end_exclusive = idx
    if seg_end_exclusive <= start_p:
        return None
    seg = df.iloc[start_p:seg_end_exclusive]

    box_high = float(seg["High"].max())
    box_low  = float(seg["Low"].min())
    if box_low <= 0 or box_high <= box_low:
        return None

    res = box_high
    sup = box_low

    sl_buf = CONFIG["SL_BUFFER_PCT"] / 100.0

    if direction == "BUY":
        sl = sup * (1 - sl_buf)
        if sl >= entry:
            return None
        risk = entry - sl
        if risk <= 0:
            return None
        tp = entry + CONFIG["TP_RR"] * risk
    else:
        sl = res * (1 + sl_buf)
        if sl <= entry:
            return None
        risk = sl - entry
        if risk <= 0:
            return None
        tp = entry - CONFIG["TP_RR"] * risk

    rr = abs(tp - entry) / risk
    if rr < CONFIG["TP_RR"] - 0.05:
        return None

    bias = "Bullish" if direction == "BUY" else "Bearish"

    # ── Zigzag nodes: قمم/قيعان تلامس حواف الصندوق ─────────────────────
    touch_tol = CONFIG["LEVEL_TOLERANCE_PCT"] / 100.0 * 2.0
    nodes = []
    for pos in range(start_p, seg_end_exclusive):
        row = df.iloc[pos]
        if not pd.isna(row["Pivot_H"]):
            v = float(row["Pivot_H"])
            if abs(v - res) / max(res, 1e-9) <= touch_tol:
                nodes.append((df.index[pos], v))
        elif not pd.isna(row["Pivot_L"]):
            v = float(row["Pivot_L"])
            if abs(v - sup) / max(sup, 1e-9) <= touch_tol:
                nodes.append((df.index[pos], v))

    if len(nodes) < 2:
        nodes = [
            (df.index[start_p], res),
            (df.index[seg_end_exclusive - 1], sup),
        ]
    nodes.append((df.index[idx], entry))

    # ── Arrow: from entry to TP ─────────────────────────────────────────
    arrow_len = max(10, (seg_end_exclusive - start_p) // 3)
    x1_pos = min(idx + arrow_len, len(df) - 1)
    arrow = {
        "x0": df.index[idx],
        "y0": entry,
        "x1": df.index[x1_pos],
        "y1": tp,
        "direction": direction,
    }

    # ── Consolidation Box ───────────────────────────────────────────────
    box = {
        "x_start": start_p,
        "x_end":   idx,
        "high":    round(res, 5),
        "low":     round(sup, 5),
    }

    pattern = {
        "name": "Horizontal Channel Breakout",
        "pattern": (
            f"Channel {direction} · "
            f"R×{channel['resistance']['touches']} / S×{channel['support']['touches']}"
        ),
        "bias": bias,
        "direction": direction,
        "match": float(min(100, 60 + (channel["resistance"]["touches"] + channel["support"]["touches"]) * 5)),
        "entry": round(entry, 5),
        "entry_trigger": round(entry, 5),
        "sl": round(sl, 5),
        "tp": round(tp, 5),
        "SL": round(sl, 5),
        "TP": round(tp, 5),
        "Entry": round(entry, 5),
        "nodes": nodes,
        "arrow": arrow,
        "consolidation_box": box,
        "resistance": round(res, 5),
        "support":    round(sup, 5),
        "level_price": round(res if direction == "BUY" else sup, 5),
        "level_touches": (channel["resistance"]["touches"] if direction == "BUY"
                          else channel["support"]["touches"]),
        "channel_start": df.index[start_p],
        "channel_end":   df.index[end_p],
        "channel_duration_bars": int(channel["duration_bars"]),
        "channel_range_pct": round((res - sup) / max(sup, 1e-9) * 100, 3),
        "neckline_start_idx": df.index[start_p],
        "neckline_end_idx":   df.index[idx],
        "end_pos": idx,
        "Entry Conditions": (
            f"Horizontal channel ≥{CONFIG['MIN_CONSOL_DAYS']}d · "
            f"R×{channel['resistance']['touches']} / S×{channel['support']['touches']} → close breakout"
        ),
        "consol_high": round(res, 5),
        "consol_low":  round(sup, 5),
        "consol_bars": int(seg_end_exclusive - start_p),
        "consol_range_pct": round((res - sup) / max(sup, 1e-9) * 100, 3),
        "consol_stability_pct": 100.0,
        "breakout_body_pct": round(body_pct, 3),
    }

    pattern.update(simulate_trade_outcome(pattern, df))
    return pattern


# ══════════════════════════════════════════════════════════════════════════════
# Simulation
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

        hit_sl = (high >= sl) if bias == "Bearish" else (low <= sl)
        hit_tp = (low <= tp)  if bias == "Bearish" else (high >= tp)

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
# run_full_analysis
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

    df_active = df.tail(800).copy()
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
        "arrow": latest.get("arrow"),
        "consolidation_box": latest.get("consolidation_box"),
        "resistance": latest.get("resistance"),
        "support": latest.get("support"),
        "all_patterns": all_patterns, "match": latest.get("match", 100.0),
        "Result": latest.get("Result", "OPEN"),
        "Entry Date": latest.get("Entry Date"),
        "Exit Date": latest.get("Exit Date"),
        "Max Reach %": latest.get("Max Reach %", 0),
        "error": None,
    }


# ══════════════════════════════════════════════════════════════════════════════
# backtest_strategy
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
            "arrow": p.get("arrow"),
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
            "resistance": p.get("resistance"),
            "support":    p.get("support"),
            "channel_start": p.get("channel_start"),
            "channel_end":   p.get("channel_end"),
            "channel_duration_bars": p.get("channel_duration_bars"),
            "channel_range_pct": p.get("channel_range_pct"),
            "consol_high": p.get("consol_high"),
            "consol_low":  p.get("consol_low"),
            "consol_bars": p.get("consol_bars"),
            "consol_range_pct": p.get("consol_range_pct"),
            "consol_stability_pct": p.get("consol_stability_pct"),
            "breakout_body_pct": p.get("breakout_body_pct"),
        })
    return trades


# ══════════════════════════════════════════════════════════════════════════════
# Backward-compat alias
# ══════════════════════════════════════════════════════════════════════════════
def detect_all_head_shoulders(pivots=None, df=None, is_backtest=False, **kwargs):
    if df is None:
        return []
    return detect_all_patterns(df)


# ══════════════════════════════════════════════════════════════════════════════
# diagnose_filters
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
        f"1. Channel ≥{CONFIG['MIN_CONSOL_DAYS']}d": {"before": len(trades), "after": len(trades), "rejected": 0, "pass_rate": "—"},
        "2. Close Breakout":                          {"before": len(trades), "after": len(trades), "rejected": 0, "pass_rate": "—"},
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
    print("ENGINE.PY — Horizontal Channel Breakout v6")
    print(f"ZigZag: depth={CONFIG['ZIGZAG_DEPTH']} backstep={CONFIG['ZIGZAG_BACKSTEP']} min_swing={CONFIG['MIN_SWING_PCT']}%")
    print(f"Channel: ≥{CONFIG['MIN_CONSOL_DAYS']}d | tol={CONFIG['LEVEL_TOLERANCE_PCT']}% | touches≥{CONFIG['MIN_TOUCHES']} | range {CONFIG['MIN_RANGE_PCT']}–{CONFIG['MAX_RANGE_PCT']}%")
    print(f"Breakout: close beyond level by {CONFIG['BREAKOUT_BUFFER_PCT']}% | body ≥ {CONFIG['MIN_BREAKOUT_BODY_PCT']}%")
    print(f"SL: {CONFIG['SL_BUFFER_PCT']}% beyond opposite side | TP = {CONFIG['TP_RR']}× risk")
    print("Box: uses ACTUAL High/Low of the correction window (flat edges)")
