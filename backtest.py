# -*- coding: utf-8 -*-
"""
ENGINE.PY — Trend → Consolidation → Continuation (v22)
========================================================
منطق جديد:
  1. نبحث عن اتجاه قوي (up أو down) بميل واضح (R² عالٍ)
  2. يليه تجميع ضيق ≥ أسبوع واحد
  3. كسر المستطيل في نفس اتجاه الموجة السابقة (استمرار)

الفلاتر:
  • اتجاه: R² ≥ 0.65, |move| ≥ 0.8%
  • تجميع: |slope| صغير · CV صغير · drift صغير · ≥2 لمسات/جهة
  • شكل أفقي: عرض ÷ ارتفاع ≥ 5
  • كسر بإغلاق شمعة
  • SL على الجهة المقابلة · TP = حجم الموجة السابقة
"""
import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view


# ══════════════════════════════════════════════════════════════════════════════
# CONFIG
# ══════════════════════════════════════════════════════════════════════════════
CONFIG = {
    # ── الاتجاه قبل التجميع ─────────────────────────────────────────────
    "TREND_WINDOWS": [15, 25, 40, 60, 90],
    "TREND_MIN_R2": 0.65,
    "TREND_MIN_MOVE_PCT": 0.80,
    "TREND_MIN_SLOPE_PCT_PER_BAR": 0.05,

    # ── التجميع ─────────────────────────────────────────────────────────
    "CONS_WINDOWS": [30, 45, 60, 90, 120, 180, 240],
    "CONS_MIN_WEEKS": 1.0,
    "CONS_MAX_SLOPE_PCT_PER_BAR": 0.012,
    "CONS_MAX_CV": 0.55,
    "CONS_MAX_DRIFT": 0.90,
    "CONS_MIN_FLAT_BARS_PCT": 0.60,
    "CONS_MIN_TOUCHES_EACH_SIDE": 2,
    "CONS_MIN_RANGE_PCT": 0.15,
    "CONS_MAX_RANGE_PCT": 4.00,
    "CONS_MIN_ASPECT": 5.0,

    # ── الكسر ───────────────────────────────────────────────────────────
    "BRK_BUFFER_PCT": 0.05,
    "BRK_MIN_BODY_PCT": 0.08,

    # ── SL/TP ───────────────────────────────────────────────────────────
    "SL_BUFFER_PCT": 0.05,
    "MIN_RR": 1.2,

    # ── عامة ────────────────────────────────────────────────────────────
    "MIN_BARS_BETWEEN": 20,
    "MIN_BARS_REQUIRED": 200,
    "MAX_TIMEOUT_BARS": 300,
}


# ══════════════════════════════════════════════════════════════════════════════
# Interval helpers
# ══════════════════════════════════════════════════════════════════════════════
_BARS_PER_WEEK = {
    "1m": 7200, "5m": 1440, "15m": 480, "30m": 240,
    "1h": 120, "2h": 60, "3h": 40, "4h": 30, "6h": 20, "8h": 15, "12h": 10,
    "1d": 5, "1wk": 1,
}

def _week_to_bars(interval, weeks=1.0):
    b = _BARS_PER_WEEK.get(interval, 120)
    return max(10, int(b * weeks))


# ══════════════════════════════════════════════════════════════════════════════
# Helpers متوافقة مع الواجهة
# ══════════════════════════════════════════════════════════════════════════════
def calculate_indicators(df):
    df = df.copy()
    hl = df["High"] - df["Low"]
    hc = np.abs(df["High"] - df["Close"].shift())
    lc = np.abs(df["Low"] - df["Close"].shift())
    tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    df["ATR"] = tr.rolling(14).mean()
    return df

def calculate_zigzag(df, *a, **kw): return df.copy()
def get_chronological_pivots(df): return []
def _get_max_gap(interval): return 50
def _get_max_pattern_duration(interval): return 200


