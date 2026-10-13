# -*- coding: utf-8 -*-
"""
ENGINE.PY — Trend → Consolidation → Continuation (v11)
=======================================================
الشروط:
  1) اتجاه قوي وواضح قبل المستطيل (≥ 1.2% حركة، ≥ 55% شموع بنفس الاتجاه)
  2) مستطيل أفقي ضيّق بعده (سعر يتحرك داخله بلا اتجاه)
  3) اختراق في نفس اتجاه الاتجاه السابق (استمرار)
  4) الإشارة بعد إغلاق شمعة الكسر خارج المستطيل
  5) SL على الجهة المقابلة من المستطيل، TP = 3× المخاطرة
"""
import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view


CONFIG = {
    "ZIGZAG_DEPTH": 5,
    "ZIGZAG_BACKSTEP": 3,

    # ── أحجام نوافذ التجميع ──────────────────────────────────────────────
    "WINDOW_SIZES": [20, 30, 45, 65, 90, 130, 180],

    # ── شروط المستطيل الأفقي ────────────────────────────────────────────
    "MIN_RANGE_PCT": 0.15,           # أدنى ارتفاع المستطيل
    "MAX_RANGE_PCT": 2.80,           # أقصى ارتفاع (نمط التجميع ضيّق)
    "MAX_SLOPE_PCT_PER_BAR": 0.006,  # ميل خط الانحدار ≈ 0
    "MAX_STD_CV_PCT": 0.40,          # std/mean صغير
    "MAX_DRIFT_PCT": 0.90,           # |آخر - أول| صغير
    "MAX_BODY_INSIDE_PCT": 60,       # لا شمعة جسمها > 60% من ارتفاع المستطيل

    # ── الاتجاه القوي قبل المستطيل ──────────────────────────────────────
    "TREND_LOOKBACK_DAYS": 7,        # ~ أسبوع من البيانات قبل المستطيل
    "MIN_TREND_MOVE_PCT": 1.20,      # |الحركة| ≥ 1.2%
    "MIN_TREND_DIRECTIONAL_PCT": 55, # ≥ 55% من شموع الاتجاه بنفس الاتجاه

    # ── الكسر ────────────────────────────────────────────────────────────
    "BREAKOUT_BUFFER_PCT": 0.03,
    "MIN_BREAKOUT_BODY_PCT": 0.10,   # جسم شمعة الكسر قوي

    # ── SL / TP ──────────────────────────────────────────────────────────
    "SL_BUFFER_PCT": 0.05,
    "TP_RR": 3.0,

    # ── فلاتر عامة ──────────────────────────────────────────────────────
    "MIN_BARS_BETWEEN": 15,
    "MAX_TIMEOUT_BARS": 300,
    "VOLUME_MA_PERIOD": 20,
    "MIN_BARS_REQUIRED": 150,
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


def get_chronological_pivots(df):
    raw = []
    highs = df["Pivot_H"].values
    lows  = df["Pivot_L"].values
    for pos in range(len(df)):
        h = highs[pos]; l = lows[pos]
        if not pd.isna(h):
            raw.append({"pos": pos, "val": float(h), "type": "H"})
        elif not pd.isna(l):
            raw.append({"pos": pos, "val": float(l), "type": "L"})
    if not raw:
        return []
    final = []
    for p in raw:
        if not final:
            final.append(p); continue
        if final[-1]["type"] != p["type"]:
            final.append(p)
        else:
            if p["type"] == "H" and p["val"] > final[-1]["val"]:
                final[-1] = p
            elif p["type"] == "L" and p["val"] < final[-1]["val"]:
                final[-1] = p
    return final


# ══════════════════════════════════════════════════════════════════════════════
# ⚡ حوسبة متجهية لخصائص كل نافذة
# ══════════════════════════════════════════════════════════════════════════════
def _compute_window_metrics(highs, lows, opens, closes, W):
    """يحسب خصائص نافذة طولها W لكل موضع انتهاء."""
    n = len(closes)
    if n < W:
        return None

    hs = sliding_window_view(highs,  W)
    ls = sliding_window_view(lows,   W)
    os_ = sliding_window_view(opens, W)
    cs = sliding_window_view(closes, W)

    win_high = hs.max(axis=1)
    win_low  = ls.min(axis=1)
    mean_c   = cs.mean(axis=1)
    std_c    = cs.std(axis=1, ddof=0)

    # slope (linear regression closed form)
    xs = np.arange(W, dtype=float)
    xs_c = xs - xs.mean()
    denom = float((xs_c ** 2).sum())
    cs_c = cs - mean_c[:, None]
    slope = (cs_c * xs_c).sum(axis=1) / denom

    drift = np.abs(cs[:, -1] - cs[:, 0]) / np.where(mean_c > 0, mean_c, 1e-9)

    bodies = np.abs(cs - os_)
    box_h  = win_high - win_low
    box_h_safe = np.where(box_h > 0, box_h, 1e-9)
    max_body_ratio = (bodies / box_h_safe[:, None]).max(axis=1) * 100

    range_pct = (win_high - win_low) / np.where(win_low > 0, win_low, 1e-9) * 100

    return {
        "win_high": win_high, "win_low": win_low,
        "mean_c": mean_c, "std_c": std_c,
        "slope": slope, "drift": drift,
        "max_body_ratio": max_body_ratio,
        "range_pct": range_pct, "window": W,
    }


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
    if len(pivots) < 4:
        return []

    highs  = df["High"].values.astype(float)
    lows   = df["Low"].values.astype(float)
    opens  = df["Open"].values.astype(float)
    closes = df["Close"].values.astype(float)
    idxs   = df.index.values
    n      = len(df)

    # ── معاملات ──────────────────────────────────────────────────────────
    trend_lookback = min(
        max(20, _days_to_bars(CONFIG["TREND_LOOKBACK_DAYS"], interval)),
        n // 3
    )
    buf = CONFIG["BREAKOUT_BUFFER_PCT"] / 100.0

    # ── حوسبة مقاييس كل حجم نافذة مرة واحدة ─────────────────────────────
    metrics_by_W = {}
    for W in CONFIG["WINDOW_SIZES"]:
        M = _compute_window_metrics(highs, lows, opens, closes, W)
        if M is not None:
            metrics_by_W[W] = M

    # ── البحث ────────────────────────────────────────────────────────────
    patterns = []
    last_signal_pos = -10**9

    for i in range(CONFIG["MIN_BARS_REQUIRED"], n):
        if i - last_signal_pos < CONFIG["MIN_BARS_BETWEEN"]:
            continue

        c_bk = closes[i]
        o_bk = opens[i]
        prev_c = closes[i - 1]

        body_pct = abs(c_bk - o_bk) / max(c_bk, 1e-9) * 100
        if body_pct < CONFIG["MIN_BREAKOUT_BODY_PCT"]:
            continue

        # جرّب كل حجم نافذة — نأخذ الأكبر الذي ينجح (أكثر تمثيلًا)
        best = None
        for W in CONFIG["WINDOW_SIZES"]:
            start = i - W
            if start < trend_lookback + 1:
                continue
            M = metrics_by_W.get(W)
            if M is None:
                continue
            k = start   # موضع النافذة [start : start+W] = [start : i]

            # ── خصائص المستطيل ──────────────────────────────────────────
            range_pct = M["range_pct"][k]
            if range_pct < CONFIG["MIN_RANGE_PCT"] or range_pct > CONFIG["MAX_RANGE_PCT"]:
                continue

            mean_c = M["mean_c"][k]
            if mean_c <= 0:
                continue

            slope_pct = abs(M["slope"][k]) / mean_c * 100
            if slope_pct > CONFIG["MAX_SLOPE_PCT_PER_BAR"]:
                continue

            cv = M["std_c"][k] / mean_c * 100
            if cv > CONFIG["MAX_STD_CV_PCT"]:
                continue

            if M["drift"][k] * 100 > CONFIG["MAX_DRIFT_PCT"]:
                continue

            if M["max_body_ratio"][k] > CONFIG["MAX_BODY_INSIDE_PCT"]:
                continue

            # ── الاتجاه قبل المستطيل ────────────────────────────────────
            t_start = start - trend_lookback
            t_end   = start - 1
            if t_start < 0:
                continue

            trend_move = (closes[t_end] - closes[t_start]) / max(closes[t_start], 1e-9) * 100
            if abs(trend_move) < CONFIG["MIN_TREND_MOVE_PCT"]:
                continue

            trend_up = trend_move > 0

            # نسبة الاتجاه
            t_seg_c = closes[t_start:t_end + 1]
            t_seg_o = opens[t_start:t_end + 1]
            t_up_candles = int((t_seg_c > t_seg_o).sum())
            t_dn_candles = int((t_seg_c < t_seg_o).sum())
            t_total = t_up_candles + t_dn_candles
            if t_total < 5:
                continue
            t_dir_pct = max(t_up_candles, t_dn_candles) / t_total * 100
            if t_dir_pct < CONFIG["MIN_TREND_DIRECTIONAL_PCT"]:
                continue

            # الاتجاه يجب أن يتوافق مع الدفع الفعلي
            if trend_up and t_up_candles < t_dn_candles:
                continue
            if (not trend_up) and t_dn_candles < t_up_candles:
                continue

            # ── الكسر ────────────────────────────────────────────────────
            box_high = float(M["win_high"][k])
            box_low  = float(M["win_low"][k])
            up_thr   = box_high * (1 + buf)
            down_thr = box_low  * (1 - buf)

            direction = None
            if prev_c <= up_thr and c_bk > up_thr and c_bk > o_bk and trend_up:
                direction = "BUY"
            elif prev_c >= down_thr and c_bk < down_thr and c_bk < o_bk and (not trend_up):
                direction = "SELL"

            if direction is None:
                continue

            # اختر الأكبر
            if best is None or W > best["W"]:
                best = {
                    "W": W, "start": start, "k": k,
                    "box_high": box_high, "box_low": box_low,
                    "range_pct": float(range_pct),
                    "slope_pct": float(slope_pct),
                    "cv": float(cv),
                    "drift_pct": float(M["drift"][k] * 100),
                    "trend_move": float(trend_move),
                    "trend_dir_pct": float(t_dir_pct),
                    "trend_up": trend_up,
                }

        if best is None:
            continue

        pattern = _build_pattern(df, i, best, direction, body_pct,
                                 highs, lows, closes, idxs, pivots)
        if pattern:
            patterns.append(pattern)
            last_signal_pos = i

    patterns.sort(key=lambda p: p["end_pos"])
    return patterns


def _build_pattern(df, idx, best, direction, body_pct,
                   highs, lows, closes, idxs, pivots):
    entry = float(closes[idx])
    box_high = best["box_high"]
    box_low  = best["box_low"]
    sl_buf = CONFIG["SL_BUFFER_PCT"] / 100.0

    if direction == "BUY":
        sl = box_low * (1 - sl_buf)
        if sl >= entry:
            return None
        risk = entry - sl
        if risk <= 0:
            return None
        tp = entry + CONFIG["TP_RR"] * risk
    else:
        sl = box_high * (1 + sl_buf)
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

    start_p = best["start"]
    end_p   = idx - 1

    # ── Nodes: بيفوتات داخل المستطيل ────────────────────────────────────
    nodes = []
    for p in pivots:
        if start_p <= p["pos"] <= end_p:
            nodes.append((idxs[p["pos"]], p["val"]))
    nodes.sort(key=lambda n: n[0])
    nodes.append((idxs[idx], entry))

    # ── سهم الهدف ───────────────────────────────────────────────────────
    arrow_len = max(8, (end_p - start_p) // 3)
    x1_pos = min(idx + arrow_len, len(df) - 1)
    arrow = {
        "x0": idxs[idx], "y0": entry,
        "x1": idxs[x1_pos], "y1": tp,
        "direction": direction,
    }

    box_data = {
        "x_start": start_p,
        "x_end":   idx,
        "high":    round(box_high, 5),
        "low":     round(box_low, 5),
    }

    trend_dir_str = "Bullish" if best["trend_up"] else "Bearish"

    pattern = {
        "name": "Trend → Consolidation → Continuation",
        "pattern": (
            f"{trend_dir_str} trend → flat box ({best['W']} bars) → "
            f"{direction} breakout"
        ),
        "bias": bias,
        "direction": direction,
        "trend_direction": trend_dir_str,
        "match": float(min(100, 60 + abs(best["trend_move"]) * 5 + best["W"] / 10)),
        "entry": round(entry, 5),
        "entry_trigger": round(entry, 5),
        "sl": round(sl, 5),
        "tp": round(tp, 5),
        "SL": round(sl, 5),
        "TP": round(tp, 5),
        "Entry": round(entry, 5),
        "nodes": nodes,
        "arrow": arrow,
        "consolidation_box": box_data,
        "resistance": round(box_high, 5),
        "support":    round(box_low, 5),
        "level_price": round(box_high if direction == "BUY" else box_low, 5),
        "channel_start": idxs[start_p],
        "channel_end":   idxs[end_p],
        "channel_duration_bars": int(best["W"]),
        "channel_range_pct": round(best["range_pct"], 3),
        "neckline_start_idx": idxs[start_p],
        "neckline_end_idx":   idxs[idx],
        "end_pos": idx,
        "Entry Conditions": (
            f"{trend_dir_str} trend ({best['trend_move']:+.2f}%, "
            f"{best['trend_dir_pct']:.0f}% dir) → flat box {best['W']} bars "
            f"({best['range_pct']:.2f}%, slope {best['slope_pct']:.4f}%/bar) → "
            f"close breakout"
        ),
        "consol_high": round(box_high, 5),
        "consol_low":  round(box_low, 5),
        "consol_bars": int(best["W"]),
        "consol_range_pct": round(best["range_pct"], 3),
        "consol_stability_pct": 100.0,
        "breakout_body_pct": round(body_pct, 3),
        "trend_move_pct": round(best["trend_move"], 2),
        "trend_dir_pct": round(best["trend_dir_pct"], 1),
        "box_slope_pct": round(best["slope_pct"], 4),
        "box_cv_pct": round(best["cv"], 3),
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
        "consolidation_box": latest.get("consolidation_box"),
        "resistance": latest.get("resistance"),
        "support": latest.get("support"),
        "trend_direction": latest.get("trend_direction"),
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
            "TrendDirection": p.get("trend_direction", "—"),
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
            "Loss Category": p.get("Loss Category"),
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
            "trend_move_pct": p.get("trend_move_pct"),
            "trend_dir_pct": p.get("trend_dir_pct"),
            "box_slope_pct": p.get("box_slope_pct"),
            "box_cv_pct": p.get("box_cv_pct"),
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
        "1. Strong pre-trend":  {"before": len(trades), "after": len(trades), "rejected": 0, "pass_rate": "—"},
        "2. Flat box detected": {"before": len(trades), "after": len(trades), "rejected": 0, "pass_rate": "—"},
        "3. Continuation break": {"before": len(trades), "after": len(trades), "rejected": 0, "pass_rate": "—"},
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
    print("ENGINE.PY — Trend → Consolidation → Continuation v11")
    print(f"Windows: {CONFIG['WINDOW_SIZES']}")
    print(f"Box: range {CONFIG['MIN_RANGE_PCT']}–{CONFIG['MAX_RANGE_PCT']}% | slope ≤ {CONFIG['MAX_SLOPE_PCT_PER_BAR']}%/bar | CV ≤ {CONFIG['MAX_STD_CV_PCT']}%")
    print(f"Pre-trend: {CONFIG['TREND_LOOKBACK_DAYS']}d, move ≥ {CONFIG['MIN_TREND_MOVE_PCT']}%, dir ≥ {CONFIG['MIN_TREND_DIRECTIONAL_PCT']}%")
    print(f"Breakout: body ≥ {CONFIG['MIN_BREAKOUT_BODY_PCT']}% | TP = {CONFIG['TP_RR']}× risk")
