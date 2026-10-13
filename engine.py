# -*- coding: utf-8 -*-
"""
ENGINE.PY — Chart Geometry Strategy Discovery (v13)
====================================================
بدلاً من المؤشرات، نستخرج من الشارت:
  • قمم وقيعان (Swing High/Low)
  • أحجام الحركات (Impulse size)
  • نسب الارتداد (Retracement %)
  • ميل خطوط القمم والقيعان
  • المسافات الزمنية بين القمم والقيعان
  • ضغط النطاق (Compression) وموقع السعر داخله
  • شكل الشمعة (أجسام / فتائل)
  • الاتجاه والانعكاسات

ثم نربطها بنسبة الربح ونستخرج قواعد هندسية للدخول.
"""
import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view


CONFIG = {
    # ── تعريف الصفقة الرابحة ────────────────────────────────────────────
    "LOOKAHEAD_BARS": 100,
    "SL_PCT": 0.5,                   # الوقف = 0.5% من السعر (هندسي، بلا مؤشرات)
    "TP_PCT": 1.5,                   # الهدف = 1.5% (1:3)

    # ── معايير القواعد ──────────────────────────────────────────────────
    "MIN_SAMPLES_FOR_RULE": 40,
    "MIN_WIN_RATE": 60.0,
    "N_BINS": 10,

    # ── Swing parameters ────────────────────────────────────────────────
    "SWING_LOOKBACK": 3,             # 3-bar fractal لكل جانب

    "MIN_BARS_REQUIRED": 250,
    "VOLUME_MA_PERIOD": 20,
}


# ══════════════════════════════════════════════════════════════════════════════
# Helpers (نفس التوقيع القديم)
# ══════════════════════════════════════════════════════════════════════════════
def _get_max_gap(interval):
    return {"1m": 120, "5m": 50, "15m": 30, "30m": 25, "1h": 20,
            "4h": 15, "1d": 10}.get(interval, 50)


def _get_max_pattern_duration(interval):
    return {"1m": 600, "5m": 200, "15m": 150, "30m": 120, "1h": 100,
            "4h": 80, "1d": 60}.get(interval, 200)


# ══════════════════════════════════════════════════════════════════════════════
# 🎯 Swing highs/lows detection (نقية بالكامل)
# ══════════════════════════════════════════════════════════════════════════════
def find_swings(highs, lows, k=3):
    """
    قمة = High[i] > High[i-k : i+k] (بدون i)
    قاع  = Low[i]  < Low[i-k : i+k]  (بدون i)
    يعيد (swing_high_idx, swing_low_idx) — كل منهما numpy array.
    """
    n = len(highs)
    sh_mask = np.zeros(n, dtype=bool)
    sl_mask = np.zeros(n, dtype=bool)
    if n < 2 * k + 1:
        return np.where(sh_mask)[0], np.where(sl_mask)[0]

    for i in range(k, n - k):
        h_win = highs[i - k:i + k + 1]
        l_win = lows[i - k:i + k + 1]
        if highs[i] == h_win.max() and np.sum(h_win == highs[i]) == 1:
            sh_mask[i] = True
        if lows[i] == l_win.min() and np.sum(l_win == lows[i]) == 1:
            sl_mask[i] = True

    return np.where(sh_mask)[0], np.where(sl_mask)[0]