# ══════════════════════════════════════════════════════════════════════════════
# 🎯 Trend metrics — زمن واحد لكل حجم نافذة
# ══════════════════════════════════════════════════════════════════════════════
def _trend_metrics(closes, W):
    """يعيد slope, r2, move_pct, mean لكل موضع انتهاء."""
    n = len(closes)
    if n < W: return None

    cs = sliding_window_view(closes, W)      # (m, W)
    m = cs.shape[0]

    xs = np.arange(W, dtype=float)
    xs_mean = xs.mean()
    xs_c = xs - xs_mean
    denom = float((xs_c ** 2).sum())

    mean_c = cs.mean(axis=1)
    cs_c = cs - mean_c[:, None]

    slopes = (cs_c * xs_c).sum(axis=1) / denom

    # R²
    predicted = mean_c[:, None] + slopes[:, None] * xs_c[None, :]
    ss_res = ((cs - predicted) ** 2).sum(axis=1)
    ss_tot = (cs_c ** 2).sum(axis=1)
    r2 = np.where(ss_tot > 1e-12, 1.0 - ss_res / ss_tot, 0.0)

    # move
    move_pct = (cs[:, -1] - cs[:, 0]) / np.where(cs[:, 0] > 0, cs[:, 0], 1e-9) * 100

    return {
        "slope": slopes.astype(np.float32),
        "r2": r2.astype(np.float32),
        "move_pct": move_pct.astype(np.float32),
        "mean": mean_c.astype(np.float32),
    }


# ══════════════════════════════════════════════════════════════════════════════
# 🎯 Consolidation metrics
# ══════════════════════════════════════════════════════════════════════════════
def _cons_metrics(highs, lows, opens, closes, W):
    n = len(closes)
    if n < W: return None

    hs = sliding_window_view(highs, W)
    ls = sliding_window_view(lows, W)
    os_ = sliding_window_view(opens, W)
    cs = sliding_window_view(closes, W)

    top = hs.max(axis=1).astype(np.float32)
    bot = ls.min(axis=1).astype(np.float32)
    mean_c = cs.mean(axis=1)
    std_c = cs.std(axis=1, ddof=0)

    # slope
    xs = np.arange(W, dtype=float)
    xs_c = xs - xs.mean()
    denom = float((xs_c ** 2).sum())
    cs_c = cs - mean_c[:, None]
    slopes = (cs_c * xs_c).sum(axis=1) / denom
    slope_pct = np.abs(slopes) / np.where(mean_c > 0, mean_c, 1e-9) * 100

    cv = std_c / np.where(mean_c > 0, mean_c, 1e-9) * 100
    drift = np.abs(cs[:, -1] - cs[:, 0]) / np.where(mean_c > 0, mean_c, 1e-9) * 100

    range_pct = (top - bot) / np.where(bot > 0, bot, 1e-9) * 100

    # touches
    tol = 0.20 / 100.0
    top_thr = top * (1 - tol)
    bot_thr = bot * (1 + tol)
    top_touch = (hs >= top_thr[:, None]).sum(axis=1)
    bot_touch = (ls <= bot_thr[:, None]).sum(axis=1)

    # flat bars
    bodies = np.abs(cs - os_)
    box_h = np.where((top - bot) > 0, top - bot, 1e-9)
    small = (bodies < (box_h[:, None] * 0.40)).sum(axis=1)
    flat_pct = small / W * 100

    # aspect
    aspect = W / np.maximum(range_pct, 0.01)

    return {
        "top": top, "bot": bot,
        "range_pct": range_pct.astype(np.float32),
        "slope_pct": slope_pct.astype(np.float32),
        "cv": cv.astype(np.float32),
        "drift": drift.astype(np.float32),
        "top_touch": top_touch.astype(np.int32),
        "bot_touch": bot_touch.astype(np.int32),
        "flat_pct": flat_pct.astype(np.float32),
        "aspect": aspect.astype(np.float32),
    }


