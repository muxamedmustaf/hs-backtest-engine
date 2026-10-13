# -*- coding: utf-8 -*-
"""
ENGINE.PY — Horizontal Rectangle Reversal (v19)
=================================================
🎯 الجديد في v19:
  • الخطوط عند وسيط أعلى/أدنى 15% من القمم/القيعان (cluster center)
  • اللمسات تُحسب حول الـ cluster لا حول أقصى قمة
  • الخط يمر عبر تجمّع البيفوتات الفعلي (يُلامس الشموع)
  • TP = حجم الانطلاقة قبل التصحيح
  • رسم علامات على القمم/القيعان الحقيقية
"""
import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view


# ══════════════════════════════════════════════════════════════════════════════
# CONFIG
# ══════════════════════════════════════════════════════════════════════════════
CONFIG = {
    "WINDOW_SIZES": [60, 90, 130, 180, 250, 340, 460],

    "MIN_TOP_TOUCHES": 3,
    "MIN_BOT_TOUCHES": 3,
    "TOUCH_TOLERANCE_PCT": 0.20,
    "FLATNESS_MAX_PCT": 0.45,

    "MIN_RANGE_PCT": 0.80,
    "MAX_RANGE_PCT": 5.00,

    "MIN_BARS_PER_RANGE_PCT": 30,

    "MAX_SLOPE_PCT_PER_BAR": 0.006,
    "MAX_STD_CV_PCT":        0.35,
    "MAX_DRIFT_PCT":         0.45,
    "MIN_FLAT_BARS_PCT":     0.70,

    "MIN_CONSOL_WEEKS": 1.0,

    "IMPULSE_LOOKBACK": 30,
    "MIN_IMPULSE_PCT": 0.80,

    "BREAKOUT_BUFFER_PCT": 0.05,
    "MIN_BREAKOUT_BODY_PCT": 0.08,

    "SL_BUFFER_PCT": 0.05,
    "MIN_RR_ACCEPTED": 1.2,
    "TP_RR": 3.0,

    "MIN_BARS_BETWEEN": 15,
    "MAX_TIMEOUT_BARS": 300,
    "VOLUME_MA_PERIOD": 20,
    "MIN_BARS_REQUIRED": 250,

    # 🆕 نسبة القمم/القيعان المُستخدمة لحساب الـ cluster
    "CLUSTER_TOP_PCT": 0.15,
}


_BARS_PER_WEEK = {
    "1m": 7200, "2m": 3600, "3m": 2400, "4m": 1800, "5m": 1440,
    "10m": 720, "15m": 480, "30m": 240, "45m": 160,
    "1h": 120, "2h": 60, "3h": 40, "4h": 30, "6h": 20, "8h": 15, "12h": 10,
    "1d": 5, "2d": 3, "3d": 2, "1wk": 1, "1mo": 1,
}

def _week_to_bars(interval, weeks=1.0):
    b = _BARS_PER_WEEK.get(interval, 120)
    return max(10, int(b * weeks))


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
    return {"1m": 120, "5m": 50, "15m": 30, "30m": 25, "1h": 20, "4h": 15, "1d": 10}.get(interval, 50)

def _get_max_pattern_duration(interval):
    return {"1m": 600, "5m": 200, "15m": 150, "30m": 120, "1h": 100, "4h": 80, "1d": 60}.get(interval, 200)

def _days_to_bars(days, interval):
    bpd = {"1m": 1440, "5m": 288, "15m": 96, "30m": 48, "1h": 24, "4h": 6, "1d": 1}.get(interval, 24)
    return max(3, int(round(bpd * days)))


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

def calculate_zigzag(df, *a, **kw): return df.copy()
def get_chronological_pivots(df): return []