def build_swing_series(highs, lows, closes, k=3):
    """
    لكل موضع i، يعيد معلومات آخر قمة وقاع:
      last_high_val, last_high_pos, last_low_val, last_low_pos
    كمتجهات numpy بطول n (forward-filled).
    """
    n = len(closes)
    sh_idx, sl_idx = find_swings(highs, lows, k)

    last_h_val = np.full(n, np.nan)
    last_h_pos = np.full(n, -1, dtype=np.int32)
    last_l_val = np.full(n, np.nan)
    last_l_pos = np.full(n, -1, dtype=np.int32)

    # دمج الحوادث في تسلسل زمني موحّد
    events = []
    for i in sh_idx:
        events.append((i, "H", float(highs[i])))
    for i in sl_idx:
        events.append((i, "L", float(lows[i])))
    events.sort()

    cur_h_val, cur_h_pos = np.nan, -1
    cur_l_val, cur_l_pos = np.nan, -1
    ei = 0
    for i in range(n):
        while ei < len(events) and events[ei][0] <= i:
            _, typ, val = events[ei]
            if typ == "H":
                cur_h_val, cur_h_pos = val, events[ei][0]
            else:
                cur_l_val, cur_l_pos = val, events[ei][0]
            ei += 1
        last_h_val[i] = cur_h_val
        last_h_pos[i] = cur_h_pos
        last_l_val[i] = cur_l_val
        last_l_pos[i] = cur_l_pos

    return last_h_val, last_h_pos, last_l_val, last_l_pos, sh_idx, sl_idx


def _last_n_swing_values(swing_idx, swing_vals, n):
    """قائمة قيم آخر n قمم/قيعان لكل موضع i."""
    total = len(swing_idx)
    last_vals = np.full((len(swing_vals), n), np.nan, dtype=np.float32)
    last_pos = np.full((len(swing_vals), n), -1, dtype=np.int32)
    ei = 0
    for i in range(len(swing_vals)):
        while ei < total and swing_idx[ei] <= i:
            # shift
            last_vals[i, 1:] = last_vals[i, :-1]
            last_pos[i, 1:]  = last_pos[i, :-1]
            last_vals[i, 0] = swing_vals[swing_idx[ei]] if False else 0
            last_vals[i, 0] = float(swing_vals[ei]) if False else 0
            ei += 1
        # not used - replaced below
    return last_vals, last_pos