# ══════════════════════════════════════════════════════════════════════════════
# 🎯 DETECTOR
# ══════════════════════════════════════════════════════════════════════════════
def detect_all_patterns(df, interval="1h", symbol=None, **kwargs):
    if df is None or df.empty or len(df) < CONFIG["MIN_BARS_REQUIRED"]:
        return []

    df = df.copy()
    for c in ["Open", "High", "Low", "Close"]:
        if c not in df.columns: return []
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["Open", "High", "Low", "Close"]).reset_index(drop=True)
    if len(df) < CONFIG["MIN_BARS_REQUIRED"]: return []

    highs = df["High"].values.astype(float)
    lows  = df["Low"].values.astype(float)
    opens = df["Open"].values.astype(float)
    closes = df["Close"].values.astype(float)
    n = len(df)

    # ── precompute metrics ─────────────────────────────────────────────
    cons_m = {}
    for W in CONFIG["CONS_WINDOWS"]:
        if W >= n: continue
        cons_m[W] = _cons_metrics(highs, lows, opens, closes, W)

    trend_m = {}
    for W in CONFIG["TREND_WINDOWS"]:
        if W >= n: continue
        trend_m[W] = _trend_metrics(closes, W)

    min_cons = _week_to_bars(interval, CONFIG["CONS_MIN_WEEKS"])
    buf = CONFIG["BRK_BUFFER_PCT"] / 100.0

    patterns = []
    last_signal = -10**9

    # ── main scan ──────────────────────────────────────────────────────
    for i in range(CONFIG["MIN_BARS_REQUIRED"], n):
        if i - last_signal < CONFIG["MIN_BARS_BETWEEN"]:
            continue

        close_bk = closes[i]; open_bk = opens[i]; prev_c = closes[i-1]
        body_pct = abs(close_bk - open_bk) / max(close_bk, 1e-9) * 100
        if body_pct < CONFIG["BRK_MIN_BODY_PCT"]:
            continue

        best = None
        # ── كل أحجام التجميع (الأكبر أولاً) ────────────────────────────
        for W_c in sorted(cons_m.keys(), reverse=True):
            if W_c < min_cons: continue
            start_c = i - W_c
            if start_c < 0: continue
            k_c = start_c
            M_c = cons_m[W_c]
            if k_c >= M_c["top"].shape[0]: continue

            # فحص التسطّح
            if M_c["slope_pct"][k_c] > CONFIG["CONS_MAX_SLOPE_PCT_PER_BAR"]: continue
            if M_c["cv"][k_c] > CONFIG["CONS_MAX_CV"]: continue
            if M_c["drift"][k_c] > CONFIG["CONS_MAX_DRIFT"]: continue
            if M_c["flat_pct"][k_c] < CONFIG["CONS_MIN_FLAT_BARS_PCT"]: continue
            if M_c["aspect"][k_c] < CONFIG["CONS_MIN_ASPECT"]: continue
            if M_c["range_pct"][k_c] < CONFIG["CONS_MIN_RANGE_PCT"]: continue
            if M_c["range_pct"][k_c] > CONFIG["CONS_MAX_RANGE_PCT"]: continue
            if M_c["top_touch"][k_c] < CONFIG["CONS_MIN_TOUCHES_EACH_SIDE"]: continue
            if M_c["bot_touch"][k_c] < CONFIG["CONS_MIN_TOUCHES_EACH_SIDE"]: continue

            box_top = float(M_c["top"][k_c])
            box_bot = float(M_c["bot"][k_c])

            # ── كل أحجام الاتجاه ───────────────────────────────────────
            for W_t in sorted(trend_m.keys(), reverse=True):
                start_t = start_c - W_t
                if start_t < 0: continue
                k_t = start_t
                M_t = trend_m[W_t]
                if k_t >= M_t["slope"].shape[0]: continue

                slope = float(M_t["slope"][k_t])
                r2    = float(M_t["r2"][k_t])
                move  = float(M_t["move_pct"][k_t])
                mean_t = float(M_t["mean"][k_t])

                if r2 < CONFIG["TREND_MIN_R2"]: continue
                if abs(move) < CONFIG["TREND_MIN_MOVE_PCT"]: continue

                slope_pct = abs(slope) / max(mean_t, 1e-9) * 100
                if slope_pct < CONFIG["TREND_MIN_SLOPE_PCT_PER_BAR"]: continue

                trend_dir = "UP" if slope > 0 else "DOWN"

                # ── الكسر في نفس الاتجاه ──────────────────────────────
                direction = None
                if trend_dir == "UP":
                    if (prev_c <= box_top * (1 + buf) and
                        close_bk > box_top * (1 + buf) and
                        close_bk > open_bk):
                        direction = "BUY"
                else:
                    if (prev_c >= box_bot * (1 - buf) and
                        close_bk < box_bot * (1 - buf) and
                        close_bk < open_bk):
                        direction = "SELL"

                if direction is None: continue

                best = (W_c, W_t, start_c, start_t, box_top, box_bot,
                        direction, trend_dir, move, M_c, M_t, k_c, k_t)
                break
            if best: break

        if best is None: continue

        pattern = _build_pattern(df, i, best, body_pct, closes)
        if pattern:
            patterns.append(pattern)
            last_signal = i

    patterns.sort(key=lambda p: p["end_pos"])
    return patterns


