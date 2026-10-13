# -*- coding: utf-8 -*-
"""
ENGINE.PY — Strict Flat Range Breakout (v8)
============================================
فلسفة جديدة كليًا:
  • نفحص النافذة السعرية مباشرة — ليس البيفوتات.
  • slope (Linear Regression على Close) ≈ 0 إلزاميًا.
  • std/mean (CV) صغير جدًا = السعر ما يتحركش أصلاً.
  • الهدف: صندوق مستطيل أفقي 100%.
  • الاتجاهات مرفوضة تلقائيًا لأن slope كبير.
"""
import pandas as pd
import numpy as np


CONFIG = {
    # ── ZigZag للعرض فقط ─────────────────────────────────────────────────
    "ZIGZAG_DEPTH": 5,
    "ZIGZAG_BACKSTEP": 3,

    # ── Flat Range — شروط صارمة تعتمد على السعر مباشرة ─────────────────
    "MIN_RANGE_BARS": 25,             # ≥ 25 شمعة (≈ 5 أيام على H4)
    "MAX_RANGE_BARS": 250,            # ≤ 250 شمعة
    "MIN_RANGE_PCT": 0.15,            # أدنى ارتفاع الصندوق
    "MAX_RANGE_PCT": 1.80,            # ⬇⬇ 3.0 → 1.8 — تصحيح ضيّق فقط

    # ميل خط الانحدار على Close
    "MAX_SLOPE_PCT_PER_BAR": 0.004,   # ⬇⬇ 0.02 → 0.004 (slope near zero)
    # انحراف معياري
    "MAX_STD_CV_PCT": 0.30,           # std/mean ≤ 0.30%
    # انجراف كلّي
    "MAX_DRIFT_PCT": 0.60,            # |last-first| ≤ 0.60% من المتوسط

    # لمسات فعلية على الحدّين
    "MIN_TOUCHES_EACH_SIDE": 3,
    "TOUCH_TOLERANCE_PCT": 0.12,      # ± 0.12% من الحد

    # شموع داخل النطاق
    "MAX_BODY_INSIDE_PCT": 45,        # جسم ≤ 45% من ارتفاع الصندوق

    # ── الكسر ────────────────────────────────────────────────────────────
    "BREAKOUT_BUFFER_PCT": 0.03,
    "MIN_BREAKOUT_BODY_PCT": 0.08,
    "MAX_BARS_AFTER_RANGE": 8,        # الكسر يجب أن يحدث خلال 8 شموع من نهاية النطاق

    # ── SL / TP ──────────────────────────────────────────────────────────
    "SL_BUFFER_PCT": 0.05,
    "TP_RR": 3.0,

    # ── فلاتر ────────────────────────────────────────────────────────────
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


def get_chronological_pivots(df):
    raw = []
    for pos, (idx, row) in enumerate(df.iterrows()):
        if not pd.isna(row["Pivot_H"]):
            raw.append({"idx": idx, "pos": pos, "val": float(row["Pivot_H"]), "type": "H"})
        elif not pd.isna(row["Pivot_L"]):
            raw.append({"idx": idx, "pos": pos, "val": float(row["Pivot_L"]), "type": "L"})
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
# 🎯 فحص مباشر للنافذة السعرية
# ══════════════════════════════════════════════════════════════════════════════
def _check_flat_segment(seg):
    """
    فحص نافذة سعرية واحدة مباشرة. يعيد dict أو None.
    """
    n = len(seg)
    if n < CONFIG["MIN_RANGE_BARS"]:
        return None

    high = float(seg["High"].max())
    low  = float(seg["Low"].min())
    if low <= 0 or high <= low:
        return None

    range_pct = (high - low) / low * 100
    if range_pct < CONFIG["MIN_RANGE_PCT"] or range_pct > CONFIG["MAX_RANGE_PCT"]:
        return None

    closes = seg["Close"].values.astype(float)
    mean_close = float(np.mean(closes))
    if mean_close <= 0:
        return None

    # ── slope via linear regression ─────────────────────────────────────
    xs = np.arange(n, dtype=float)
    try:
        slope = float(np.polyfit(xs, closes, 1)[0])
    except Exception:
        return None
    slope_pct = abs(slope) / mean_close * 100
    if slope_pct > CONFIG["MAX_SLOPE_PCT_PER_BAR"]:
        return None

    # ── std / CV ─────────────────────────────────────────────────────────
    std_close = float(np.std(closes))
    cv = std_close / mean_close * 100
    if cv > CONFIG["MAX_STD_CV_PCT"]:
        return None

    # ── drift ────────────────────────────────────────────────────────────
    drift_pct = abs(closes[-1] - closes[0]) / mean_close * 100
    if drift_pct > CONFIG["MAX_DRIFT_PCT"]:
        return None

    # ── لمسات فعلية على الحدّين ─────────────────────────────────────────
    tol = CONFIG["TOUCH_TOLERANCE_PCT"] / 100.0
    top_touch = 0
    bot_touch = 0
    top_positions = []
    bot_positions = []

    for pos_local in range(n):
        row = seg.iloc[pos_local]
        h = float(row["High"])
        l = float(row["Low"])
        # اللمس: قمة قريبة من الـ high (أو القمة نفسها)
        if abs(h - high) / high <= tol:
            top_touch += 1
            top_positions.append(pos_local)
        if abs(l - low) / low <= tol:
            bot_touch += 1
            bot_positions.append(pos_local)

    # نحتاج لمسات موزّعة (لا تتكدّس في نقطة واحدة)
    def _spread(positions):
        if len(positions) < 2:
            return 0
        return max(positions) - min(positions)

    if top_touch < CONFIG["MIN_TOUCHES_EACH_SIDE"]:
        return None
    if bot_touch < CONFIG["MIN_TOUCHES_EACH_SIDE"]:
        return None
    # يجب أن تكون اللمسات موزّعة على الأقل نصف النافذة
    if _spread(top_positions) < n * 0.5:
        return None
    if _spread(bot_positions) < n * 0.5:
        return None

    # ── لا شمعة بجسم ضخم ─────────────────────────────────────────────────
    box_h = high - low
    if box_h <= 0:
        return None
    for _, row in seg.iterrows():
        body = abs(float(row["Close"]) - float(row["Open"]))
        if body / box_h * 100 > CONFIG["MAX_BODY_INSIDE_PCT"]:
            return None

    return {
        "high": high, "low": low,
        "range_pct": range_pct,
        "length": n,
        "slope_pct": slope_pct,
        "cv": cv,
        "drift_pct": drift_pct,
        "top_touches": top_touch,
        "bot_touches": bot_touch,
    }


# ══════════════════════════════════════════════════════════════════════════════
# 🎯 DETECTOR — انطلاقًا من الكسر نبحث عن النافذة
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

    min_bars = CONFIG["MIN_RANGE_BARS"]
    max_bars = min(CONFIG["MAX_RANGE_BARS"],
                   _days_to_bars(30, interval) if interval != "4h" else CONFIG["MAX_RANGE_BARS"])
    buf = CONFIG["BREAKOUT_BUFFER_PCT"] / 100.0

    n = len(df)
    patterns = []
    last_signal_pos = -10**9

    # نتحرك على كل شمعة كسر محتملة
    for i in range(CONFIG["MIN_BARS_REQUIRED"], n):
        if i - last_signal_pos < CONFIG["MIN_BARS_BETWEEN"]:
            continue

        candle = df.iloc[i]
        prev   = df.iloc[i - 1]
        close      = float(candle["Close"])
        open_      = float(candle["Open"])
        prev_close = float(prev["Close"])

        body_pct = abs(close - open_) / max(close, 1e-9) * 100
        if body_pct < CONFIG["MIN_BREAKOUT_BODY_PCT"]:
            continue

        # ── ابحث عن أفضل نافذة أفقية تنتهي قبل الكسر بقليل ─────────────
        best = None
        best_len = 0

        # النافذة يجب أن تنتهي عند i-1 (آخر شمعة قبل الكسر)
        for length in range(min_bars, min(max_bars, i) + 1):
            start = i - length
            seg = df.iloc[start:i]  # [start, i-1] شامل
            if len(seg) != length:
                continue
            info = _check_flat_segment(seg)
            if info is None:
                continue
            # نفضّل الأطول
            if info["length"] > best_len:
                best_len = info["length"]
                best = info
                best["start"] = start
                best["end"]   = i - 1
                best["length"] = info["length"]

        if best is None:
            continue

        # ── فحص الكسر عند i ─────────────────────────────────────────────
        res = best["high"]
        sup = best["low"]
        up_thr   = res * (1 + buf)
        down_thr = sup * (1 - buf)

        direction = None
        if prev_close <= up_thr and close > up_thr and close > open_:
            direction = "BUY"
        elif prev_close >= down_thr and close < down_thr and close < open_:
            direction = "SELL"

        if direction is None:
            continue

        pattern = _build_pattern(df, i, best, direction, body_pct)
        if pattern:
            patterns.append(pattern)
            last_signal_pos = i

    return patterns


def _build_pattern(df, idx, box, direction, body_pct):
    candle = df.iloc[idx]
    entry  = float(candle["Close"])
    res    = box["high"]
    sup    = box["low"]
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

    # ── Nodes: قمم ملامسة للحد العلوي + قيعان ملامسة للحد السفلي فقط ───
    start_p = box["start"]
    end_p   = box["end"]
    tol = CONFIG["TOUCH_TOLERANCE_PCT"] / 100.0 * 1.5

    top_nodes = []
    bot_nodes = []

    for pos in range(start_p, end_p + 1):
        row = df.iloc[pos]
        h = float(row["High"])
        l = float(row["Low"])
        if abs(h - res) / res <= tol:
            top_nodes.append((df.index[pos], res))
        if abs(l - sup) / sup <= tol:
            bot_nodes.append((df.index[pos], sup))

    # نقاط الخط المتعرج: قمم ثم قيعان بالتسلسل الزمني
    touch_points = sorted(top_nodes + bot_nodes, key=lambda x: pd.to_datetime(x[0]))
    # أضف نقطة الكسر
    touch_points.append((df.index[idx], entry))
    nodes = touch_points

    # ── سهم الهدف ───────────────────────────────────────────────────────
    arrow_len = max(8, (end_p - start_p) // 3)
    x1_pos = min(idx + arrow_len, len(df) - 1)
    arrow = {
        "x0": df.index[idx], "y0": entry,
        "x1": df.index[x1_pos], "y1": tp,
        "direction": direction,
    }

    box_data = {
        "x_start": start_p,
        "x_end":   idx,
        "high":    round(res, 5),
        "low":     round(sup, 5),
    }

    pattern = {
        "name": "Flat Range Breakout",
        "pattern": (
            f"Flat {direction} · "
            f"T{box['top_touches']}/B{box['bot_touches']} · "
            f"{box['range_pct']:.2f}%"
        ),
        "bias": bias,
        "direction": direction,
        "match": float(min(100, 55 + (box["top_touches"] + box["bot_touches"]) * 4)),
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
        "resistance": round(res, 5),
        "support":    round(sup, 5),
        "level_price": round(res if direction == "BUY" else sup, 5),
        "level_touches": (box["top_touches"] if direction == "BUY" else box["bot_touches"]),
        "channel_start": df.index[start_p],
        "channel_end":   df.index[end_p],
        "channel_duration_bars": int(box["length"]),
        "channel_range_pct": round(box["range_pct"], 3),
        "neckline_start_idx": df.index[start_p],
        "neckline_end_idx":   df.index[idx],
        "end_pos": idx,
        "Entry Conditions": (
            f"Flat range {box['length']} bars · slope {box['slope_pct']:.4f}%/bar · "
            f"CV {box['cv']:.3f}% · drift {box['drift_pct']:.3f}%"
        ),
        "consol_high": round(res, 5),
        "consol_low":  round(sup, 5),
        "consol_bars": int(box["length"]),
        "consol_range_pct": round(box["range_pct"], 3),
        "consol_stability_pct": 100.0,
        "breakout_body_pct": round(body_pct, 3),
    }

    pattern.update(simulate_trade_outcome(pattern, df))
    return pattern


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


def detect_all_head_shoulders(pivots=None, df=None, is_backtest=False, **kwargs):
    if df is None:
        return []
    return detect_all_patterns(df)


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
        f"1. Flat Range ≥{CONFIG['MIN_RANGE_BARS']} bars": {"before": len(trades), "after": len(trades), "rejected": 0, "pass_rate": "—"},
        "2. Close Breakout":                                {"before": len(trades), "after": len(trades), "rejected": 0, "pass_rate": "—"},
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
    print("ENGINE.PY — Strict Flat Range Breakout v8")
    print(f"Range: {CONFIG['MIN_RANGE_BARS']}–{CONFIG['MAX_RANGE_BARS']} bars | size {CONFIG['MIN_RANGE_PCT']}%–{CONFIG['MAX_RANGE_PCT']}%")
    print(f"slope ≤ {CONFIG['MAX_SLOPE_PCT_PER_BAR']}%/bar | CV ≤ {CONFIG['MAX_STD_CV_PCT']}% | drift ≤ {CONFIG['MAX_DRIFT_PCT']}%")
    print(f"touches ≥ {CONFIG['MIN_TOUCHES_EACH_SIDE']} each side | tolerance ± {CONFIG['TOUCH_TOLERANCE_PCT']}%")
    print(f"Breakout body ≥ {CONFIG['MIN_BREAKOUT_BODY_PCT']}% | TP = {CONFIG['TP_RR']}× risk")