# ══════════════════════════════════════════════════════════════════════════════
# 🎯 استخراج 20 خاصية هندسية خالصة من الشارت
# ══════════════════════════════════════════════════════════════════════════════
def compute_chart_features(df, k_swing=None):
    """يعيد dict: feature_name → np.array بطول df."""
    if k_swing is None:
        k_swing = CONFIG["SWING_LOOKBACK"]

    o = df["Open"].values.astype(float)
    h = df["High"].values.astype(float)
    l = df["Low"].values.astype(float)
    c = df["Close"].values.astype(float)
    n = len(c)

    close_safe = np.where(c > 0, c, 1e-9)

    # ── قمم وقيعان ───────────────────────────────────────────────────────
    lh_val, lh_pos, ll_val, ll_pos, sh_idx, sl_idx = build_swing_series(h, l, c, k_swing)

    # المسافة من آخر قمة / آخر قاع (%)
    dist_from_high = np.where(np.isfinite(lh_val), (lh_val - c) / close_safe * 100, np.nan)
    dist_from_low  = np.where(np.isfinite(ll_val), (c - ll_val) / close_safe * 100, np.nan)

    bars_since_high = np.where(lh_pos >= 0, np.arange(n) - lh_pos, np.nan).astype(np.float32)
    bars_since_low  = np.where(ll_pos >= 0, np.arange(n) - ll_pos, np.nan).astype(np.float32)

    # آخر حدث
    last_is_high = np.where(lh_pos > ll_pos, 1.0, -1.0).astype(np.float32)

    # ── حجم آخر دفعة (impulse) — من آخر قمة لقاعها أو العكس ──────────────
    impulse_pct = np.full(n, np.nan, dtype=np.float32)
    for i in range(n):
        if lh_pos[i] >= 0 and ll_pos[i] >= 0:
            hi = lh_val[i]; lo = ll_val[i]
            if lo > 0:
                impulse_pct[i] = abs(hi - lo) / lo * 100

    # ── الارتداد الحالي من آخر دفعة (%) ─────────────────────────────────
    retracement_pct = np.full(n, np.nan, dtype=np.float32)
    for i in range(n):
        if not np.isfinite(impulse_pct[i]) or impulse_pct[i] == 0:
            continue
        hi = lh_val[i]; lo = ll_val[i]
        if lh_pos[i] > ll_pos[i]:
            # آخر دفعة صاعدة → الارتداد هبوطي
            if hi > lo:
                retracement_pct[i] = (hi - c[i]) / (hi - lo) * 100
        else:
            if hi > lo:
                retracement_pct[i] = (c[i] - lo) / (hi - lo) * 100

    # ── ميل خطوط آخر 3 قمم / قيعان ──────────────────────────────────────
    # نجمع آخر 3 قمم لكل موضع i ثم نحسب الميل (%/bar)
    last3_h = np.full((n, 3), np.nan, dtype=np.float32)
    last3_h_pos = np.full((n, 3), -1, dtype=np.int32)
    last3_l = np.full((n, 3), np.nan, dtype=np.float32)
    last3_l_pos = np.full((n, 3), -1, dtype=np.int32)

    # تعبئة متسلسلة
    from collections import deque
    hq = deque(maxlen=3)
    lq = deque(maxlen=3)
    events = []
    for i in sh_idx:
        events.append((int(i), "H", float(h[i])))
    for i in sl_idx:
        events.append((int(i), "L", float(l[i])))
    events.sort()

    ei = 0
    for i in range(n):
        while ei < len(events) and events[ei][0] <= i:
            pos, typ, val = events[ei]
            if typ == "H":
                hq.append((pos, val))
            else:
                lq.append((pos, val))
            ei += 1
        # خزّن آخر 3 (بترتيب زمني تصاعدي)
        for j, (pp, vv) in enumerate(reversed(list(hq))):
            last3_h[i, j] = vv
            last3_h_pos[i, j] = pp
        for j, (pp, vv) in enumerate(reversed(list(lq))):
            last3_l[i, j] = vv
            last3_l_pos[i, j] = pp

    slope_highs_pct = np.full(n, np.nan, dtype=np.float32)
    slope_lows_pct  = np.full(n, np.nan, dtype=np.float32)

    for i in range(n):
        # قمم
        h_idx = last3_h_pos[i]
        h_val = last3_h[i]
        valid = h_idx >= 0
        if valid.sum() >= 2:
            xs = h_idx[valid].astype(float)
            ys = h_val[valid].astype(float)
            if xs.max() > xs.min():
                s = np.polyfit(xs, ys, 1)[0]
                slope_highs_pct[i] = s / max(abs(np.mean(ys)), 1e-9) * 100
        # قيعان
        l_idx = last3_l_pos[i]
        l_val = last3_l[i]
        valid = l_idx >= 0
        if valid.sum() >= 2:
            xs = l_idx[valid].astype(float)
            ys = l_val[valid].astype(float)
            if xs.max() > xs.min():
                s = np.polyfit(xs, ys, 1)[0]
                slope_lows_pct[i] = s / max(abs(np.mean(ys)), 1e-9) * 100

    # ── عائدات بحتة (returns) ───────────────────────────────────────────
    def ret(lag):
        r = np.full(n, np.nan, dtype=np.float32)
        if n > lag:
            r[lag:] = (c[lag:] - c[:-lag]) / close_safe[:-lag] * 100
        return r

    ret5  = ret(5)
    ret10 = ret(10)
    ret20 = ret(20)
    ret50 = ret(50)

    # ── ضغط النطاق (compression) ────────────────────────────────────────
    high_s = pd.Series(h)
    low_s  = pd.Series(l)
    r5  = (high_s.rolling(5 ).max() - low_s.rolling(5 ).min()).values
    r10 = (high_s.rolling(10).max() - low_s.rolling(10).min()).values
    r20 = (high_s.rolling(20).max() - low_s.rolling(20).min()).values
    r50 = (high_s.rolling(50).max() - low_s.rolling(50).min()).values

    comp_5_20  = np.where(r20 > 0, r5  / r20 * 100, np.nan)
    comp_10_50 = np.where(r50 > 0, r10 / r50 * 100, np.nan)

    # ── موقع السعر داخل النطاق (0 = القاع، 1 = القمة) ───────────────────
    h20 = high_s.rolling(20).max().values
    l20 = low_s.rolling(20).min().values
    range_pos_20 = np.where(h20 > l20, (c - l20) / (h20 - l20), 0.5)

    h50 = high_s.rolling(50).max().values
    l50 = low_s.rolling(50).min().values
    range_pos_50 = np.where(h50 > l50, (c - l50) / (h50 - l50), 0.5)

    # ── شموع متتالية بنفس الاتجاه ───────────────────────────────────────
    bull = (c > o).astype(np.int32)
    consec_bull = np.zeros(n, dtype=np.float32)
    consec_bear = np.zeros(n, dtype=np.float32)
    for i in range(1, n):
        if bull[i]:
            consec_bull[i] = consec_bull[i-1] + 1
        else:
            consec_bear[i] = consec_bear[i-1] + 1

    # ── شكل الشمعة (body / wicks) ───────────────────────────────────────
    rng = h - l
    body = np.abs(c - o)
    upper_wick = h - np.maximum(c, o)
    lower_wick = np.minimum(c, o) - l
    rng_safe = np.where(rng > 0, rng, 1e-9)

    body_ratio        = body / rng_safe
    upper_wick_ratio  = upper_wick / rng_safe
    lower_wick_ratio  = lower_wick / rng_safe

    # ── اختراق قمة/قاع حديث ─────────────────────────────────────────────
    breakout_up = np.where(np.isfinite(lh_val), (c - lh_val) / close_safe * 100, np.nan)
    breakout_dn = np.where(np.isfinite(ll_val), (ll_val - c) / close_safe * 100, np.nan)

    return {
        # مسافات من قمم/قيعان
        "dist_from_high_pct": dist_from_high,
        "dist_from_low_pct":  dist_from_low,
        "bars_since_high":    bars_since_high,
        "bars_since_low":     bars_since_low,
        "last_is_high":       last_is_high,
        # حركات
        "impulse_pct":        impulse_pct,
        "retracement_pct":    retracement_pct,
        "slope_highs_pct":    slope_highs_pct,
        "slope_lows_pct":     slope_lows_pct,
        # عائدات بحتة
        "ret_5_pct":          ret5,
        "ret_10_pct":         ret10,
        "ret_20_pct":         ret20,
        "ret_50_pct":         ret50,
        # ضغط وموقع
        "compression_5_20":   comp_5_20,
        "compression_10_50":  comp_10_50,
        "range_pos_20":       range_pos_20,
        "range_pos_50":       range_pos_50,
        # شموع
        "consec_bull":        consec_bull,
        "consec_bear":        consec_bear,
        "body_ratio":         body_ratio,
        "upper_wick_ratio":   upper_wick_ratio,
        "lower_wick_ratio":   lower_wick_ratio,
        # اختراق
        "breakout_up_pct":    breakout_up,
        "breakout_dn_pct":    breakout_dn,
    }