# ══════════════════════════════════════════════════════════════════════════════
# 🎯 Build pattern
# ══════════════════════════════════════════════════════════════════════════════
def _build_pattern(df, i, best, body_pct, closes):
    (W_c, W_t, start_c, start_t, box_top, box_bot,
     direction, trend_dir, trend_move_pct, M_c, M_t, k_c, k_t) = best

    entry = float(closes[i])
    end_c = i - 1

    # SL
    sl_buf = CONFIG["SL_BUFFER_PCT"] / 100.0
    if direction == "BUY":
        sl = box_bot * (1 - sl_buf)
        if sl >= entry: return None
        risk = entry - sl
    else:
        sl = box_top * (1 + sl_buf)
        if sl <= entry: return None
        risk = sl - entry
    if risk <= 0: return None

    # TP = حجم الموجة السابقة
    trend_dist = abs(trend_move_pct) / 100.0 * entry
    if trend_dist < 0.5 * risk:
        trend_dist = 2.0 * risk
    tp = entry + trend_dist if direction == "BUY" else entry - trend_dist

    rr = abs(tp - entry) / risk
    if rr < CONFIG["MIN_RR"]: return None

    bias = "Bullish" if direction == "BUY" else "Bearish"

    # nodes on consolidation
    highs = df["High"].values
    lows  = df["Low"].values

    tol_vis = 0.20 / 100.0 * 2.5
    seg_h = highs[start_c:end_c + 1]
    seg_l = lows[start_c:end_c + 1]

    top_hits = np.where(seg_h >= box_top * (1 - tol_vis))[0]
    bot_hits = np.where(seg_l <= box_bot * (1 + tol_vis))[0]

    top_nodes = [(int(start_c + p), float(seg_h[p])) for p in top_hits]
    bot_nodes = [(int(start_c + p), float(seg_l[p])) for p in bot_hits]

    top_line = [(int(start_c), box_top), (int(end_c), box_top)]
    bot_line = [(int(start_c), box_bot), (int(end_c), box_bot)]

    nodes = [(int(i), entry)]

    # trend line
    trend_start_pos = start_t
    trend_end_pos = end_c if start_c == 0 else start_c - 1
    if trend_end_pos <= trend_start_pos:
        trend_end_pos = start_c
    trend_line = [
        (int(trend_start_pos), float(closes[trend_start_pos])),
        (int(trend_end_pos),   float(closes[trend_end_pos])),
    ]

    # arrow
    arrow_len = max(8, (end_c - start_c) // 3)
    x1_pos = min(i + arrow_len, len(df) - 1)
    arrow = {
        "x0": int(i), "y0": entry,
        "x1": int(x1_pos), "y1": tp,
        "direction": direction,
    }

    box_data = {
        "x_start": int(start_c),
        "x_end":   int(end_c),
        "high":    float(box_top),
        "low":     float(box_bot),
    }

    pattern = {
        "name": "Trend → Consolidation → Continuation",
        "pattern": f"{trend_dir} Trend → Flat {W_c}bars → {direction} Breakout",
        "bias": bias,
        "direction": direction,
        "trend_direction": trend_dir,
        "entry": round(entry, 5),
        "entry_trigger": round(entry, 5),
        "sl": round(sl, 5),
        "tp": round(tp, 5),
        "SL": round(sl, 5),
        "TP": round(tp, 5),
        "Entry": round(entry, 5),
        "R:R": round(rr, 2),
        "tp_source": "trend_size",
        "trend_distance": round(trend_dist, 5),
        "nodes": nodes,
        "top_nodes": top_nodes,
        "bot_nodes": bot_nodes,
        "top_line": top_line,
        "bot_line": bot_line,
        "trend_line": trend_line,
        "arrow": arrow,
        "consolidation_box": box_data,
        "resistance": round(box_top, 5),
        "support": round(box_bot, 5),
        "level_price": round(box_top if direction == "BUY" else box_bot, 5),
        "channel_start": int(start_c),
        "channel_end": int(end_c),
        "channel_duration_bars": int(W_c),
        "channel_range_pct": round(float(M_c["range_pct"][k_c]), 3),
        "neckline_start_idx": int(start_c),
        "neckline_end_idx": int(i),
        "end_pos": int(i),
        "Entry Conditions": (
            f"Trend {trend_dir} {trend_move_pct:+.2f}% ({W_t}bars, R²={M_t['r2'][k_t]:.2f}) "
            f"→ flat {W_c}bars → {direction} breakout"
        ),
        "consol_high": round(box_top, 5),
        "consol_low": round(box_bot, 5),
        "consol_bars": int(W_c),
        "consol_range_pct": round(float(M_c["range_pct"][k_c]), 3),
        "consol_stability_pct": 100.0,
        "breakout_body_pct": round(body_pct, 3),
        "trend_move_pct": round(trend_move_pct, 3),
        "trend_bars": int(W_t),
        "trend_r2": round(float(M_t["r2"][k_t]), 3),
        "top_touches": int(M_c["top_touch"][k_c]),
        "bot_touches": int(M_c["bot_touch"][k_c]),
        "cons_slope_pct": round(float(M_c["slope_pct"][k_c]), 4),
        "cons_cv_pct": round(float(M_c["cv"][k_c]), 4),
        "cons_drift_pct": round(float(M_c["drift"][k_c]), 4),
        "cons_flat_bars_pct": round(float(M_c["flat_pct"][k_c]), 2),
        "cons_aspect": round(float(M_c["aspect"][k_c]), 2),
    }

    pattern.update(simulate_trade_outcome(pattern, df))
    return pattern


# ══════════════════════════════════════════════════════════════════════════════
# Simulation
# ══════════════════════════════════════════════════════════════════════════════
def simulate_trade_outcome(pattern, df):
    bias = pattern["bias"]; entry = float(pattern["entry"])
    sl = float(pattern["sl"]); tp = float(pattern["tp"])
    end_idx = pattern["neckline_end_idx"]

    stats = {
        "Result": "OPEN", "Head Result": "OPEN",
        "progress_ratio": 0.0, "candles_to_exit": 0,
        "exit_idx": None, "exit_price": None,
        "Entry Date": None, "Exit Date": None,
        "Max Reach %": 0.0, "SL Safety %": 0.0,
        "Breakeven Activated": False, "Breakeven Exit": False,
        "Trailing Stage": 0, "Initial SL": sl, "Final SL": sl,
        "Loss Category": None, "Pattern Duration": 50,
        "Timeout Used": CONFIG["MAX_TIMEOUT_BARS"],
    }

    if end_idx < 0 or end_idx >= len(df): return stats
    post = df.iloc[end_idx:]
    if len(post) <= 1: return stats

    stats["Entry Date"] = str(df.index[end_idx])
    total_tp = abs(tp - entry); total_sl = abs(sl - entry)
    max_fav = 0.0; max_adv = 0.0

    highs_arr = post["High"].values.astype(float)
    lows_arr = post["Low"].values.astype(float)
    closes_arr = post["Close"].values.astype(float)
    dates_arr = post.index.values
    is_bear = (bias == "Bearish")

    for i in range(1, len(post)):
        high = highs_arr[i]; low = lows_arr[i]
        if is_bear:
            fav = max(0.0, entry - low); adv = max(0.0, high - entry)
        else:
            fav = max(0.0, high - entry); adv = max(0.0, entry - low)
        if total_tp > 0: max_fav = max(max_fav, fav / total_tp * 100)
        if total_sl > 0: max_adv = max(max_adv, adv / total_sl * 100)
        hit_sl = (high >= sl) if is_bear else (low <= sl)
        hit_tp = (low <= tp) if is_bear else (high >= tp)
        if hit_sl:
            stats["Result"] = "LOSS"; stats["Head Result"] = "LOSS"
            r = max_fav
            if r < 5: stats["Loss Category"] = "immediate_rejection"
            elif r < 30: stats["Loss Category"] = "early_reversal"
            elif r < 70: stats["Loss Category"] = "mid_reversal"
            else: stats["Loss Category"] = "late_reversal"
            stats["exit_idx"] = dates_arr[i]; stats["exit_price"] = sl
            stats["candles_to_exit"] = i; stats["Exit Date"] = str(dates_arr[i]); break
        if hit_tp:
            stats["Result"] = "WIN"; stats["Head Result"] = "WIN"
            stats["Loss Category"] = "success"
            stats["exit_idx"] = dates_arr[i]; stats["exit_price"] = tp
            stats["candles_to_exit"] = i; stats["Exit Date"] = str(dates_arr[i]); break
        if i >= CONFIG["MAX_TIMEOUT_BARS"]:
            stats["Result"] = "TIMEOUT"; stats["Head Result"] = "TIMEOUT"
            stats["Loss Category"] = "timeout"
            stats["exit_idx"] = dates_arr[i]; stats["exit_price"] = float(closes_arr[i])
            stats["candles_to_exit"] = i; stats["Exit Date"] = str(dates_arr[i]); break
    else:
        stats["candles_to_exit"] = max(0, len(post) - 1)
        stats["Exit Date"] = str(dates_arr[-1]); stats["Loss Category"] = "open"

    stats["Max Reach %"] = round(max_fav, 1)
    stats["SL Safety %"] = round(100 - max_adv, 1) if max_adv <= 100 else 0.0
    stats["Final SL"] = sl
    if stats["Result"] == "WIN": stats["progress_ratio"] = 100.0
    elif stats["Result"] in ("LOSS", "BREAKEVEN"): stats["progress_ratio"] = 0.0
    return stats


# ══════════════════════════════════════════════════════════════════════════════
# run_full_analysis
# ══════════════════════════════════════════════════════════════════════════════
def run_full_analysis(df, interval="1h", symbol=None):
    empty = {
        "df": df, "symbol": symbol or "N/A",
        "signal": "WAITING", "pattern": "NO PATTERN DETECTED",
        "bias": "Neutral", "entry": None, "sl": None, "tp": None,
        "nodes": [], "pattern_nodes": [], "all_patterns": [], "error": None,
    }
    if df is None or df.empty: return empty

    df = df.copy()
    for c in ["Open", "High", "Low", "Close"]:
        if c not in df.columns:
            empty["error"] = f"Missing: {c}"; return empty
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["Open", "High", "Low", "Close"])
    if len(df) < CONFIG["MIN_BARS_REQUIRED"]:
        empty["error"] = f"Insufficient: {len(df)}"; return empty

    dfa = df.tail(1200).copy().reset_index(drop=True)
    pats = detect_all_patterns(dfa, interval=interval, symbol=symbol)

    if not pats:
        empty["df"] = dfa
        return empty

    latest = pats[-1]
    signal = "STRONG BUY" if latest["bias"] == "Bullish" else "STRONG SELL"

    return {
        "df": dfa, "symbol": symbol or "N/A",
        "signal": signal,
        "pattern": latest["pattern"],
        "bias": latest["bias"],
        "entry": latest["entry"],
        "entry_trigger": latest["entry_trigger"],
        "sl": latest["sl"], "tp": latest["tp"],
        "nodes": latest.get("nodes", []),
        "pattern_nodes": latest.get("nodes", []),
        "top_nodes": latest.get("top_nodes", []),
        "bot_nodes": latest.get("bot_nodes", []),
        "top_line": latest.get("top_line"),
        "bot_line": latest.get("bot_line"),
        "trend_line": latest.get("trend_line"),
        "arrow": latest.get("arrow"),
        "consolidation_box": latest.get("consolidation_box"),
        "resistance": latest.get("resistance"),
        "support": latest.get("support"),
        "all_patterns": pats,
        "match": 100.0,
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
        if c not in df.columns: return []
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["Open", "High", "Low", "Close"])
    if len(df) < CONFIG["MIN_BARS_REQUIRED"]: return []

    pats = detect_all_patterns(df, interval=interval, symbol=symbol)
    trades = []
    for p in pats:
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
            "R:R": p.get("R:R"),
            "Entry Date": p.get("Entry Date"), "Exit Date": p.get("Exit Date"),
            "Exit Price": p.get("exit_price"),
            "time": p.get("Entry Date"), "close_time": p.get("Exit Date"),
            "Max Reach %": p.get("Max Reach %", 0.0),
            "SL Safety %": p.get("SL Safety %", 0.0),
            "Entry Conditions": p.get("Entry Conditions", ""),
            "nodes": p.get("nodes", []),
            "top_nodes": p.get("top_nodes", []),
            "bot_nodes": p.get("bot_nodes", []),
            "top_line": p.get("top_line"),
            "bot_line": p.get("bot_line"),
            "trend_line": p.get("trend_line"),
            "arrow": p.get("arrow"),
            "consolidation_box": p.get("consolidation_box"),
            "candles_to_exit": p.get("candles_to_exit", 0),
            "progress_ratio": p.get("progress_ratio", 0.0),
            "neckline_end_idx": p["neckline_end_idx"],
            "Loss Category": p.get("Loss Category"),
            "resistance": p.get("resistance"),
            "support":   p.get("support"),
            "channel_start": p.get("channel_start"),
            "channel_end":   p.get("channel_end"),
            "channel_duration_bars": p.get("channel_duration_bars"),
            "channel_range_pct": p.get("channel_range_pct"),
            "consol_high": p.get("consol_high"),
            "consol_low":  p.get("consol_low"),
            "consol_bars": p.get("consol_bars"),
            "consol_range_pct": p.get("consol_range_pct"),
            "breakout_body_pct": p.get("breakout_body_pct"),
            "trend_direction": p.get("trend_direction"),
            "trend_move_pct": p.get("trend_move_pct"),
            "trend_bars": p.get("trend_bars"),
            "trend_r2": p.get("trend_r2"),
            "top_touches": p.get("top_touches"),
            "bot_touches": p.get("bot_touches"),
            "cons_slope_pct": p.get("cons_slope_pct"),
            "cons_cv_pct": p.get("cons_cv_pct"),
            "cons_drift_pct": p.get("cons_drift_pct"),
            "cons_flat_bars_pct": p.get("cons_flat_bars_pct"),
            "cons_aspect": p.get("cons_aspect"),
        })
    return trades


