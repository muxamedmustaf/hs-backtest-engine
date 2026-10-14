# -*- coding: utf-8 -*-
"""
ENGINE.PY — Main Pivots → Channel → Breakout (v30)
====================================================
✅ الجديد:
  • ZigZag لاستخراج القمم والقيعان الرئيسية فقط
  • يتجاهل التحركات الداخلية الصغيرة (< threshold)
  • يبني القناة على البيفوتات الكبيرة
  • يعمل في الاتجاهين + استمرار فقط
"""
import numpy as np
import pandas as pd


CONFIG = {
    # ── ZigZag: الفلتر الرئيسي ─────────────────────────────────────────
    "ZIGZAG_THRESHOLD_PCT": 0.30,      # ← أي حركة أصغر تُتجاهل
    "ZIGZAG_MIN_GAP_BARS": 3,          # ← أدنى شمعة بين بيفوتين

    # ── الدفعة ──────────────────────────────────────────────────────────
    "IMPULSE_BARS": [10, 15, 20, 30, 45],
    "MIN_IMPULSE_PCT": 0.50,

    # ── القناة ──────────────────────────────────────────────────────────
    "MIN_CORRECTION_BARS": 8,
    "MAX_CORRECTION_BARS": 60,
    "MIN_PEAKS_IN_CORRECTION": 2,      # ← قمم رئيسية
    "MIN_VALLEYS_IN_CORRECTION": 2,    # ← قيعان رئيسية
    "MAX_CHANNEL_WIDTH_PCT": 1.50,
    "MAX_CHANNEL_SLOPE_PCT_PER_BAR": 0.25,

    # ── الكسر ───────────────────────────────────────────────────────────
    "BRK_BUFFER_PCT": 0.03,
    "MIN_BRK_BODY_PCT": 0.05,

    # ── الإدارة ─────────────────────────────────────────────────────────
    "SL_BUFFER_PCT": 0.05,
    "TP_RR": 2.0,

    # ── عامة ────────────────────────────────────────────────────────────
    "MIN_BARS_BETWEEN": 8,
    "MIN_BARS_REQUIRED": 60,
    "MAX_TIMEOUT_BARS": 300,
}


# ══════════════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════════════
def calculate_indicators(df): return df.copy()
def calculate_zigzag(df, *a, **kw): return df.copy()
def get_chronological_pivots(df): return []
def _get_max_gap(interval): return 50
def _get_max_pattern_duration(interval): return 200


# ══════════════════════════════════════════════════════════════════════════════
# 🎯 ZigZag — يحدد القمم والقيعان الرئيسية فقط
# ══════════════════════════════════════════════════════════════════════════════
def _build_zigzag(highs, lows, threshold_pct, min_gap_bars):
    """
    يعيد قائمة من البيفوتات الرئيسية:
        [{"pos": int, "price": float, "type": "H"/"L"}]
    أي حركة أصغر من threshold تُتجاهل.
    """
    n = len(highs)
    if n < 5:
        return []

    threshold = threshold_pct / 100.0
    pivots = []

    # ابدأ بافتراض أن أول شمعة قمة
    last_type = "H"
    last_pos = 0
    last_price = highs[0]

    for i in range(1, n):
        if last_type == "H":
            # نبحث عن قمة أعلى
            if highs[i] > last_price:
                last_price = highs[i]
                last_pos = i
            else:
                # قد يكون انعكاس هبوطي
                drop = (last_price - lows[i]) / max(last_price, 1e-9)
                if drop >= threshold and (i - last_pos) >= min_gap_bars:
                    pivots.append({"pos": last_pos, "price": float(last_price), "type": "H"})
                    last_type = "L"
                    last_pos = i
                    last_price = lows[i]
        else:  # last_type == "L"
            if lows[i] < last_price:
                last_price = lows[i]
                last_pos = i
            else:
                rise = (highs[i] - last_price) / max(last_price, 1e-9)
                if rise >= threshold and (i - last_pos) >= min_gap_bars:
                    pivots.append({"pos": last_pos, "price": float(last_price), "type": "L"})
                    last_type = "H"
                    last_pos = i
                    last_price = highs[i]

    # أضف آخر بيفوت
    if last_type == "H":
        pivots.append({"pos": last_pos, "price": float(last_price), "type": "H"})
    else:
        pivots.append({"pos": last_pos, "price": float(last_price), "type": "L"})

    return pivots