# ══════════════════════════════════════════════════════════════════════════════
# حساب النتائج التاريخية (SL/TP نسب مئوية)
# ══════════════════════════════════════════════════════════════════════════════
def compute_outcomes(highs, lows, closes, horizon, sl_pct, tp_pct):
    n = len(closes)
    outcomes = np.zeros(n, dtype=np.int8)
    achieved_rr = np.zeros(n, dtype=np.float32)
    if n <= horizon + 1:
        return outcomes, achieved_rr

    fh = sliding_window_view(highs, horizon)[1:]
    fl = sliding_window_view(lows,  horizon)[1:]
    m = fh.shape[0]

    entry = closes[:m]
    sl_dist = entry * (sl_pct / 100.0)
    tp_dist = entry * (tp_pct / 100.0)

    buy_sl  = entry - sl_dist
    buy_tp  = entry + tp_dist
    sell_sl = entry + sl_dist
    sell_tp = entry - tp_dist

    hit_tp_b = fh >= buy_tp[:, None]
    hit_sl_b = fl <= buy_sl[:, None]
    hit_tp_s = fl <= sell_tp[:, None]
    hit_sl_s = fh >= sell_sl[:, None]

    BIG = horizon + 1
    ftp_b = np.where(hit_tp_b.any(axis=1), np.argmax(hit_tp_b, axis=1), BIG)
    fsl_b = np.where(hit_sl_b.any(axis=1), np.argmax(hit_sl_b, axis=1), BIG)
    ftp_s = np.where(hit_tp_s.any(axis=1), np.argmax(hit_tp_s, axis=1), BIG)
    fsl_s = np.where(hit_sl_s.any(axis=1), np.argmax(hit_sl_s, axis=1), BIG)

    buy_win  = (ftp_b < fsl_b)
    sell_win = (ftp_s < fsl_s) & ~buy_win

    outcomes[:m][buy_win]  = 1
    outcomes[:m][sell_win] = -1

    max_up   = (fh.max(axis=1) - entry) / np.where(entry > 0, entry, 1e-9) * 100
    max_down = (entry - fl.min(axis=1)) / np.where(entry > 0, entry, 1e-9) * 100
    rr_buy   = np.where(sl_pct > 0, max_up   / sl_pct, 0)
    rr_sell  = np.where(sl_pct > 0, max_down / sl_pct, 0)

    achieved_rr[:m][buy_win]  = rr_buy[buy_win].astype(np.float32)
    achieved_rr[:m][sell_win] = rr_sell[sell_win].astype(np.float32)

    return outcomes, achieved_rr