def detect_all_head_shoulders(*a, **kw): return []


# ══════════════════════════════════════════════════════════════════════════════
# diagnose_filters
# ══════════════════════════════════════════════════════════════════════════════
def diagnose_filters(df, interval="1h", symbol=None):
    res = {
        "error": None, "total_raw_candidates": 0, "final_count": 0,
        "stages": {}, "smart_diagnosis": {}, "recommendations": [],
        "trade_analysis": [], "rejection_samples": {},
    }
    if df is None or df.empty or len(df) < CONFIG["MIN_BARS_REQUIRED"]:
        res["error"] = "بيانات غير كافية"; return res
    df = df.copy()
    for c in ["Open", "High", "Low", "Close"]:
        if c not in df.columns:
            res["error"] = f"مفقود: {c}"; return res
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["Open", "High", "Low", "Close"])

    trades = backtest_strategy(df, interval=interval, symbol=symbol)
    res["final_count"] = len(trades)
    res["total_raw_candidates"] = len(trades)

    wins = [t for t in trades if "WIN" in str(t.get("Result", "")).upper()]
    losses = [t for t in trades if "LOSS" in str(t.get("Result", "")).upper()]
    timeouts = [t for t in trades if "TIMEOUT" in str(t.get("Result", "")).upper()]

    closed = len(wins) + len(losses)
    wr = round(len(wins) / closed * 100, 1) if closed else 0

    if closed == 0: verdict = "لا توجد صفقات كافية"
    elif wr >= 70: verdict = f"ممتاز — {wr}%"
    elif wr >= 50: verdict = f"جيد — {wr}%"
    elif wr >= 35: verdict = f"متوسط — {wr}%"
    else: verdict = f"ضعيف — {wr}%"

    res["smart_diagnosis"] = {
        "verdict": verdict,
        "win_breakdown": {"total_wins": len(wins)},
        "loss_breakdown": {
            "immediate_rejection": 0, "early_reversal": len(losses),
            "mid_reversal": 0, "late_reversal": 0,
            "unavoidable": 0, "avoidable": len(losses),
        },
        "action_plan": [f"🟢 WIN: {len(wins)} | ❌ LOSS: {len(losses)} | ⏰ TIMEOUT: {len(timeouts)}"],
    }
    return res


if __name__ == "__main__":
    print("ENGINE.PY — Trend → Consolidation → Continuation v22")
    print(f"Trend: R² ≥ {CONFIG['TREND_MIN_R2']} | move ≥ {CONFIG['TREND_MIN_MOVE_PCT']}%")
    print(f"Cons: slope ≤ {CONFIG['CONS_MAX_SLOPE_PCT_PER_BAR']}%/bar | CV ≤ {CONFIG['CONS_MAX_CV']}% | aspect ≥ {CONFIG['CONS_MIN_ASPECT']}")
    print(f"Breakout: body ≥ {CONFIG['BRK_MIN_BODY_PCT']}% in trend direction")
    print(f"TP = trend size | SL on opposite side")