# ══════════════════════════════════════════════════════════════════════════════
# 🆕 _window_metrics — cluster-based lines
# ══════════════════════════════════════════════════════════════════════════════
def _window_metrics(highs, lows, opens, closes, W, tol, impulse_bars):
    n = len(closes)
    if n < W + impulse_bars + 2: return None

    hs = sliding_window_view(highs, W); ls = sliding_window_view(lows, W)
    os_ = sliding_window_view(opens, W); cs = sliding_window_view(closes, W)
    m = hs.shape[0]

    win_high = hs.max(axis=1)
    win_low  = ls.min(axis=1)
    mean_c = cs.mean(axis=1)
    std_c = cs.std(axis=1, ddof=0)

    # slope
    xs = np.arange(W, dtype=float); xs_c = xs - xs.mean()
    denom = float((xs_c ** 2).sum())
    cs_c = cs - mean_c[:, None]
    slopes = (cs_c * xs_c).sum(axis=1) / denom
    slope_pct = np.abs(slopes) / np.where(mean_c > 0, mean_c, 1e-9) * 100

    cv = std_c / np.where(mean_c > 0, mean_c, 1e-9) * 100
    drift = np.abs(cs[:, -1] - cs[:, 0]) / np.where(mean_c > 0, mean_c, 1e-9) * 100

    # ═══ 🆕 cluster: وسيط أعلى/أدنى 15% من القمم/القيعان ═══
    hs_sorted = np.sort(hs, axis=1)
    ls_sorted = np.sort(ls, axis=1)
    n_peak = max(1, int(W * CONFIG["CLUSTER_TOP_PCT"]))

    top_cluster = np.median(hs_sorted[:, -n_peak:], axis=1)  # وسيط أعلى القمم
    bot_cluster = np.median(ls_sorted[:, :n_peak], axis=1)   # وسيط أدنى القيعان

    # touches حول الـ cluster (بمدى أوسع قليلاً)
    touch_range = tol * 3.0
    top_thr_lo = top_cluster * (1.0 - touch_range)
    top_thr_hi = top_cluster * (1.0 + touch_range)
    bot_thr_lo = bot_cluster * (1.0 - touch_range)
    bot_thr_hi = bot_cluster * (1.0 + touch_range)

    top_touch = ((hs >= top_thr_lo[:, None]) & (hs <= top_thr_hi[:, None])).sum(axis=1)
    bot_touch = ((ls >= bot_thr_lo[:, None]) & (ls <= bot_thr_hi[:, None])).sum(axis=1)

    # flatness: مدى القمم/القيعان حول الـ cluster
    top_masked = np.where((hs >= top_thr_lo[:, None]) & (hs <= top_thr_hi[:, None]), hs, np.nan)
    bot_masked = np.where((ls >= bot_thr_lo[:, None]) & (ls <= bot_thr_hi[:, None]), ls, np.nan)
    with np.errstate(invalid="ignore"):
        top_max = np.nanmax(top_masked, axis=1); top_min = np.nanmin(top_masked, axis=1)
        bot_max = np.nanmax(bot_masked, axis=1); bot_min = np.nanmin(bot_masked, axis=1)

    top_flat_pct = np.where(top_cluster > 0, (top_max - top_min) / top_cluster * 100, np.inf)
    bot_flat_pct = np.where(bot_cluster > 0, (bot_max - bot_min) / bot_cluster * 100, np.inf)

    # range_pct: يُحسب من الـ clusters (وليس من القمة/القاع المطلق)
    range_pct = np.where(bot_cluster > 0, (top_cluster - bot_cluster) / bot_cluster * 100, np.inf)

    # flat bars: نسبة الشموع بجسم صغير
    bodies = np.abs(cs - os_)
    box_h = np.where((top_cluster - bot_cluster) > 0, top_cluster - bot_cluster, 1e-9)
    small_bodies = (bodies < (box_h[:, None] * 0.35)).sum(axis=1)
    flat_bars_pct = small_bodies / W * 100

    # شكل: عرض ÷ ارتفاع %
    bars_per_pct = W / np.maximum(range_pct, 0.01)

    # impulse قبل النافذة
    impulse_pct = np.full(m, 0.0, dtype=np.float32)
    for k in range(m):
        base_idx = k - 1
        t_start = base_idx - impulse_bars
        if t_start < 0: continue
        p0 = closes[t_start]; p1 = closes[base_idx]
        if p0 > 0: impulse_pct[k] = (p1 - p0) / p0 * 100

    return {
        "top": win_high, "bottom": win_low,
        "top_cluster": top_cluster,
        "bot_cluster": bot_cluster,
        "range_pct": range_pct,
        "top_touch": top_touch.astype(np.int32),
        "bot_touch": bot_touch.astype(np.int32),
        "top_flat": top_flat_pct, "bot_flat": bot_flat_pct,
        "slope_pct": slope_pct, "cv": cv, "drift": drift,
        "flat_bars_pct": flat_bars_pct,
        "bars_per_pct": bars_per_pct,
        "impulse": impulse_pct, "W": W,
    }