# ══════════════════════════════════════════════════════════════════════════════
# Rule mining (نفس المنطق لكن على الخصائص الهندسية)
# ══════════════════════════════════════════════════════════════════════════════
def _analyze_feature(fvals, outcomes, direction, n_bins):
    valid = np.isfinite(fvals) & ~np.isnan(fvals)
    fv = fvals[valid]
    mw = outcomes[valid] == direction
    ml = outcomes[valid] == -direction
    if len(fv) < 80 or mw.sum() + ml.sum() < 40:
        return None
    try:
        qs = np.percentile(fv, np.linspace(0, 100, n_bins + 1))
    except Exception:
        return None
    qs = np.unique(qs)
    if len(qs) < 3:
        return None

    bins_res = []
    for i in range(len(qs) - 1):
        lo, hi = qs[i], qs[i+1]
        if i < len(qs) - 2:
            in_bin = (fv >= lo) & (fv < hi)
        else:
            in_bin = (fv >= lo) & (fv <= hi)
        w = int(mw[in_bin].sum())
        l = int(ml[in_bin].sum())
        tot = w + l
        if tot < 20:
            continue
        wr = w / tot * 100
        bins_res.append({
            "lo": float(lo), "hi": float(hi),
            "win_rate": float(wr), "samples": tot,
            "wins": w, "losses": l,
        })
    return bins_res


def analyze_features(features, outcomes, direction, n_bins):
    results = {}
    for fname, fvals in features.items():
        bins_res = _analyze_feature(fvals, outcomes, direction, n_bins)
        if not bins_res:
            continue
        best_bin = max(bins_res, key=lambda b: b["win_rate"] * np.log1p(b["samples"]))
        results[fname] = {
            "bins": bins_res,
            "best_bin": best_bin,
            "score": float(best_bin["win_rate"] * np.log1p(best_bin["samples"])),
            "overall_baseline": (
                (outcomes == direction).sum() /
                max(((outcomes == direction) | (outcomes == -direction)).sum(), 1) * 100
            ),
        }
    return results