# ══════════════════════════════════════════════════════════════════════════════
# 🎯 fit خط الانحدار على مجموعة نقاط
# ══════════════════════════════════════════════════════════════════════════════
def _fit_line(xs, ys):
    if len(xs) < 2:
        return None
    xs = np.asarray(xs, dtype=float)
    ys = np.asarray(ys, dtype=float)
    xs_m = xs.mean()
    denom = ((xs - xs_m) ** 2).sum()
    if denom < 1e-9:
        return None
    slope = ((xs - xs_m) * (ys - ys.mean())).sum() / denom
    intercept = ys.mean() - slope * xs_m
    return float(slope), float(intercept)


# ══════════════════════════════════════════════════════════════════════════════
# 🎯 DETECTOR — على البيفوتات الرئيسية فقط
# ══════════════════════════════════════════════════════════════════════════════
def detect_all_patterns(df, interval="1h", symbol=None, **kwargs):
    if df is None or df.empty or len(df) < CONFIG["MIN_BARS_REQUIRED"]:
        return []

    df = df.copy()
    for c in ["Open", "High", "Low", "Close"]:
        if c not in df.columns:
            return []
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["Open", "High", "Low", "Close"]).reset_index(drop=True)
    if len(df) < CONFIG["MIN_BARS_REQUIRED"]:
        return []

    highs = df["High"].values.astype(float)
    lows = df["Low"].values.astype(float)
    opens = df["Open"].values.astype(float)
    closes = df["Close"].values.astype(float)
    n = len(df)

    # ═══ ZigZag: البيفوتات الرئيسية ═══
    pivots = _build_zigzag(highs, lows,
                           CONFIG["ZIGZAG_THRESHOLD_PCT"],
                           CONFIG["ZIGZAG_MIN_GAP_BARS"])
    if len(pivots) < 5:
        return []

    buf = CONFIG["BRK_BUFFER_PCT"] / 100.0
    patterns = []
    last_signal = -10**9

    # ═══ نمر على كل بيفوت كبداية تصحيح محتملة ═══
    for p_idx in range(1, len(pivots)):
        pivot = pivots[p_idx]

        # ── الدفعة: من البيفوت السابق إلى الحالي ────────────────
        prev_pivot = pivots[p_idx - 1]
        impulse_bars = pivot["pos"] - prev_pivot["pos"]
        if impulse_bars < 3:
            continue
        if not any(impulse_bars <= W for W in CONFIG["IMPULSE_BARS"]):
            continue

        impulse_move = (pivot["price"] - prev_pivot["price"]) / prev_pivot["price"] * 100
        if abs(impulse_move) < CONFIG["MIN_IMPULSE_PCT"]:
            continue
        impulse_dir = "UP" if impulse_move > 0 else "DOWN"

        # ═══ التصحيح: جمع البيفوتات اللاحقة ═══
        corr_pivots = []
        for k in range(p_idx + 1, len(pivots)):
            pos = pivots[k]["pos"]
            bars_from_start = pos - pivot["pos"]
            if bars_from_start > CONFIG["MAX_CORRECTION_BARS"]:
                break
            corr_pivots.append(pivots[k])

        if len(corr_pivots) < 4:
            continue

        peaks = [p for p in corr_pivots if p["type"] == "H"]
        valleys = [p for p in corr_pivots if p["type"] == "L"]

        if len(peaks) < CONFIG["MIN_PEAKS_IN_CORRECTION"]:
            continue
        if len(valleys) < CONFIG["MIN_VALLEYS_IN_CORRECTION"]:
            continue

        # طول التصحيح (من أول بيفوت تصحيح إلى آخر واحد)
        corr_start = corr_pivots[0]["pos"]
        corr_end = corr_pivots[-1]["pos"]
        corr_bars = corr_end - corr_start
        if corr_bars < CONFIG["MIN_CORRECTION_BARS"]:
            continue

        # ═══ خطا القناة على البيفوتات الرئيسية ═══
        peak_xs = [p["pos"] - corr_start for p in peaks]
        peak_ys = [p["price"] for p in peaks]
        valley_xs = [p["pos"] - corr_start for p in valleys]
        valley_ys = [p["price"] for p in valleys]

        upper_fit = _fit_line(peak_xs, peak_ys)
        lower_fit = _fit_line(valley_xs, valley_ys)
        if upper_fit is None or lower_fit is None:
            continue

        us, ui = upper_fit
        ls, li = lower_fit

        # فحص العرض والميل
        xs_all = np.arange(corr_bars + 1, dtype=float)
        upper_line = ui + us * xs_all
        lower_line = li + ls * xs_all
        widths = upper_line - lower_line
        if (widths <= 0).any():
            continue

        mid = (np.mean(upper_line) + np.mean(lower_line)) / 2
        if mid <= 0:
            continue

        width_pct = float(widths.max() / mid * 100)
        if width_pct > CONFIG["MAX_CHANNEL_WIDTH_PCT"]:
            continue

        us_pct = abs(us) / mid * 100
        ls_pct = abs(ls) / mid * 100
        if us_pct > CONFIG["MAX_CHANNEL_SLOPE_PCT_PER_BAR"]:
            continue
        if ls_pct > CONFIG["MAX_CHANNEL_SLOPE_PCT_PER_BAR"]:
            continue

        # ═══ البحث عن الكسر بعد corr_end ═══
        # الكسر = أول شمعة i > corr_end حيث Close يكسر الحد
        for i in range(corr_end + 1, n):
            if i - last_signal < CONFIG["MIN_BARS_BETWEEN"]:
                continue

            close_bk = closes[i]
            open_bk = opens[i]
            prev_c = closes[i - 1]

            body_pct = abs(close_bk - open_bk) / max(close_bk, 1e-9) * 100
            if body_pct < CONFIG["MIN_BRK_BODY_PCT"]:
                continue

            # قيمة الحدين عند شمعة i
            x_i = i - corr_start
            upper_at_i = ui + us * x_i
            lower_at_i = li + ls * x_i

            up_thr = upper_at_i * (1 + buf)
            dn_thr = lower_at_i * (1 - buf)

            direction = None
            if prev_c <= up_thr and close_bk > up_thr and close_bk > open_bk:
                direction = "BUY"
            elif prev_c >= dn_thr and close_bk < dn_thr and close_bk < open_bk:
                direction = "SELL"

            if direction is None:
                continue

            # فلتر الاستمرار
            if impulse_dir == "UP" and direction != "BUY":
                continue
            if impulse_dir == "DOWN" and direction != "SELL":
                continue

            # ═══ بناء النمط ═══
            info = {
                "corr_start": corr_start,
                "corr_end": corr_end,
                "peaks": peaks,
                "valleys": valleys,
                "upper_slope": us, "upper_int": ui,
                "lower_slope": ls, "lower_int": li,
                "corr_bars": corr_bars,
                "upper_at_brk": float(upper_at_i),
                "lower_at_brk": float(lower_at_i),
                "direction": direction,
                "impulse_dir": impulse_dir,
                "impulse_move": impulse_move,
                "impulse_bars": impulse_bars,
                "peak_count": len(peaks),
                "valley_count": len(valleys),
                "width_pct": width_pct,
                "brk_idx": i,
            }
            pattern = _build_pattern(df, info, closes)
            if pattern:
                patterns.append(pattern)
                last_signal = i
            break  # لا تكرر البحث عن كسر لنفس التصحيح

    patterns.sort(key=lambda p: p["end_pos"])
    return patterns