# ══════════════════════════════════════════════════════════════════════════════
# DETECTOR
# ══════════════════════════════════════════════════════════════════════════════
def detect_all_patterns(df, interval="1h", symbol=None, **kwargs):
    if df is None or df.empty or len(df) < CONFIG["MIN_BARS_REQUIRED"]: return []

    df = df.copy()
    for c in ["Open", "High", "Low", "Close"]:
        if c not in df.columns: return []
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["Open", "High", "Low", "Close"]).reset_index(drop=True)
    if len(df) < CONFIG["MIN_BARS_REQUIRED"]: return []

    df = calculate_indicators(df)
    highs = df["High"].values.astype(float); lows = df["Low"].values.astype(float)
    opens = df["Open"].values.astype(float); closes = df["Close"].values.astype(float)
    n = len(df)
    tol = CONFIG["TOUCH_TOLERANCE_PCT"] / 100.0
    buf = CONFIG["BREAKOUT_BUFFER_PCT"] / 100.0
    imp_bars = CONFIG["IMPULSE_LOOKBACK"]

    min_bars_required = _week_to_bars(interval, CONFIG["MIN_CONSOL_WEEKS"])

    # metrics by window
    metrics_by_W = {}
    for W in CONFIG["WINDOW_SIZES"]:
        if W < min_bars_required: continue
        if W + imp_bars + 5 > n: continue
        M = _window_metrics(highs, lows, opens, closes, W, tol, imp_bars)
        if M is not None:
            metrics_by_W[W] = M

    windows_desc = sorted(metrics_by_W.keys(), reverse=True)

    patterns = []
    last_signal_pos = -10**9

    for i in range(CONFIG["MIN_BARS_REQUIRED"], n):
        if i - last_signal_pos < CONFIG["MIN_BARS_BETWEEN"]:
            continue

        close_bk = closes[i]; open_bk = opens[i]
        prev_c = closes[i - 1]
        body_pct = abs(close_bk - open_bk) / max(close_bk, 1e-9) * 100
        if body_pct < CONFIG["MIN_BREAKOUT_BODY_PCT"]:
            continue

        best_match = None
        for W in windows_desc:
            M = metrics_by_W[W]
            k = i - W
            if k < 0 or k >= len(M["top"]):
                continue

            range_pct = float(M["range_pct"][k])
            top_touch = int(M["top_touch"][k])
            bot_touch = int(M["bot_touch"][k])
            top_flat = float(M["top_flat"][k])
            bot_flat = float(M["bot_flat"][k])
            slope_pct = float(M["slope_pct"][k])
            cv = float(M["cv"][k])
            drift = float(M["drift"][k])
            flat_bars_pct = float(M["flat_bars_pct"][k])
            bars_per_pct = float(M["bars_per_pct"][k])
            impulse = float(M["impulse"][k])

            if not (CONFIG["MIN_RANGE_PCT"] <= range_pct <= CONFIG["MAX_RANGE_PCT"]): continue
            if top_touch < CONFIG["MIN_TOP_TOUCHES"]: continue
            if bot_touch < CONFIG["MIN_BOT_TOUCHES"]: continue
            if top_flat > CONFIG["FLATNESS_MAX_PCT"]: continue
            if bot_flat > CONFIG["FLATNESS_MAX_PCT"]: continue
            if slope_pct > CONFIG["MAX_SLOPE_PCT_PER_BAR"]: continue
            if cv > CONFIG["MAX_STD_CV_PCT"]: continue
            if drift > CONFIG["MAX_DRIFT_PCT"]: continue
            if flat_bars_pct < CONFIG["MIN_FLAT_BARS_PCT"]: continue
            if bars_per_pct < CONFIG["MIN_BARS_PER_RANGE_PCT"]: continue
            if abs(impulse) < CONFIG["MIN_IMPULSE_PCT"]: continue

            best_match = (W, k, M)
            break

        if best_match is None:
            continue

        W, k, M = best_match
        end_window = int(k + W - 1)
        if end_window != i - 1:
            continue

        # 🆕 استخدم الـ cluster (مستوى المقاومة/الدعم الفعلي)
        box_high = float(M["top_cluster"][k])
        box_low  = float(M["bot_cluster"][k])
        impulse = float(M["impulse"][k])
        up_thr = box_high * (1 + buf); down_thr = box_low * (1 - buf)

        direction = None
        if prev_c <= up_thr and close_bk > up_thr and close_bk > open_bk:
            direction = "BUY"
        elif prev_c >= down_thr and close_bk < down_thr and close_bk < open_bk:
            direction = "SELL"
        if direction is None: continue

        info = {
            "top": box_high, "bottom": box_low,
            "range_pct": float(M["range_pct"][k]),
            "top_touch": int(M["top_touch"][k]),
            "bot_touch": int(M["bot_touch"][k]),
            "top_flat": float(M["top_flat"][k]),
            "bot_flat": float(M["bot_flat"][k]),
            "slope_pct": float(M["slope_pct"][k]),
            "cv": float(M["cv"][k]),
            "drift": float(M["drift"][k]),
            "flat_bars_pct": float(M["flat_bars_pct"][k]),
            "bars_per_pct": float(M["bars_per_pct"][k]),
            "impulse_pct": impulse,
            "start": int(k), "end": end_window, "W": W,
        }
        pattern = _build_pattern(df, i, info, direction, body_pct, highs, lows, closes)
        if pattern:
            patterns.append(pattern)
            last_signal_pos = i

    patterns.sort(key=lambda p: p["end_pos"])
    return patterns