def discover_rules(features, outcomes, direction, n_bins,
                   min_samples, min_win_rate, top_k=6):
    fa = analyze_features(features, outcomes, direction, n_bins)
    if not fa:
        return [], {}

    singles = []
    for fname, res in fa.items():
        for b in res["bins"]:
            if b["win_rate"] >= min_win_rate and b["samples"] >= min_samples:
                singles.append({
                    "type": "single",
                    "conditions": [{"feature": fname, "lo": b["lo"], "hi": b["hi"]}],
                    "win_rate": b["win_rate"], "samples": b["samples"],
                    "wins": b["wins"], "losses": b["losses"],
                    "score": b["win_rate"] * np.log1p(b["samples"]),
                    "_feature": fname,
                    "_lo": b["lo"], "_hi": b["hi"],
                })

    top_features = sorted(fa.items(), key=lambda kv: kv[1]["score"], reverse=True)[:4]
    doubles = []
    for i in range(len(top_features)):
        for j in range(i + 1, len(top_features)):
            f1n, f1r = top_features[i]
            f2n, f2r = top_features[j]
            f1v = features[f1n]
            f2v = features[f2n]

            b1_sorted = sorted(f1r["bins"], key=lambda b: b["win_rate"] * np.log1p(b["samples"]), reverse=True)[:2]
            b2_sorted = sorted(f2r["bins"], key=lambda b: b["win_rate"] * np.log1p(b["samples"]), reverse=True)[:2]

            for b1 in b1_sorted:
                for b2 in b2_sorted:
                    mask = (
                        (f1v >= b1["lo"]) & (f1v <= b1["hi"]) &
                        (f2v >= b2["lo"]) & (f2v <= b2["hi"])
                    )
                    w = int(((outcomes == direction) & mask).sum())
                    l = int(((outcomes == -direction) & mask).sum())
                    tot = w + l
                    if tot < min_samples:
                        continue
                    wr = w / tot * 100
                    if wr < min_win_rate:
                        continue
                    doubles.append({
                        "type": "double",
                        "conditions": [
                            {"feature": f1n, "lo": b1["lo"], "hi": b1["hi"]},
                            {"feature": f2n, "lo": b2["lo"], "hi": b2["hi"]},
                        ],
                        "win_rate": float(wr), "samples": tot,
                        "wins": w, "losses": l,
                        "score": wr * np.log1p(tot),
                        "_feature": f"{f1n}+{f2n}",
                    })

    all_rules = singles + doubles
    all_rules.sort(key=lambda r: r["score"], reverse=True)

    dedup = []
    for r in all_rules:
        is_dup = False
        for d in dedup:
            if d["_feature"] == r["_feature"]:
                if (abs(d["conditions"][0]["lo"] - r["conditions"][0]["lo"]) /
                    max(abs(d["conditions"][0]["lo"]), 1e-9) < 0.15):
                    is_dup = True
                    break
        if not is_dup:
            dedup.append(r)
        if len(dedup) >= top_k:
            break

    return dedup, fa


def evaluate_live_signal(features, rules, direction):
    if not rules or not features:
        return None
    last_values = {k: float(v[-1]) for k, v in features.items() if np.isfinite(v[-1])}
    matched = []
    for r in rules:
        ok = True
        for cond in r["conditions"]:
            fname = cond["feature"]
            if fname not in last_values:
                ok = False
                break
            v = last_values[fname]
            if v < cond["lo"] or v > cond["hi"]:
                ok = False
                break
        if ok:
            matched.append(r)
    if not matched:
        return None
    best = max(matched, key=lambda r: r["score"])
    return {
        "direction": direction,
        "rule": best,
        "last_values": last_values,
        "matched_count": len(matched),
    }


