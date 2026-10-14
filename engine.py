# -*- coding: utf-8 -*-
"""
ENGINE.PY — 3 Sharia Only (v25)
=================================
منطق مبسّط تماماً كما في الصورة:

  الشرط 1: اتجاه واضح (حركة ≥ X% في نافذة زمنية)
  الشرط 2: تصحيح أفقي ≥ أسبوع (المدى ≤ Y%)
  الشرط 3: كسر بإغلاق شمعة خارج الحد

  SL = الجهة المقابلة
  TP = 2× المخاطرة
"""
import numpy as np
import pandas as pd


CONFIG = {
    # ── الشرط 1: الاتجاه ────────────────────────────────────────────────
    "TREND_BARS": [20, 30, 45, 60],       # نوافذ الاتجاه
    "TREND_MIN_MOVE_PCT": 0.50,           # أدنى حركة %

    # ── الشرط 2: التصحيح ────────────────────────────────────────────────
    "CONS_BARS": [40, 60, 90, 130, 180],  # نوافذ التجميع
    "CONS_MIN_BARS": 40,                  # ≥ ~أسبوع على H4
    "CONS_MAX_RANGE_PCT": 2.00,           # عرض المستطيل ≤ 2%

    # ── الشرط 3: الكسر ──────────────────────────────────────────────────
    "BRK_BUFFER_PCT": 0.03,               # هامش صغير

    # ── الإدارة ─────────────────────────────────────────────────────────
    "SL_BUFFER_PCT": 0.05,
    "TP_RR": 2.0,                         # الهدف = ضعف الوقف

    # ── عامة ────────────────────────────────────────────────────────────
    "MIN_BARS_BETWEEN": 15,
    "MIN_BARS_REQUIRED": 60,
    "MAX_TIMEOUT_BARS": 300,
}


# ══════════════════════════════════════════════════════════════════════════════
# Helpers متوافقة مع الواجهة
# ══════════════════════════════════════════════════════════════════════════════
def calculate_indicators(df): return df.copy()
def calculate_zigzag(df, *a, **kw): return df.copy()
def get_chronological_pivots(df): return []
def _get_max_gap(interval): return 50
def _get_max_pattern_duration(interval): return 200


# ══════════════════════════════════════════════════════════════════════════════
# 🎯 الكشف البسيط
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

    buf = CONFIG["BRK_BUFFER_PCT"] / 100.0
    patterns = []
    last_signal = -10**9

    for i in range(CONFIG["MIN_BARS_REQUIRED"], n):
        if i - last_signal < CONFIG["MIN_BARS_BETWEEN"]:
            continue

        close_bk = closes[i]
        prev_c = closes[i - 1]

        best = None

        # ═══ كل نوافذ التصحيح (الأطول أولاً) ═══
        for W_c in CONFIG["CONS_BARS"]:
            if W_c < CONFIG["CONS_MIN_BARS"]: continue
            start_c = i - W_c
            if start_c < 0: continue

            # ── الشرط 2: التصحيح ────────────────────────────────────
            seg_h = highs[start_c:i]
            seg_l = lows[start_c:i]
            box_top = float(seg_h.max())
            box_bot = float(seg_l.min())

            if box_bot <= 0: continue
            range_pct = (box_top - box_bot) / box_bot * 100
            if range_pct > CONFIG["CONS_MAX_RANGE_PCT"]: continue

            # ── الشرط 3: الكسر ─────────────────────────────────────
            up_thr = box_top * (1 + buf)
            dn_thr = box_bot * (1 - buf)

            direction = None
            if prev_c <= up_thr and close_bk > up_thr:
                direction = "BUY"
            elif prev_c >= dn_thr and close_bk < dn_thr:
                direction = "SELL"

            if direction is None: continue

            # ── الشرط 1: الاتجاه قبل التصحيح ────────────────────────
            for W_t in CONFIG["TREND_BARS"]:
                start_t = start_c - W_t
                if start_t < 0: continue

                trend_move_pct = (closes[start_c - 1] - closes[start_t]) / closes[start_t] * 100

                if abs(trend_move_pct) < CONFIG["TREND_MIN_MOVE_PCT"]: continue

                trend_dir = "UP" if trend_move_pct > 0 else "DOWN"

                best = (W_c, W_t, start_c, start_t, box_top, box_bot,
                        direction, trend_dir, trend_move_pct)
                break
            if best: break

        if best is None: continue

        pattern = _build_pattern(df, i, best, closes)
        if pattern:
            patterns.append(pattern)
            last_signal = i

    patterns.sort(key=lambda p: p["end_pos"])
    return patterns