# ══════════════════════════════════════════════════════════════════════════════
# _build_pattern — TP = impulse size
# ══════════════════════════════════════════════════════════════════════════════
def _build_pattern(df, idx, info, direction, body_pct, highs, lows, closes):
    entry = float(closes[idx])
    box_high = info["top"]; box_low = info["bottom"]
    sl_buf = CONFIG["SL_BUFFER_PCT"] / 100.0

    # SL
    if direction == "BUY":
        sl = box_low * (1 - sl_buf)
        if sl >= entry: return None
        risk = entry - sl
        if risk <= 0: return None
    else:
        sl = box_high * (1 + sl_buf)
        if sl <= entry: return None
        risk = sl - entry
        if risk <= 0: return None

    # 🆕 TP = حجم الانطلاقة
    impulse_dist = abs(info["impulse_pct"]) / 100.0 * entry
    if impulse_dist < 0.5 * risk:
        impulse_dist = 2.0 * risk

    tp = entry + impulse_dist if direction == "BUY" else entry - impulse_dist

    # فلتر R:R
    rr = abs(tp - entry) / risk
    if rr < CONFIG["MIN_RR_ACCEPTED"]:
        return None

    bias = "Bullish" if direction == "BUY" else "Bearish"
    start_p = info["start"]; end_p = info["end"]

    # 🆕 نقاط اللمسات — عند السعر الفعلي لكل قمة/قاع قريب من الخط
    tol_vis = CONFIG["TOUCH_TOLERANCE_PCT"] / 100.0 * 3.0
    seg_h = highs[start_p:end_p + 1]; seg_l = lows[start_p:end_p + 1]

    top_hits = np.where(np.abs(seg_h - box_high) <= box_high * tol_vis)[0]
    bot_hits = np.where(np.abs(seg_l - box_low)  <= box_low  * tol_vis)[0]

    # النقاط عند السعر الفعلي للشموع (تُلامس الشارت)
    top_nodes = [(int(start_p + p), float(seg_h[p])) for p in top_hits]
    bot_nodes = [(int(start_p + p), float(seg_l[p])) for p in bot_hits]

    # خطان أفقيان عند الـ cluster
    top_line = [(int(start_p), box_high), (int(end_p), box_high)]
    bot_line = [(int(start_p), box_low),  (int(end_p), box_low)]

    nodes = [(int(idx), entry)]

    # سهم
    arrow_len = max(8, (end_p - start_p) // 3)
    x1_pos = min(idx + arrow_len, len(df) - 1)
    arrow = {"x0": int(idx), "y0": entry, "x1": int(x1_pos), "y1": tp, "direction": direction}

    # المستطيل
    box_data = {"x_start": int(start_p), "x_end": int(end_p),
                "high": float(box_high), "low": float(box_low)}

    pattern = {
        "name": "Horizontal Rectangle Reversal",
        "pattern": f"Rect {direction} · T{info['top_touch']}/B{info['bot_touch']} · W{info['W']}bars · R:R {rr:.2f}",
        "bias": bias, "direction": direction,
        "match": float(min(100, 55 + (info["top_touch"] + info["bot_touch"]) * 6)),
        "entry": round(entry, 5), "entry_trigger": round(entry, 5),
        "sl": round(sl, 5), "tp": round(tp, 5),
        "SL": round(sl, 5), "TP": round(tp, 5), "Entry": round(entry, 5),
        "R:R": round(rr, 2),
        "tp_source": "impulse_size",
        "impulse_distance": round(impulse_dist, 5),
        "nodes": nodes, "top_nodes": top_nodes, "bot_nodes": bot_nodes,
        "top_line": top_line, "bot_line": bot_line, "arrow": arrow,
        "consolidation_box": box_data,
        "resistance": round(box_high, 5), "support": round(box_low, 5),
        "level_price": round(box_high if direction == "BUY" else box_low, 5),
        "channel_start": int(start_p), "channel_end": int(end_p),
        "channel_duration_bars": int(info["W"]),
        "channel_range_pct": round(info["range_pct"], 3),
        "neckline_start_idx": int(start_p), "neckline_end_idx": int(idx), "end_pos": int(idx),
        "Entry Conditions": f"W{info['W']} rect · TP=impulse {info['impulse_pct']:+.2f}% · R:R {rr:.2f}",
        "consol_high": round(box_high, 5), "consol_low": round(box_low, 5),
        "consol_bars": int(info["W"]), "consol_range_pct": round(info["range_pct"], 3),
        "consol_stability_pct": 100.0,
        "breakout_body_pct": round(body_pct, 3),
        "top_touches": info["top_touch"], "bot_touches": info["bot_touch"],
        "top_flatness_pct": round(info["top_flat"], 4),
        "bot_flatness_pct": round(info["bot_flat"], 4),
        "impulse_pct": round(info["impulse_pct"], 3),
        "slope_pct": round(info["slope_pct"], 4),
        "cv_pct": round(info["cv"], 4),
        "drift_pct": round(info["drift"], 4),
        "flat_bars_pct": round(info["flat_bars_pct"], 2),
        "bars_per_pct": round(info["bars_per_pct"], 2),
    }

    pattern.update(simulate_trade_outcome(pattern, df))
    return pattern


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

    highs_arr = post["High"].values.astype(float); lows_arr = post["Low"].values.astype(float)
    closes_arr = post["Close"].values.astype(float); dates_arr = post.index.values
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
    elif stats["Result"] in ["LOSS", "BREAKEVEN"]: stats["progress_ratio"] = 0.0
    return stats


def run_full_analysis(df, interval="1h", symbol=None):
    default_empty = {
        "df": df, "symbol": symbol or "N/A",
        "signal": "WAITING", "pattern": "NO PATTERN DETECTED",
        "bias": "Neutral", "entry": None, "sl": None, "tp": None,
        "nodes": [], "pattern_nodes": [], "all_patterns": [], "error": None,
    }
    if df is None or df.empty: return default_empty
    df = df.copy()
    for c in ["Open", "High", "Low", "Close"]:
        if c not in df.columns:
            default_empty["error"] = f"Missing column: {c}"; return default_empty
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["Open", "High", "Low", "Close"])
    if len(df) < CONFIG["MIN_BARS_REQUIRED"]:
        default_empty["error"] = f"Insufficient data: {len(df)}"; return default_empty

    df_active = df.tail(1200).copy().reset_index(drop=True)
    all_patterns = detect_all_patterns(df_active, interval=interval, symbol=symbol)

    if not all_patterns:
        default_empty["df"] = df_active; return default_empty

    latest = all_patterns[-1]
    signal = "STRONG BUY" if latest["bias"] == "Bullish" else "STRONG SELL"

    return {
        "df": df_active, "symbol": symbol or "N/A",
        "signal": signal, "pattern": latest["pattern"], "bias": latest["bias"],
        "entry": latest["entry"], "entry_trigger": latest["entry_trigger"],
        "sl": latest["sl"], "tp": latest["tp"],
        "nodes": latest.get("nodes", []),
        "pattern_nodes": latest.get("nodes", []),
        "top_nodes": latest.get("top_nodes", []),
        "bot_nodes": latest.get("bot_nodes", []),
        "top_line": latest.get("top_line"), "bot_line": latest.get("bot_line"),
        "arrow": latest.get("arrow"),
        "consolidation_box": latest.get("consolidation_box"),
        "resistance": latest.get("resistance"), "support": latest.get("support"),
        "all_patterns": all_patterns, "match": latest.get("match", 100.0),
        "Result": latest.get("Result", "OPEN"),
        "Entry Date": latest.get("Entry Date"),
        "Exit Date": latest.get("Exit Date"),
        "Max Reach %": latest.get("Max Reach %", 0),
        "error": None,
    }