# ══════════════════════════════════════════════════════════════════════════════
# 🎯 الواجهة الرئيسية
# ══════════════════════════════════════════════════════════════════════════════
def discover_strategy(df, interval="1h", symbol=None):
    empty = {
        "error": None, "symbol": symbol or "N/A",
        "stats": {}, "features": {}, "rules_buy": [], "rules_sell": [],
        "feature_analysis_buy": {}, "feature_analysis_sell": {},
        "live_buy": None, "live_sell": None,
    }
    if df is None or df.empty or len(df) < CONFIG["MIN_BARS_REQUIRED"]:
        empty["error"] = f"بيانات غير كافية: {0 if df is None else len(df)}"
        return empty

    df = df.copy()
    for c in ["Open", "High", "Low", "Close"]:
        if c not in df.columns:
            empty["error"] = f"مفقود: {c}"
            return empty
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["Open", "High", "Low", "Close"])
    if len(df) < CONFIG["MIN_BARS_REQUIRED"]:
        empty["error"] = f"بيانات غير كافية بعد التنظيف: {len(df)}"
        return empty

    features = compute_chart_features(df)
    highs  = df["High"].values.astype(float)
    lows   = df["Low"].values.astype(float)
    closes = df["Close"].values.astype(float)

    outcomes, achieved_rr = compute_outcomes(
        highs, lows, closes,
        CONFIG["LOOKAHEAD_BARS"],
        CONFIG["SL_PCT"],
        CONFIG["TP_PCT"],
    )

    n_buy  = int((outcomes ==  1).sum())
    n_sell = int((outcomes == -1).sum())
    n_neutral = int((outcomes == 0).sum())
    denom = max(n_buy + n_sell, 1)

    stats = {
        "total_bars":    int(len(outcomes)),
        "buy_wins":      n_buy,
        "sell_wins":     n_sell,
        "neutral":       n_neutral,
        "buy_win_rate":  round(n_buy  / denom * 100, 2),
        "sell_win_rate": round(n_sell / denom * 100, 2),
        "avg_rr_buy":    round(float(achieved_rr[outcomes ==  1].mean()) if n_buy  else 0, 2),
        "avg_rr_sell":   round(float(achieved_rr[outcomes == -1].mean()) if n_sell else 0, 2),
    }

    rules_buy,   fa_buy  = discover_rules(
        features, outcomes, +1,
        CONFIG["N_BINS"], CONFIG["MIN_SAMPLES_FOR_RULE"], CONFIG["MIN_WIN_RATE"], top_k=6)
    rules_sell, fa_sell = discover_rules(
        features, outcomes, -1,
        CONFIG["N_BINS"], CONFIG["MIN_SAMPLES_FOR_RULE"], CONFIG["MIN_WIN_RATE"], top_k=6)

    live_buy  = evaluate_live_signal(features, rules_buy,  "BUY")
    live_sell = evaluate_live_signal(features, rules_sell, "SELL")

    return {
        "error": None,
        "symbol": symbol or "N/A",
        "stats": stats,
        "features": {k: v.tolist() if hasattr(v, "tolist") else v
                     for k, v in features.items()},
        "feature_analysis_buy":  fa_buy,
        "feature_analysis_sell": fa_sell,
        "rules_buy":  [{k: v for k, v in r.items() if not k.startswith("_")} for r in rules_buy],
        "rules_sell": [{k: v for k, v in r.items() if not k.startswith("_")} for r in rules_sell],
        "live_buy":  live_buy,
        "live_sell": live_sell,
    }


# ══════════════════════════════════════════════════════════════════════════════
# واجهات متوافقة
# ══════════════════════════════════════════════════════════════════════════════
def calculate_indicators(df): return df.copy()
def calculate_zigzag(df, *a, **kw): return df.copy()
def get_chronological_pivots(df): return []
def detect_all_patterns(df, **kw): return []
def detect_all_head_shoulders(*a, **kw): return []
def backtest_strategy(df, **kw): return []