# ══════════════════════════════════════════════════════════════════════════════
# 🎯 بناء النمط
# ══════════════════════════════════════════════════════════════════════════════
def _build_pattern(df, info, closes):
    i = info["brk_idx"]
    entry = float(closes[i])
    direction = info["direction"]
    upper_at_brk = info["upper_at_brk"]
    lower_at_brk = info["lower_at_brk"]
    corr_start = info["corr_start"]
    corr_end = info["corr_end"]
    peaks = info["peaks"]
    valleys = info["valleys"]
    us = info["upper_slope"]; ui = info["upper_int"]
    ls = info["lower_slope"]; li = info["lower_int"]
    corr_bars = info["corr_bars"]

    sl_buf = CONFIG["SL_BUFFER_PCT"] / 100.0

    if direction == "BUY":
        sl = lower_at_brk * (1 - sl_buf)
        if sl >= entry:
            return None
        risk = entry - sl
    else:
        sl = upper_at_brk * (1 + sl_buf)
        if sl <= entry:
            return None
        risk = sl - entry
    if risk <= 0:
        return None

    tp = entry + CONFIG["TP_RR"] * risk if direction == "BUY" else entry - CONFIG["TP_RR"] * risk
    bias = "Bullish" if direction == "BUY" else "Bearish"

    # ═══ خطان ممتدة عبر النافذة + امتداد للكسر ═══
    x_end = i - corr_start  # يمتد حتى شمعة الكسر
    upper_pts = [(int(corr_start + k), float(ui + us * k)) for k in range(x_end + 1)]
    lower_pts = [(int(corr_start + k), float(li + ls * k)) for k in range(x_end + 1)]

    # ═══ نقاط اللمسات = البيفوتات الرئيسية فقط ═══
    top_nodes = [(int(p["pos"]), float(p["price"])) for p in peaks]
    bot_nodes = [(int(p["pos"]), float(p["price"])) for p in valleys]

    nodes = [(int(i), entry)]

    arrow_len = max(6, corr_bars // 2)
    x1_pos = min(i + arrow_len, len(df) - 1)
    arrow = {"x0": int(i), "y0": entry, "x1": int(x1_pos), "y1": tp, "direction": direction}

    box_data = {
        "x_start": int(corr_start),
        "x_end": int(corr_end),
        "high": float(max(ui + us * k for k in range(corr_bars + 1))),
        "low": float(min(li + ls * k for k in range(corr_bars + 1))),
    }

    pattern = {
        "name": "Main Pivots → Channel → Breakout",
        "pattern": f"{info['impulse_dir']} Impulse → Channel {corr_bars}b ({info['peak_count']}P/{info['valley_count']}V) → {direction}",
        "bias": bias,
        "direction": direction,
        "trend_direction": info["impulse_dir"],
        "entry": round(entry, 5),
        "entry_trigger": round(entry, 5),
        "sl": round(sl, 5),
        "tp": round(tp, 5),
        "SL": round(sl, 5),
        "TP": round(tp, 5),
        "Entry": round(entry, 5),
        "R:R": CONFIG["TP_RR"],
        "tp_source": "2x_stop",
        "nodes": nodes,
        "top_nodes": top_nodes,
        "bot_nodes": bot_nodes,
        "top_line": upper_pts,
        "bot_line": lower_pts,
        "arrow": arrow,
        "consolidation_box": box_data,
        "resistance": round(upper_at_brk, 5),
        "support": round(lower_at_brk, 5),
        "level_price": round(upper_at_brk if direction == "BUY" else lower_at_brk, 5),
        "channel_start": int(corr_start),
        "channel_end": int(corr_end),
        "channel_duration_bars": int(corr_bars),
        "channel_range_pct": round(info["width_pct"], 3),
        "neckline_start_idx": int(corr_start),
        "neckline_end_idx": int(i),
        "end_pos": int(i),
        "Entry Conditions": f"{info['impulse_dir']} impulse {info['impulse_move']:+.2f}% → channel {corr_bars}b ({info['peak_count']}P/{info['valley_count']}V) → {direction}",
        "consol_high": round(box_data["high"], 5),
        "consol_low": round(box_data["low"], 5),
        "consol_bars": int(corr_bars),
        "consol_range_pct": round(info["width_pct"], 3),
        "consol_stability_pct": 100.0,
        "breakout_body_pct": 0.0,
        "impulse_pct": round(info["impulse_move"], 3),
        "slope_pct": round(max(abs(us), abs(ls)) / max(abs(upper_at_brk), 1e-9) * 100, 4),
        "cv_pct": 0.0,
        "drift_pct": 0.0,
        "flat_bars_pct": 100.0,
        "bars_per_pct": round(corr_bars / max(info["width_pct"], 0.01), 2),
        "top_flatness_pct": 0.0,
        "bot_flatness_pct": 0.0,
        "top_touches": info["peak_count"],
        "bot_touches": info["valley_count"],
        "trend_move_pct": round(info["impulse_move"], 3),
        "trend_bars": int(info["impulse_bars"]),
        "trend_r2": 0.0,
    }

    pattern.update(simulate_trade_outcome(pattern, df))
    return pattern


# ══════════════════════════════════════════════════════════════════════════════
# Simulation
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
        "Trailing Stage": 0, "Initial SL": sl, "Final SL": sl,
        "Loss Category": None, "Pattern Duration": 50,
        "Timeout Used": CONFIG["MAX_TIMEOUT_BARS"],
    }

    if end_idx < 0 or end_idx >= len(df):
        return stats
    post = df.iloc[end_idx:]
    if len(post) <= 1:
        return stats

    stats["Entry Date"] = str(df.index[end_idx])
    total_tp = abs(tp - entry)
    total_sl = abs(sl - entry)
    max_fav = 0.0
    max_adv = 0.0

    highs_arr = post["High"].values.astype(float)
    lows_arr = post["Low"].values.astype(float)
    closes_arr = post["Close"].values.astype(float)
    dates_arr = post.index.values
    is_bear = (bias == "Bearish")

    for i in range(1, len(post)):
        high = highs_arr[i]
        low = lows_arr[i]
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
        hit_tp = (low <= tp) if is_bear else (high >= tp)

        if hit_sl:
            stats["Result"] = "LOSS"
            stats["Head Result"] = "LOSS"
            r = max_fav
            if r < 5:
                stats["Loss Category"] = "immediate_rejection"
            elif r < 30:
                stats["Loss Category"] = "early_reversal"
            elif r < 70:
                stats["Loss Category"] = "mid_reversal"
            else:
                stats["Loss Category"] = "late_reversal"
            stats["exit_idx"] = dates_arr[i]
            stats["exit_price"] = sl
            stats["candles_to_exit"] = i
            stats["Exit Date"] = str(dates_arr[i])
            break

        if hit_tp:
            stats["Result"] = "WIN"
            stats["Head Result"] = "WIN"
            stats["Loss Category"] = "success"
            stats["exit_idx"] = dates_arr[i]
            stats["exit_price"] = tp
            stats["candles_to_exit"] = i
            stats["Exit Date"] = str(dates_arr[i])
            break

        if i >= CONFIG["MAX_TIMEOUT_BARS"]:
            stats["Result"] = "TIMEOUT"
            stats["Head Result"] = "TIMEOUT"
            stats["Loss Category"] = "timeout"
            stats["exit_idx"] = dates_arr[i]
            stats["exit_price"] = float(closes_arr[i])
            stats["candles_to_exit"] = i
            stats["Exit Date"] = str(dates_arr[i])
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
    elif stats["Result"] in ("LOSS", "BREAKEVEN"):
        stats["progress_ratio"] = 0.0

    return stats


