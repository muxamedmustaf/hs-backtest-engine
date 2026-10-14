# -*- coding: utf-8 -*-
"""
ENGINE.PY — Flag / Pennant Pattern (v33)
==========================================
النمط: علم مثلث يتقارب بعد دفعة قوية.

المنطق:
  1) دفعة قوية (impulse ≥ 0.5%)
  2) تصحيح بقمتين وقاعين متقاربين (خطان يقتربان)
  3) كسر بنفس اتجاه الدفعة

الإدارة:
  • SL = الحد المقابل
  • TP = 2× المخاطرة
"""
import numpy as np
import pandas as pd


CONFIG = {
    # ── الدفعة ──────────────────────────────────────────────────────────
    "IMPULSE_BARS": [8, 12, 18, 25, 35],
    "MIN_IMPULSE_PCT": 0.50,

    # ── التصحيح (العلم) ─────────────────────────────────────────────────
    "CONSOL_BARS": [8, 12, 16, 22, 30, 40],
    "MIN_CONSOL_BARS": 8,
    "MAX_CONSOL_BARS": 40,
    "MIN_WIDTH_START_PCT": 0.10,
    "MAX_WIDTH_START_PCT": 1.50,
    "MIN_CONVERGENCE": 0.20,   # ← التقارب: العرض النهائي ≤ 80% من الأول

    # ── الكسر ───────────────────────────────────────────────────────────
    "BRK_BUFFER_PCT": 0.05,
    "MIN_BRK_BODY_PCT": 0.05,

    # ── الإدارة ─────────────────────────────────────────────────────────
    "SL_BUFFER_PCT": 0.05,
    "TP_RR": 2.0,

    # ── عامة ────────────────────────────────────────────────────────────
    "MIN_BARS_BETWEEN": 8,
    "MIN_BARS_REQUIRED": 50,
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


def _fit_line(xs, ys):
    if len(xs) < 2:
        return None
    xs = np.asarray(xs, dtype=float)
    ys = np.asarray(ys, dtype=float)
    denom = ((xs - xs.mean()) ** 2).sum()
    if denom < 1e-9:
        return None
    slope = ((xs - xs.mean()) * (ys - ys.mean())).sum() / denom
    intercept = ys.mean() - slope * xs.mean()
    return float(slope), float(intercept)


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
    df = df.dropna(subset=["Open", "High", "Low", "Close"]).reset_index(drop=True)
    if len(df) < CONFIG["MIN_BARS_REQUIRED"]:
        return []

    highs = df["High"].values.astype(float)
    lows = df["Low"].values.astype(float)
    opens = df["Open"].values.astype(float)
    closes = df["Close"].values.astype(float)
    n = len(df)

    buf = CONFIG["BRK_BUFFER_PCT"] / 100.0
    patterns = []
    last_signal = -10**9

    for i in range(CONFIG["MIN_BARS_REQUIRED"], n):
        if i - last_signal < CONFIG["MIN_BARS_BETWEEN"]:
            continue

        close_bk = closes[i]
        open_bk = opens[i]
        prev_c = closes[i - 1]

        body_pct = abs(close_bk - open_bk) / max(close_bk, 1e-9) * 100
        if body_pct < CONFIG["MIN_BRK_BODY_PCT"]:
            continue

        # ═══ جرّب كل نافذة تصحيح ═══
        best = None

        for W_c in CONFIG["CONSOL_BARS"]:
            if W_c < CONFIG["MIN_CONSOL_BARS"]:
                continue
            corr_start = i - W_c
            if corr_start < 0:
                continue

            seg_h = highs[corr_start:i]
            seg_l = lows[corr_start:i]

            xs = np.arange(W_c, dtype=float)
            upper_fit = _fit_line(xs, seg_h)
            lower_fit = _fit_line(xs, seg_l)
            if upper_fit is None or lower_fit is None:
                continue

            us, ui = upper_fit
            ls, li = lower_fit

            # ═══ فحص التقارب ═══
            w_start = (ui + us * 0) - (li + ls * 0)
            w_end = (ui + us * (W_c - 1)) - (li + ls * (W_c - 1))

            if w_start <= 0 or w_end <= 0:
                continue

            # العرض يجب أن يتقلص
            if w_end / w_start > (1 - CONFIG["MIN_CONVERGENCE"]):
                continue

            mid = (seg_h.mean() + seg_l.mean()) / 2
            if mid <= 0:
                continue

            w_start_pct = w_start / mid * 100
            if w_start_pct < CONFIG["MIN_WIDTH_START_PCT"]:
                continue
            if w_start_pct > CONFIG["MAX_WIDTH_START_PCT"]:
                continue

            # الخط العلوي يجب أن ينزل أسرع من السفلي (تقارب)
            if us >= ls:
                continue

            # ═══ قيمة الخطين عند شمعة الكسر ═══
            x_brk = float(W_c)
            upper_at = ui + us * x_brk
            lower_at = li + ls * x_brk

            up_thr = upper_at * (1 + buf)
            dn_thr = lower_at * (1 - buf)

            direction = None
            if prev_c <= up_thr and close_bk > up_thr and close_bk > open_bk:
                direction = "BUY"
            elif prev_c >= dn_thr and close_bk < dn_thr and close_bk < open_bk:
                direction = "SELL"

            if direction is None:
                continue

            # ═══ الدفعة قبل التصحيح ═══
            best_imp = None
            for W_t in CONFIG["IMPULSE_BARS"]:
                t_start = corr_start - W_t
                if t_start < 0:
                    continue
                move = (closes[corr_start - 1] - closes[t_start]) / closes[t_start] * 100
                if abs(move) < CONFIG["MIN_IMPULSE_PCT"]:
                    continue
                best_imp = (W_t, t_start, move)
                break

            if best_imp is None:
                continue

            W_t, t_start, move = best_imp
            impulse_dir = "UP" if move > 0 else "DOWN"

            # ═══ استمرار فقط ═══
            if impulse_dir == "UP" and direction != "BUY":
                continue
            if impulse_dir == "DOWN" and direction != "SELL":
                continue

            best = (W_c, W_t, corr_start, t_start, us, ui, ls, li,
                    upper_at, lower_at, direction, impulse_dir, move,
                    w_start_pct, w_end / w_start)
            break

        if best is None:
            continue

        pattern = _build_pattern(df, i, best, closes)
        if pattern:
            patterns.append(pattern)
            last_signal = i

    patterns.sort(key=lambda p: p["end_pos"])
    return patterns


# ══════════════════════════════════════════════════════════════════════════════
# 🎯 بناء النمط
# ══════════════════════════════════════════════════════════════════════════════
def _build_pattern(df, i, best, closes):
    (W_c, W_t, corr_start, t_start, us, ui, ls, li,
     upper_at, lower_at, direction, impulse_dir, impulse_move,
     w_start_pct, convergence) = best

    entry = float(closes[i])
    corr_end = i - 1
    sl_buf = CONFIG["SL_BUFFER_PCT"] / 100.0

    # ═══ SL على الجهة المقابلة ═══
    if direction == "BUY":
        sl = lower_at * (1 - sl_buf)
        if sl >= entry:
            return None
        risk = entry - sl
    else:
        sl = upper_at * (1 + sl_buf)
        if sl <= entry:
            return None
        risk = sl - entry
    if risk <= 0:
        return None

    tp = entry + CONFIG["TP_RR"] * risk if direction == "BUY" else entry - CONFIG["TP_RR"] * risk
    bias = "Bullish" if direction == "BUY" else "Bearish"

    # ═══ الخطوط المتقاربة ═══
    upper_pts = [(int(corr_start + k), float(ui + us * k)) for k in range(W_c + 1)]
    lower_pts = [(int(corr_start + k), float(li + ls * k)) for k in range(W_c + 1)]

    # ═══ علامات على القمم والقيعان الحقيقية ═══
    highs = df["High"].values
    lows = df["Low"].values

    tol_vis = 0.15 / 100.0
    top_nodes = []
    bot_nodes = []
    for k in range(W_c):
        idx = corr_start + k
        up_val = ui + us * k
        lo_val = li + ls * k
        if up_val > 0 and abs(highs[idx] - up_val) / up_val <= tol_vis:
            top_nodes.append((int(idx), float(highs[idx])))
        if lo_val > 0 and abs(lows[idx] - lo_val) / lo_val <= tol_vis:
            bot_nodes.append((int(idx), float(lows[idx])))

    nodes = [(int(i), entry)]

    # ═══ السهم ═══
    arrow_len = max(6, W_c // 2)
    x1_pos = min(i + arrow_len, len(df) - 1)
    arrow = {"x0": int(i), "y0": entry, "x1": int(x1_pos), "y1": tp, "direction": direction}

    box_data = {
        "x_start": int(corr_start),
        "x_end": int(corr_end),
        "high": float(max(ui + us * k for k in range(W_c))),
        "low": float(min(li + ls * k for k in range(W_c))),
    }

    range_pct = (box_data["high"] - box_data["low"]) / box_data["low"] * 100

    pattern = {
        "name": "Flag / Pennant Pattern",
        "pattern": f"{impulse_dir} Flag → {direction} Break ({W_c}b)",
        "bias": bias,
        "direction": direction,
        "trend_direction": impulse_dir,
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
        "resistance": round(upper_at, 5),
        "support": round(lower_at, 5),
        "level_price": round(upper_at if direction == "BUY" else lower_at, 5),
        "channel_start": int(corr_start),
        "channel_end": int(corr_end),
        "channel_duration_bars": int(W_c),
        "channel_range_pct": round(range_pct, 3),
        "neckline_start_idx": int(corr_start),
        "neckline_end_idx": int(i),
        "end_pos": int(i),
        "Entry Conditions": f"{impulse_dir} impulse {impulse_move:+.2f}% → flag {W_c}b (conv {convergence:.2f}) → {direction}",
        "consol_high": round(box_data["high"], 5),
        "consol_low": round(box_data["low"], 5),
        "consol_bars": int(W_c),
        "consol_range_pct": round(range_pct, 3),
        "consol_stability_pct": 100.0,
        "breakout_body_pct": 0.0,
        "impulse_pct": round(impulse_move, 3),
        "slope_pct": round(max(abs(us), abs(ls)) / max(abs(upper_at), 1e-9) * 100, 4),
        "cv_pct": 0.0,
        "drift_pct": 0.0,
        "flat_bars_pct": 100.0,
        "bars_per_pct": round(W_c / max(w_start_pct, 0.01), 2),
        "top_flatness_pct": 0.0,
        "bot_flatness_pct": 0.0,
        "top_touches": len(top_nodes),
        "bot_touches": len(bot_nodes),
        "trend_move_pct": round(impulse_move, 3),
        "trend_bars": int(W_t),
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
        "1. Impulse": {"before": len(trades), "after": len(trades), "rejected": 0, "pass_rate": "—"},
        "2. Converging flag": {"before": len(trades), "after": len(trades), "rejected": 0, "pass_rate": "—"},
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
    print("ENGINE.PY — Flag / Pennant Pattern v33")
    print(f"Impulse: ≥ {CONFIG['MIN_IMPULSE_PCT']}% in {CONFIG['IMPULSE_BARS']} bars")
    print(f"Flag: {CONFIG['MIN_CONSOL_BARS']}-{CONFIG['MAX_CONSOL_BARS']} bars | convergence ≥ {CONFIG['MIN_CONVERGENCE']*100}%")
    print(f"Breakout: close beyond line + {CONFIG['BRK_BUFFER_PCT']}%")
    print(f"TP = {CONFIG['TP_RR']}× SL")