def backtest_strategy(df, interval="1h", symbol=None):
    if df is None or df.empty or len(df) < CONFIG["MIN_BARS_REQUIRED"]: return []
    df = df.copy()
    for c in ["Open", "High", "Low", "Close"]:
        if c not in df.columns: return []
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["Open", "High", "Low", "Close"])
    if len(df) < CONFIG["MIN_BARS_REQUIRED"]: return []

    patterns = detect_all_patterns(df, interval=interval, symbol=symbol)

    trades = []
    for p in patterns:
        trades.append({
            "Symbol": symbol or "N/A", "symbol": symbol or "N/A",
            "Pattern": p["pattern"], "pattern": p["pattern"],
            "Bias": p["bias"], "bias": p["bias"], "Direction": p.get("direction", "BUY"),
            "Result": p.get("Result", "OPEN"), "Head Result": p.get("Head Result", "OPEN"),
            "Entry": p["entry"], "Entry Price": p["entry"],
            "SL": p["sl"], "Stop Loss": p["sl"],
            "TP": p["tp"], "Take Profit": p["tp"],
            "R:R": p.get("R:R"),
            "tp_source": p.get("tp_source"),
            "impulse_distance": p.get("impulse_distance"),
            "Entry Date": p.get("Entry Date"), "Exit Date": p.get("Exit Date"),
            "Exit Price": p.get("exit_price"),
            "time": p.get("Entry Date"), "close_time": p.get("Exit Date"),
            "Max Reach %": p.get("Max Reach %", 0.0), "SL Safety %": p.get("SL Safety %", 0.0),
            "Entry Conditions": p.get("Entry Conditions", ""),
            "nodes": p.get("nodes", []), "top_nodes": p.get("top_nodes", []),
            "bot_nodes": p.get("bot_nodes", []), "top_line": p.get("top_line"),
            "bot_line": p.get("bot_line"), "arrow": p.get("arrow"),
            "consolidation_box": p.get("consolidation_box"),
            "candles_to_exit": p.get("candles_to_exit", 0),
            "progress_ratio": p.get("progress_ratio", 0.0),
            "neckline_end_idx": p["neckline_end_idx"], "Loss Category": p.get("Loss Category"),
            "resistance": p.get("resistance"), "support": p.get("support"),
            "channel_start": p.get("channel_start"), "channel_end": p.get("channel_end"),
            "channel_duration_bars": p.get("channel_duration_bars"),
            "channel_range_pct": p.get("channel_range_pct"),
            "consol_high": p.get("consol_high"), "consol_low": p.get("consol_low"),
            "consol_bars": p.get("consol_bars"), "consol_range_pct": p.get("consol_range_pct"),
            "breakout_body_pct": p.get("breakout_body_pct"),
            "top_touches": p.get("top_touches"), "bot_touches": p.get("bot_touches"),
            "top_flatness_pct": p.get("top_flatness_pct"),
            "bot_flatness_pct": p.get("bot_flatness_pct"),
            "impulse_pct": p.get("impulse_pct"),
            "slope_pct": p.get("slope_pct"),
            "cv_pct": p.get("cv_pct"),
            "drift_pct": p.get("drift_pct"),
            "flat_bars_pct": p.get("flat_bars_pct"),
            "bars_per_pct": p.get("bars_per_pct"),
        })
    return trades