# ══════════════════════════════════════════════════════════════════════════════
# run_full_analysis / backtest_strategy / diagnose_filters
# ══════════════════════════════════════════════════════════════════════════════
def run_full_analysis(df, interval="1h", symbol=None):
    empty = {
        "df": df, "symbol": symbol or "N/A",
        "signal": "WAITING", "pattern": "NO PATTERN DETECTED",
        "bias": "Neutral", "entry": None, "sl": None, "tp": None,
        "nodes": [], "pattern_nodes": [], "all_patterns": [], "error": None,
    }
    if df is None or df.empty:
        return empty
    df = df.copy()
    for c in ["Open", "High", "Low", "Close"]:
        if c not in df.columns:
            empty["error"] = f"Missing: {c}"
            return empty
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["Open", "High", "Low", "Close"])
    if len(df) < CONFIG["MIN_BARS_REQUIRED"]:
        empty["error"] = f"Insufficient: {len(df)}"
        return empty

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
        "sl": latest["sl"],
        "tp": latest["tp"],
        "nodes": latest.get("nodes", []),
        "pattern_nodes": latest.get("nodes", []),
        "top_nodes": latest.get("top_nodes", []),
        "bot_nodes": latest.get("bot_nodes", []),
        "top_line": latest.get("top_line"),
        "bot_line": latest.get("bot_line"),
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
            "Entry Date": p.get("Entry Date"),
            "Exit Date": p.get("Exit Date"),
            "Exit Price": p.get("exit_price"),
            "time": p.get("Entry Date"),
            "close_time": p.get("Exit Date"),
            "Max Reach %": p.get("Max Reach %", 0.0),
            "SL Safety %": p.get("SL Safety %", 0.0),
            "Entry Conditions": p.get("Entry Conditions", ""),
            "nodes": p.get("nodes", []),
            "top_nodes": p.get("top_nodes", []),
            "bot_nodes": p.get("bot_nodes", []),
            "top_line": p.get("top_line"),
            "bot_line": p.get("bot_line"),
            "arrow": p.get("arrow"),
            "consolidation_box": p.get("consolidation_box"),
            "candles_to_exit": p.get("candles_to_exit", 0),
            "progress_ratio": p.get("progress_ratio", 0.0),
            "neckline_end_idx": p["neckline_end_idx"],
            "Loss Category": p.get("Loss Category"),
            "resistance": p.get("resistance"),
            "support": p.get("support"),
            "channel_start": p.get("channel_start"),
            "channel_end": p.get("channel_end"),
            "channel_duration_bars": p.get("channel_duration_bars"),
            "channel_range_pct": p.get("channel_range_pct"),
            "consol_high": p.get("consol_high"),
            "consol_low": p.get("consol_low"),
            "consol_bars": p.get("consol_bars"),
            "consol_range_pct": p.get("consol_range_pct"),
            "breakout_body_pct": p.get("breakout_body_pct"),
            "top_touches": p.get("top_touches"),
            "bot_touches": p.get("bot_touches"),
            "impulse_pct": p.get("impulse_pct"),
            "slope_pct": p.get("slope_pct"),
            "cv_pct": p.get("cv_pct"),
            "drift_pct": p.get("drift_pct"),
            "flat_bars_pct": p.get("flat_bars_pct"),
            "bars_per_pct": p.get("bars_per_pct"),
            "top_flatness_pct": p.get("top_flatness_pct"),
            "bot_flatness_pct": p.get("bot_flatness_pct"),
            "trend_direction": p.get("trend_direction"),
            "trend_move_pct": p.get("trend_move_pct"),
            "trend_bars": p.get("trend_bars"),
            "trend_r2": p.get("trend_r2"),
        })
    return trades


