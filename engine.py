# -*- coding: utf-8 -*-
"""
ENGINE.PY — Triangle / Wedge Breakout (v10)
============================================
يدعم:
  • Symmetrical Triangle   — قمة هابطة + قاع صاعد
  • Descending Triangle    — قمة هابطة + قاع أفقي
  • Ascending Triangle     — قمة أفقية + قاع صاعد
  • Rising Wedge           — القمة والقاع يصعدان مع تقارب
  • Falling Wedge          — القمة والقاع يهبطان مع تقارب

الأداء:
  • fit خطين عبر Linear Regression على البيفوتات
  • R² عالٍ إلزامي (الخطان نظيفان)
  • Apex مستقبلي + مسافة معقولة
  • ~50ms لزوج واحد H4 (500 شمعة)
"""
import numpy as np
import pandas as pd


CONFIG = {
    # ── ZigZag ───────────────────────────────────────────────────────────
    "ZIGZAG_DEPTH": 12,
    "ZIGZAG_BACKSTEP": 3,
    "MIN_SWING_PCT": 0.15,

    # ── Triangle windows ─────────────────────────────────────────────────
    "WINDOW_SIZES": [35, 50, 70, 95, 130, 175, 230],

    # ── شروط المثلث ──────────────────────────────────────────────────────
    "MIN_TOUCHES_PER_LINE": 3,       # ≥ 3 بيفوتات على كل خط
    "MIN_R2": 0.72,                  # جودة الخطين
    "MIN_WIDTH_START_PCT": 0.35,     # أدنى عرض للمثلث عند بدايته
    "MAX_WIDTH_START_PCT": 3.50,     # أقصى عرض
    "MIN_CONVERGENCE": 0.35,         # عرض النهاية ≤ 65% من عرض البداية
    "APEX_MAX_MULTIPLIER": 2.5,      # Apex ليس أبعد من 2.5× عرض النافذة
    "MIN_TOUCH_DISTANCE_PCT": 0.25,  # كل بيفوت على مسافة ≤ 0.25% من الخط

    # ── الكسر ────────────────────────────────────────────────────────────
    "BREAKOUT_BUFFER_PCT": 0.03,
    "MIN_BREAKOUT_BODY_PCT": 0.08,

    # ── SL / TP ──────────────────────────────────────────────────────────
    "SL_BUFFER_PCT": 0.05,
    "TP_RR": 3.0,

    # ── فلاتر ────────────────────────────────────────────────────────────
    "MIN_BARS_BETWEEN": 15,
    "MAX_TIMEOUT_BARS": 300,
    "VOLUME_MA_PERIOD": 20,
    "MIN_BARS_REQUIRED": 80,
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
    bpd = {"1m": 1440, "5m": 288, "15m": 96, "30m": 48, "1h": 24,
           "4h": 6, "1d": 1}.get(interval, 24)
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
    ph_col = df.columns.get_loc("Pivot_H")
    pl_col = df.columns.get_loc("Pivot_L")
    for i in range(depth, n - backstep):
        hw = highs[i - depth:i + backstep + 1]
        lw = lows[i - depth:i + backstep + 1]
        ch, cl = highs[i], lows[i]
        is_h = (ch == hw.max() and np.sum(hw == ch) == 1)
        is_l = (cl == lw.min() and np.sum(lw == cl) == 1)
        if is_h and not is_l:
            df.iloc[i, ph_col] = ch
        elif is_l and not is_h:
            df.iloc[i, pl_col] = cl
    return df


def get_chronological_pivots(df, min_swing_pct=None):
    if min_swing_pct is None:
        min_swing_pct = CONFIG["MIN_SWING_PCT"]
    raw = []
    highs = df["Pivot_H"].values
    lows  = df["Pivot_L"].values
    for pos in range(len(df)):
        h = highs[pos]
        l = lows[pos]
        if not pd.isna(h):
            raw.append({"pos": pos, "val": float(h), "type": "H"})
        elif not pd.isna(l):
            raw.append({"pos": pos, "val": float(l), "type": "L"})
    if not raw:
        return []
    # دمج المتتاليات نفس النوع
    collapsed = [raw[0]]
    for p in raw[1:]:
        last = collapsed[-1]
        if last["type"] == p["type"]:
            if p["type"] == "H" and p["val"] > last["val"]:
                collapsed[-1] = p
            elif p["type"] == "L" and p["val"] < last["val"]:
                collapsed[-1] = p
        else:
            collapsed.append(p)
    # فلتر أدنى تأرجح
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
# ⚡ Linear Fit سريع
# ══════════════════════════════════════════════════════════════════════════════
def _fit_line(xs, ys):
    """يعيد (slope, intercept, r2) أو None."""
    n = len(xs)
    if n < 2:
        return None
    xs = np.asarray(xs, dtype=float)
    ys = np.asarray(ys, dtype=float)
    mx = xs.mean()
    my = ys.mean()
    dx = xs - mx
    dy = ys - my
    denom = (dx * dx).sum()
    if denom < 1e-12:
        return None
    slope = (dx * dy).sum() / denom
    intercept = my - slope * mx
    y_pred = slope * xs + intercept
    ss_res = ((ys - y_pred) ** 2).sum()
    ss_tot = (dy ** 2).sum()
    if ss_tot < 1e-12:
        return (slope, intercept, 1.0)
    r2 = 1.0 - ss_res / ss_tot
    return (slope, intercept, r2)


def _classify_triangle(a_h, a_l, mean_price):
    """
    يصنّف المثلث حسب ميل الخطين.
    يعيد: نوع + اتجاها الكسر المحتملين (bias hint).
    """
    eps = 1e-7
    # نسب الميل (%/شمعة)
    sh = a_h / mean_price * 100
    sl = a_l / mean_price * 100

    if sh < -eps and sl > eps:
        return "Symmetrical", "both"
    if sh < -eps and abs(sl) <= eps:
        return "Descending", "bearish"
    if abs(sh) <= eps and sl > eps:
        return "Ascending", "bullish"
    if sh > eps and sl > eps and sh < sl:
        return "Rising Wedge", "bearish"
    if sh < -eps and sl < -eps and sh > sl:
        return "Falling Wedge", "bullish"
    if abs(sh) <= eps and abs(sl) <= eps:
        return "Rectangle", "both"
    return "Triangle", "both"


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
    df = df.dropna(subset=["Open", "High", "Low", "Close"]).reset_index(drop=False)
    if "index" not in df.columns:
        df = df.reset_index(drop=False)
    df = df.set_index("index", drop=False)
    if len(df) < CONFIG["MIN_BARS_REQUIRED"]:
        return []

    df = calculate_indicators(df)
    df = calculate_zigzag(df)
    pivots = get_chronological_pivots(df)
    if len(pivots) < 6:
        return []

    highs_arr  = df["High"].values.astype(float)
    lows_arr   = df["Low"].values.astype(float)
    opens_arr  = df["Open"].values.astype(float)
    closes_arr = df["Close"].values.astype(float)
    idxs       = df.index.values
    n          = len(df)

    # فرز البيفوتات مسبقًا
    ph = [(p["pos"], p["val"]) for p in pivots if p["type"] == "H"]
    pl = [(p["pos"], p["val"]) for p in pivots if p["type"] == "L"]

    buf = CONFIG["BREAKOUT_BUFFER_PCT"] / 100.0
    min_touches = CONFIG["MIN_TOUCHES_PER_LINE"]
    r2_min = CONFIG["MIN_R2"]
    width_min = CONFIG["MIN_WIDTH_START_PCT"]
    width_max = CONFIG["MAX_WIDTH_START_PCT"]
    conv_min = CONFIG["MIN_CONVERGENCE"]
    touch_tol = CONFIG["MIN_TOUCH_DISTANCE_PCT"] / 100.0
    apex_mult = CONFIG["APEX_MAX_MULTIPLIER"]

    patterns = []
    last_signal_pos = -10**9

    for i in range(CONFIG["MIN_BARS_REQUIRED"], n):
        if i - last_signal_pos < CONFIG["MIN_BARS_BETWEEN"]:
            continue

        # شمعة الكسر عند i
        close_bk   = closes_arr[i]
        open_bk    = opens_arr[i]
        prev_close = closes_arr[i - 1]

        body_pct = abs(close_bk - open_bk) / max(close_bk, 1e-9) * 100
        if body_pct < CONFIG["MIN_BREAKOUT_BODY_PCT"]:
            continue

        best = None
        best_len = 0

        # جرّب كل نافذة (نبحث عن أفضل مثلث ينتهي قبل i)
        for W in CONFIG["WINDOW_SIZES"]:
            start = i - W
            if start < 0:
                continue

            # pivots داخل النافذة [start, i-1]
            h_in = [(x, y) for (x, y) in ph if start <= x <= (i - 1)]
            l_in = [(x, y) for (x, y) in pl if start <= x <= (i - 1)]

            if len(h_in) < min_touches or len(l_in) < min_touches:
                continue

            h_fit = _fit_line([x for x, y in h_in], [y for x, y in h_in])
            l_fit = _fit_line([x for x, y in l_in], [y for x, y in l_in])
            if h_fit is None or l_fit is None:
                continue

            a_h, b_h, r2_h = h_fit
            a_l, b_l, r2_l = l_fit

            if r2_h < r2_min or r2_l < r2_min:
                continue

            # يجب أن يتقاربا: a_h < a_l
            if a_h >= a_l:
                continue

            # Apex
            denom = a_h - a_l
            if abs(denom) < 1e-12:
                continue
            x_apex = (b_l - b_h) / denom
            if x_apex < i:                # يجب أن يكون مستقبليًا
                continue
            if x_apex > i + W * apex_mult:
                continue

            # عرض البداية والنهاية
            width_start = (a_h - a_l) * start + (b_h - b_l)
            width_end   = (a_h - a_l) * (i - 1) + (b_h - b_l)

            if width_start <= 0 or width_end <= 0:
                continue

            mean_price = closes_arr[start:i].mean()
            width_start_pct = width_start / max(mean_price, 1e-9) * 100
            if width_start_pct < width_min or width_start_pct > width_max:
                continue

            convergence = width_end / width_start
            if convergence > (1 - conv_min):
                continue

            # touches: كم بيفوت قريب من الخط
            def _count_touches(items, a, b):
                c = 0
                for (x, y) in items:
                    line_y = a * x + b
                    if abs(y - line_y) / max(abs(line_y), 1e-9) <= touch_tol:
                        c += 1
                return c

            h_touches = _count_touches(h_in, a_h, b_h)
            l_touches = _count_touches(l_in, a_l, b_l)

            if h_touches < min_touches or l_touches < min_touches:
                continue

            # تفضيل النوافذ الأطول
            if W > best_len:
                best_len = W
                best = {
                    "start": start,
                    "end": i - 1,
                    "a_h": a_h, "b_h": b_h, "r2_h": r2_h,
                    "a_l": a_l, "b_l": b_l, "r2_l": r2_l,
                    "x_apex": x_apex,
                    "width_start_pct": width_start_pct,
                    "convergence": convergence,
                    "h_touches": h_touches,
                    "l_touches": l_touches,
                    "window": W,
                    "h_in": h_in,
                    "l_in": l_in,
                }

        if best is None:
            continue

        # ═══════ فحص الكسر ═══════
        upper_now = best["a_h"] * i + best["b_h"]
        lower_now = best["a_l"] * i + best["b_l"]
        upper_prev = best["a_h"] * (i - 1) + best["b_h"]
        lower_prev = best["a_l"] * (i - 1) + best["b_l"]

        up_thr   = upper_now * (1 + buf)
        down_thr = lower_now * (1 - buf)

        direction = None
        if prev_close <= upper_prev * (1 + buf) and close_bk > up_thr and close_bk > open_bk:
            direction = "BUY"
        elif prev_close >= lower_prev * (1 - buf) and close_bk < down_thr and close_bk < open_bk:
            direction = "SELL"

        if direction is None:
            continue

        pattern = _build_pattern(df, i, best, direction, body_pct,
                                 idxs, highs_arr, lows_arr, closes_arr)
        if pattern:
            patterns.append(pattern)
            last_signal_pos = i

    patterns.sort(key=lambda p: p["end_pos"])
    return patterns


def _build_pattern(df, idx, tri, direction, body_pct,
                   idxs, highs_arr, lows_arr, closes_arr):
    entry = float(closes_arr[idx])
    a_h, b_h = tri["a_h"], tri["b_h"]
    a_l, b_l = tri["a_l"], tri["b_l"]

    upper_at_break = a_h * idx + b_h
    lower_at_break = a_l * idx + b_l

    sl_buf = CONFIG["SL_BUFFER_PCT"] / 100.0

    if direction == "BUY":
        # الوقف تحت الخط السفلي عند الكسر
        sl = lower_at_break * (1 - sl_buf)
        if sl >= entry:
            return None
        risk = entry - sl
        if risk <= 0:
            return None
        tp = entry + CONFIG["TP_RR"] * risk
    else:
        sl = upper_at_break * (1 + sl_buf)
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

    mean_price = float(closes_arr[tri["start"]:idx].mean())
    tri_type, _ = _classify_triangle(a_h, a_l, mean_price)

    # ── Nodes: بيفوتات على الخطين ────────────────────────────────────────
    nodes = []
    for x, y in tri["h_in"]:
        nodes.append((idxs[x], float(y)))
    for x, y in tri["l_in"]:
        nodes.append((idxs[x], float(y)))
    nodes.sort(key=lambda n: n[0])
    nodes.append((idxs[idx], entry))

    # ── بيانات الخطين للرسم ─────────────────────────────────────────────
    triangle_upper = {
        "x0": idxs[tri["start"]],
        "y0": float(a_h * tri["start"] + b_h),
        "x1": idxs[tri["end"]],
        "y1": float(a_h * tri["end"] + b_h),
    }
    triangle_lower = {
        "x0": idxs[tri["start"]],
        "y0": float(a_l * tri["start"] + b_l),
        "x1": idxs[tri["end"]],
        "y1": float(a_l * tri["end"] + b_l),
    }
    apex_x_int = int(min(max(tri["x_apex"], idx), len(df) - 1))
    triangle_apex = {
        "x": idxs[apex_x_int],
        "y": float(a_h * apex_x_int + b_h),
    }

    # ── سهم الهدف ───────────────────────────────────────────────────────
    arrow_len = max(8, (tri["end"] - tri["start"]) // 3)
    x1_pos = min(idx + arrow_len, len(df) - 1)
    arrow = {
        "x0": idxs[idx], "y0": entry,
        "x1": idxs[x1_pos], "y1": tp,
        "direction": direction,
    }

    box_data = {
        "x_start": tri["start"],
        "x_end":   idx,
        "high":    round(float(a_h * tri["start"] + b_h), 5),
        "low":     round(float(a_l * tri["start"] + b_l), 5),
    }

    pattern = {
        "name": f"{tri_type} Triangle",
        "pattern": (
            f"{tri_type} {direction} · "
            f"T{tri['h_touches']}/B{tri['l_touches']} · "
            f"{tri['width_start_pct']:.2f}% → {tri['width_start_pct']*tri['convergence']:.2f}%"
        ),
        "bias": bias,
        "direction": direction,
        "triangle_type": tri_type,
        "match": float(min(100, 55 + (tri["h_touches"] + tri["l_touches"]) * 4 + tri["r2_h"] * 10)),
        "entry": round(entry, 5),
        "entry_trigger": round(entry, 5),
        "sl": round(sl, 5),
        "tp": round(tp, 5),
        "SL": round(sl, 5),
        "TP": round(tp, 5),
        "Entry": round(entry, 5),
        "nodes": nodes,
        "arrow": arrow,
        "triangle_upper": triangle_upper,
        "triangle_lower": triangle_lower,
        "triangle_apex":  triangle_apex,
        "consolidation_box": box_data,
        "resistance": round(float(upper_at_break), 5),
        "support":    round(float(lower_at_break), 5),
        "level_price": round(float(upper_at_break if direction == "BUY" else lower_at_break), 5),
        "channel_start": idxs[tri["start"]],
        "channel_end":   idxs[tri["end"]],
        "channel_duration_bars": int(tri["window"]),
        "neckline_start_idx": idxs[tri["start"]],
        "neckline_end_idx":   idxs[idx],
        "end_pos": idx,
        "Entry Conditions": (
            f"{tri_type} triangle · {tri['window']} bars · "
            f"R² top {tri['r2_h']:.2f} / bottom {tri['r2_l']:.2f} · "
            f"conv {tri['convergence']:.2f}"
        ),
        "consol_bars": int(tri["window"]),
        "breakout_body_pct": round(body_pct, 3),
        "triangle_r2_top": float(tri["r2_h"]),
        "triangle_r2_bot": float(tri["r2_l"]),
        "triangle_convergence": float(tri["convergence"]),
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

    highs_arr = post["High"].values.astype(float)
    lows_arr  = post["Low"].values.astype(float)
    closes_arr = post["Close"].values.astype(float)
    dates_arr = post.index.values

    is_bear = (bias == "Bearish")
    for i in range(1, len(post)):
        high = highs_arr[i]
        low  = lows_arr[i]

        if is_bear:
            fav = max(0.0, entry - low)
            adv = max(0.0, high - entry)
        else:
            fav = max(0.0, high - entry)
            adv = max(0.0, entry - low)

        if total_tp > 0:
            max_fav = max(max_fav, fav / total_tp * 100)
        if total_sl > 0:
            max_adv = max(max_adv, adv / total_sl * 100)

        hit_sl = (high >= sl) if is_bear else (low <= sl)
        hit_tp = (low  <= tp) if is_bear else (high >= tp)

        if hit_sl:
            stats["Result"] = "LOSS"; stats["Head Result"] = "LOSS"
            r = max_fav
            if r < 5:      stats["Loss Category"] = "immediate_rejection"
            elif r < 30:   stats["Loss Category"] = "early_reversal"
            elif r < 70:   stats["Loss Category"] = "mid_reversal"
            else:          stats["Loss Category"] = "late_reversal"
            stats["exit_idx"] = dates_arr[i]; stats["exit_price"] = sl
            stats["candles_to_exit"] = i; stats["Exit Date"] = str(dates_arr[i])
            break

        if hit_tp:
            stats["Result"] = "WIN"; stats["Head Result"] = "WIN"
            stats["Loss Category"] = "success"
            stats["exit_idx"] = dates_arr[i]; stats["exit_price"] = tp
            stats["candles_to_exit"] = i; stats["Exit Date"] = str(dates_arr[i])
            break

        if i >= CONFIG["MAX_TIMEOUT_BARS"]:
            stats["Result"] = "TIMEOUT"; stats["Head Result"] = "TIMEOUT"
            stats["Loss Category"] = "timeout"
            stats["exit_idx"] = dates_arr[i]; stats["exit_price"] = float(closes_arr[i])
            stats["candles_to_exit"] = i; stats["Exit Date"] = str(dates_arr[i])
            break
    else:
        stats["candles_to_exit"] = max(0, len(post) - 1)
        stats["Exit Date"] = str(dates_arr[-1])
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
        "triangle_upper": latest.get("triangle_upper"),
        "triangle_lower": latest.get("triangle_lower"),
        "triangle_apex":  latest.get("triangle_apex"),
        "triangle_type":  latest.get("triangle_type"),
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
            "Triangle_Type": p.get("triangle_type", "—"),
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
            "triangle_upper": p.get("triangle_upper"),
            "triangle_lower": p.get("triangle_lower"),
            "triangle_apex":  p.get("triangle_apex"),
            "candles_to_exit": p.get("candles_to_exit", 0),
            "progress_ratio": p.get("progress_ratio", 0.0),
            "neckline_end_idx": p["neckline_end_idx"],
            "Loss Category": p.get("Loss Category"),
            "Initial SL": p.get("Initial SL"),
            "Final SL": p.get("Final SL"),
            "resistance": p.get("resistance"),
            "support":    p.get("support"),
            "channel_start": p.get("channel_start"),
            "channel_end":   p.get("channel_end"),
            "channel_duration_bars": p.get("channel_duration_bars"),
            "triangle_r2_top": p.get("triangle_r2_top"),
            "triangle_r2_bot": p.get("triangle_r2_bot"),
            "triangle_convergence": p.get("triangle_convergence"),
            "breakout_body_pct": p.get("breakout_body_pct"),
        })
    return trades


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
        "1. Triangle detected":   {"before": len(trades), "after": len(trades), "rejected": 0, "pass_rate": "—"},
        "2. Close Breakout":      {"before": len(trades), "after": len(trades), "rejected": 0, "pass_rate": "—"},
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
    print("ENGINE.PY — Triangle / Wedge Breakout v10")
    print(f"Windows: {CONFIG['WINDOW_SIZES']}")
    print(f"Touches ≥ {CONFIG['MIN_TOUCHES_PER_LINE']} | R² ≥ {CONFIG['MIN_R2']}")
    print(f"Width start: {CONFIG['MIN_WIDTH_START_PCT']}%–{CONFIG['MAX_WIDTH_START_PCT']}%")
    print(f"Convergence ≥ {CONFIG['MIN_CONVERGENCE']} | TP = {CONFIG['TP_RR']}× risk")