def run_full_analysis(df, interval="1h", symbol=None):
    result = discover_strategy(df, interval=interval, symbol=symbol)
    live_buy  = result.get("live_buy")
    live_sell = result.get("live_sell")

    sig = "WAITING"; pattern = "—"; bias = "Neutral"
    entry = sl = tp = None

    if live_buy:
        sig = "STRONG BUY"
        pattern = f"Rule: {live_buy['rule']['win_rate']:.1f}% / N={live_buy['rule']['samples']}"
        bias = "Bullish"
    elif live_sell:
        sig = "STRONG SELL"
        pattern = f"Rule: {live_sell['rule']['win_rate']:.1f}% / N={live_sell['rule']['samples']}"
        bias = "Bearish"

    if sig != "WAITING":
        closes = pd.to_numeric(df["Close"], errors="coerce").values
        entry = float(closes[-1])
        if bias == "Bullish":
            sl = entry * (1 - CONFIG["SL_PCT"] / 100)
            tp = entry * (1 + CONFIG["TP_PCT"] / 100)
        else:
            sl = entry * (1 + CONFIG["SL_PCT"] / 100)
            tp = entry * (1 - CONFIG["TP_PCT"] / 100)

    return {
        "df": df, "symbol": symbol or "N/A",
        "signal": sig, "pattern": pattern, "bias": bias,
        "entry": round(entry, 5) if entry else None,
        "entry_trigger": round(entry, 5) if entry else None,
        "sl": round(sl, 5) if sl else None,
        "tp": round(tp, 5) if tp else None,
        "nodes": [], "pattern_nodes": [], "all_patterns": [],
        "discovery": result,
        "error": result.get("error"),
    }


def diagnose_filters(df, interval="1h", symbol=None):
    result = discover_strategy(df, interval=interval, symbol=symbol)
    if result.get("error"):
        return {"error": result["error"]}

    stats = result["stats"]
    rules_buy = result["rules_buy"]
    rules_sell = result["rules_sell"]

    return {
        "error": None,
        "total_raw_candidates": stats["total_bars"],
        "final_count": len(rules_buy) + len(rules_sell),
        "stages": {
            "1. تصنيف الشموع": {
                "before": stats["total_bars"],
                "after": stats["buy_wins"] + stats["sell_wins"],
                "rejected": stats["neutral"],
                "pass_rate": f"{(stats['buy_wins']+stats['sell_wins'])/max(stats['total_bars'],1)*100:.1f}%",
            },
            "2. استخراج القواعد": {
                "before": stats["buy_wins"] + stats["sell_wins"],
                "after": len(rules_buy) + len(rules_sell),
                "rejected": 0,
                "pass_rate": "—",
            },
        },
        "smart_diagnosis": {
            "verdict": (
                f"BUY {stats['buy_win_rate']}% ({stats['buy_wins']}) | "
                f"SELL {stats['sell_win_rate']}% ({stats['sell_wins']})"
            ),
            "win_breakdown": {
                "total_wins": stats["buy_wins"] + stats["sell_wins"],
                "avg_max_reach": stats["avg_rr_buy"],
            },
            "loss_breakdown": {
                "immediate_rejection": 0, "early_reversal": 0,
                "mid_reversal": 0, "late_reversal": 0,
                "unavoidable": 0, "avoidable": 0,
            },
            "action_plan": (
                [f"🟢 قاعدة شراء: {r['win_rate']:.1f}% / N={r['samples']}" for r in rules_buy[:3]] +
                [f"🔴 قاعدة بيع: {r['win_rate']:.1f}% / N={r['samples']}" for r in rules_sell[:3]]
            ) or ["لم توجد قواعد قوية"],
        },
        "trade_analysis": [],
        "recommendations": [],
        "discovery": result,
    }


if __name__ == "__main__":
    print("ENGINE.PY — Chart Geometry Strategy Discovery v13")
    print(f"Features: pure price action (swings, impulses, slopes, compression, ...)")
    print(f"SL = {CONFIG['SL_PCT']}% | TP = {CONFIG['TP_PCT']}% | Lookahead = {CONFIG['LOOKAHEAD_BARS']} bars")