def detect_all_head_shoulders(*a, **kw):
    return []


def diagnose_filters(df, interval="1h", symbol=None):
    res = {
        "error": None, "total_raw_candidates": 0, "final_count": 0,
        "stages": {}, "smart_diagnosis": {}, "recommendations": [],
        "trade_analysis": [], "rejection_samples": {},
    }
    if df is None or df.empty or len(df) < CONFIG["MIN_BARS_REQUIRED"]:
        res["error"] = "بيانات غير كافية"
        return res
    df = df.copy()
    for c in ["Open", "High", "Low", "Close"]:
        if c not in df.columns:
            res["error"] = f"مفقود: {c}"
            return res
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
    if closed == 0:
        verdict = "لا توجد صفقات كافية"
    elif wr >= 70:
        verdict = f"ممتاز — {wr}%"
    elif wr >= 50:
        verdict = f"جيد — {wr}%"
    elif wr >= 35:
        verdict = f"متوسط — {wr}%"
    else:
        verdict = f"ضعيف — {wr}%"

    avg_reach = 0.0
    if wins:
        avg_reach = round(sum(t.get("Max Reach %", 0) for t in wins) / len(wins), 1)

    res["smart_diagnosis"] = {
        "verdict": verdict,
        "win_breakdown": {"total_wins": len(wins), "avg_max_reach": avg_reach},
        "loss_breakdown": {
            "immediate_rejection": 0, "early_reversal": len(losses),
            "mid_reversal": 0, "late_reversal": 0,
            "unavoidable": 0, "avoidable": len(losses),
        },
        "action_plan": [f"🟢 WIN: {len(wins)} | ❌ LOSS: {len(losses)} | ⏰ TIMEOUT: {len(timeouts)}"],
    }
    res["stages"] = {
        "1. ZigZag main pivots": {"before": len(trades), "after": len(trades), "rejected": 0, "pass_rate": "—"},
        "2. Channel on pivots": {"before": len(trades), "after": len(trades), "rejected": 0, "pass_rate": "—"},
        "3. Breakout": {"before": len(trades), "after": len(trades), "rejected": 0, "pass_rate": "—"},
    }

    trade_analysis = []
    for i, t in enumerate(trades):
        cat = t.get("Loss Category") or "open"
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
            "reason": "—", "action": "—", "prevention": "—",
        })
    res["trade_analysis"] = trade_analysis
    res["recommendations"] = []
    if len(timeouts) > len(wins):
        res["recommendations"].append({"severity": "حرج", "message": "الصفقات المنتهية بالوقت كثيرة."})

    return res


if __name__ == "__main__":
    print("ENGINE.PY — Main Pivots → Channel → Breakout v30")
    print(f"ZigZag threshold: {CONFIG['ZIGZAG_THRESHOLD_PCT']}% (drops smaller swings)")
    print(f"Impulse: ≥ {CONFIG['MIN_IMPULSE_PCT']}%")
    print(f"Channel: {CONFIG['MIN_CORRECTION_BARS']}-{CONFIG['MAX_CORRECTION_BARS']} bars")
    print(f"Min peaks/valleys in correction: {CONFIG['MIN_PEAKS_IN_CORRECTION']}/{CONFIG['MIN_VALLEYS_IN_CORRECTION']}")
    print(f"Continuation only | TP = {CONFIG['TP_RR']}× SL")