def _build_pattern(df, i, best, closes):
    (W_c, W_t, start_c, start_t, box_top, box_bot,
     direction, trend_dir, trend_move_pct) = best

    entry = float(closes[i])
    end_c = i - 1
    sl_buf = CONFIG["SL_BUFFER_PCT"] / 100.0

    # ── SL: الجهة المقابلة ─────────────────────────────────────────────
    if direction == "BUY":
        sl = box_bot * (1 - sl_buf)
        if sl >= entry: return None
        risk = entry - sl
    else:
        sl = box_top * (1 + sl_buf)
        if sl <= entry: return None
        risk = sl - entry

    if risk <= 0: return None

    # ── TP: ضعف الوقف ──────────────────────────────────────────────────
    tp = entry + CONFIG["TP_RR"] * risk if direction == "BUY" else entry - CONFIG["TP_RR"] * risk

    bias = "Bullish" if direction == "BUY" else "Bearish"

    # ── نقاط اللمسات (للعرض) ───────────────────────────────────────────
    highs = df["High"].values
    lows  = df["Low"].values

    tol_vis = 0.30 / 100.0
    seg_h = highs[start_c:end_c + 1]
    seg_l = lows[start_c:end_c + 1]

    top_hits = np.where(seg_h >= box_top * (1 - tol_vis))[0]
    bot_hits = np.where(seg_l <= box_bot * (1 + tol_vis))[0]

    top_nodes = [(int(start_c + p), float(seg_h[p])) for p in top_hits]
    bot_nodes = [(int(start_c + p), float(seg_l[p])) for p in bot_hits]

    top_line = [(int(start_c), box_top), (int(end_c), box_top)]
    bot_line = [(int(start_c), box_bot), (int(end_c), box_bot)]
    nodes = [(int(i), entry)]

    arrow_len = max(8, (end_c - start_c) // 3)
    x1_pos = min(i + arrow_len, len(df) - 1)
    arrow = {"x0": int(i), "y0": entry, "x1": int(x1_pos), "y1": tp, "direction": direction}

    box_data = {"x_start": int(start_c), "x_end": int(end_c),
                "high": float(box_top), "low": float(box_bot)}

    range_pct = (box_top - box_bot) / box_bot * 100

    pattern = {
        "name": "Trend → Flat → Breakout",
        "pattern": f"{trend_dir} Trend → Flat {W_c}b → {direction} Break",
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
        "R:R": CONFIG["TP_RR"],
        "tp_source": "2x_stop",
        "nodes": nodes,
        "top_nodes": top_nodes,
        "bot_nodes": bot_nodes,
        "top_line": top_line,
        "bot_line": bot_line,
        "arrow": arrow,
        "consolidation_box": box_data,
        "resistance": round(box_top, 5),
        "support": round(box_bot, 5),
        "level_price": round(box_top if direction == "BUY" else box_bot, 5),
        "channel_start": int(start_c),
        "channel_end": int(end_c),
        "channel_duration_bars": int(W_c),
        "channel_range_pct": round(range_pct, 3),
        "neckline_start_idx": int(start_c),
        "neckline_end_idx": int(i),
        "end_pos": int(i),
        "Entry Conditions": f"Trend {trend_dir} {trend_move_pct:+.2f}% → Flat {W_c}b → {direction} break",
        "consol_high": round(box_top, 5),
        "consol_low": round(box_bot, 5),
        "consol_bars": int(W_c),
        "consol_range_pct": round(range_pct, 3),
        "consol_stability_pct": 100.0,
        "breakout_body_pct": 0.0,
        # الحقول المتوافقة مع الواجهة
        "impulse_pct":      round(trend_move_pct, 3),
        "slope_pct":        0.0,
        "cv_pct":           0.0,
        "drift_pct":        0.0,
        "flat_bars_pct":    100.0,
        "bars_per_pct":     0.0,
        "top_flatness_pct": 0.0,
        "bot_flatness_pct": 0.0,
        "top_touches":      len(top_hits),
        "bot_touches":      len(bot_hits),
        "trend_move_pct":   round(trend_move_pct, 3),
        "trend_bars":       int(W_t),
        "trend_r2":         0.0,
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
        "signal": signal, "pattern": latest["pattern"], "bias": latest["bias"],
        "entry": latest["entry"], "entry_trigger": latest["entry_trigger"],
        "sl": latest["sl"], "tp": latest["tp"],
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
        "all_patterns": pats, "match": 100.0,
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
            "top_touches":       p.get("top_touches"),
            "bot_touches":       p.get("bot_touches"),
            "impulse_pct":       p.get("impulse_pct"),
            "slope_pct":         p.get("slope_pct"),
            "cv_pct":            p.get("cv_pct"),
            "drift_pct":         p.get("drift_pct"),
            "flat_bars_pct":     p.get("flat_bars_pct"),
            "bars_per_pct":      p.get("bars_per_pct"),
            "top_flatness_pct":  p.get("top_flatness_pct"),
            "bot_flatness_pct":  p.get("bot_flatness_pct"),
            "trend_direction":   p.get("trend_direction"),
            "trend_move_pct":    p.get("trend_move_pct"),
            "trend_bars":        p.get("trend_bars"),
            "trend_r2":          p.get("trend_r2"),
        })
    return trades


def detect_all_head_shoulders(*a, **kw): return []


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
        "1. Trend detected":       {"before": len(trades), "after": len(trades), "rejected": 0, "pass_rate": "—"},
        "2. Flat correction":      {"before": len(trades), "after": len(trades), "rejected": 0, "pass_rate": "—"},
        "3. Breakout with close":  {"before": len(trades), "after": len(trades), "rejected": 0, "pass_rate": "—"},
    }

    trade_analysis = []
    for i, t in enumerate(trades):
        cat = t.get("Loss Category") or "open"
        entry = t.get("Entry", 0) or 0
        sl = t.get("SL", 0) or 0
        tp = t.get("TP", 0) or 0
        risk = abs(entry - sl); reward = abs(tp - entry)
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
    print("ENGINE.PY — 3 Sharia Only v25")
    print(f"1. Trend: |move| ≥ {CONFIG['TREND_MIN_MOVE_PCT']}% in {CONFIG['TREND_BARS']} bars")
    print(f"2. Flat: range ≤ {CONFIG['CONS_MAX_RANGE_PCT']}% for ≥ {CONFIG['CONS_MIN_BARS']} bars")
    print(f"3. Breakout: close beyond border ± {CONFIG['BRK_BUFFER_PCT']}%")
    print(f"SL = opposite | TP = {CONFIG['TP_RR']}× SL")