def detect_all_head_shoulders(*a, **kw): return []


def diagnose_filters(df, interval="1h", symbol=None):
    result = {
        "error": None, "total_raw_candidates": 0, "final_count": 0,
        "stages": {}, "smart_diagnosis": {}, "recommendations": [],
        "trade_analysis": [], "rejection_samples": {},
    }
    if df is None or df.empty or len(df) < CONFIG["MIN_BARS_REQUIRED"]:
        result["error"] = "بيانات غير كافية"; return result
    df = df.copy()
    for c in ["Open", "High", "Low", "Close"]:
        if c not in df.columns:
            result["error"] = f"مفقود: {c}"; return result
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

    if total_closed == 0: verdict = "لا توجد صفقات كافية"
    elif win_rate >= 70: verdict = f"ممتاز — {win_rate}%"
    elif win_rate >= 50: verdict = f"جيد — {win_rate}%"
    elif win_rate >= 35: verdict = f"متوسط — {win_rate}%"
    else: verdict = f"ضعيف — {win_rate}%"

    avg_reach = 0.0
    if wins: avg_reach = round(sum(t.get("Max Reach %", 0) for t in wins) / len(wins), 1)

    result["smart_diagnosis"] = {
        "verdict": verdict,
        "win_breakdown": {"total_wins": len(wins), "avg_max_reach": avg_reach},
        "loss_breakdown": {
            "immediate_rejection": 0, "early_reversal": len(losses),
            "mid_reversal": 0, "late_reversal": 0,
            "unavoidable": 0, "avoidable": len(losses),
        },
        "action_plan": [f"🟢 WIN: {len(wins)} | ❌ LOSS: {len(losses)} | ⏰ TIMEOUT: {len(timeouts)}"],
    }
    return result


if __name__ == "__main__":
    print("ENGINE.PY — Horizontal Rectangle v19 (cluster-based lines)")
    print(f"Windows: {CONFIG['WINDOW_SIZES']}")
    print(f"Cluster top %: {CONFIG['CLUSTER_TOP_PCT']*100}%")
    print(f"Range: {CONFIG['MIN_RANGE_PCT']}% – {CONFIG['MAX_RANGE_PCT']}%")
    print(f"TP source: impulse size")
    print(f"Min R:R: {CONFIG['MIN_RR_ACCEPTED']}")
