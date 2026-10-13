# -*- coding: utf-8 -*-
"""
ENGINE.PY — Rectangle Reversal Pattern (v14.1)
==============================================
يكتشف نمط "اتجاه قوي → مستطيل بحدود متساوية → كسر":

الشروط:
  1) انطلاقة قوية قبل المستطيل (≥ 1% في ≤ 30 شمعة)
  2) حدود المستطيل: كل قمة ≈ القمة الأعلى (≥ 3 لمسات)، كل قاع ≈ القاع الأدنى (≥ 3 لمسات)
  3) تسطّح الحدود: الفرق بين أعلى وأدنى لمسة ≤ 0.25%
  4) الكسر بإغلاق شمعة خارج الحد + جسم واضح
  5) SL على الجهة المقابلة، TP = 3× المخاطرة

الإصلاح v14.1:
  • nodes و arrow و box تستخدم positions (أرقام) لا تواريخ
  • يتوافق مع reset_index في الواجهة
"""
import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view


CONFIG = {
    "WINDOW_SIZES": [35, 55, 80, 110, 155, 210],
    "MIN_TOP_TOUCHES": 3,
    "MIN_BOT_TOUCHES": 3,
    "TOUCH_TOLERANCE_PCT": 0.18,
    "FLATNESS_MAX_PCT": 0.30,
    "MIN_RANGE_PCT": 0.30,
    "MAX_RANGE_PCT": 3.50,

    "IMPULSE_LOOKBACK": 30,
    "MIN_IMPULSE_PCT": 1.00,

    "BREAKOUT_BUFFER_PCT": 0.05,
    "MIN_BREAKOUT_BODY_PCT": 0.10,

    "SL_BUFFER_PCT": 0.05,
    "TP_RR": 3.0,

    "MIN_BARS_BETWEEN": 15,
    "MAX_TIMEOUT_BARS": 300,
    "VOLUME_MA_PERIOD": 20,
    "MIN_BARS_REQUIRED": 120,
}


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
    bpd = {"1m": 1440, "5m": 288, "15m": 96, "30m": 48, "1h": 24,
           "4h": 6, "1d": 1}.get(interval, 24)
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


def calculate_zigzag(df, *a, **kw):
    return df.copy()


def get_chronological_pivots(df):
    return []


def _window_metrics(highs, lows, opens, closes, W, tol, impulse_bars):
    n = len(closes)
    if n < W + impulse_bars + 2:
        return None

    hs = sliding_window_view(highs, W)
    ls = sliding_window_view(lows,  W)
    m = hs.shape[0]

    win_high = hs.max(axis=1)
    win_low  = ls.min(axis=1)

    top_thr = win_high * (1.0 - tol)
    bot_thr = win_low  * (1.0 + tol)
    top_touch = (hs >= top_thr[:, None]).sum(axis=1)
    bot_touch = (ls <= bot_thr[:, None]).sum(axis=1)

    top_masked = np.where(hs >= top_thr[:, None], hs, np.nan)
    bot_masked = np.where(ls <= bot_thr[:, None], ls, np.nan)

    with np.errstate(invalid="ignore"):
        top_max = np.nanmax(top_masked, axis=1)
        top_min = np.nanmin(top_masked, axis=1)
        bot_max = np.nanmax(bot_masked, axis=1)
        bot_min = np.nanmin(bot_masked, axis=1)

    top_flat_pct = np.where(win_high > 0,
                            (top_max - top_min) / win_high * 100,
                            np.inf)
    bot_flat_pct = np.where(win_low > 0,
                            (bot_max - bot_min) / win_low * 100,
                            np.inf)

    range_pct = np.where(win_low > 0,
                         (win_high - win_low) / win_low * 100,
                         np.inf)

    impulse_pct = np.full(m, 0.0, dtype=np.float32)
    for k in range(m):
        base_idx = k - 1
        t_start = base_idx - impulse_bars
        if t_start < 0:
            continue
        p0 = closes[t_start]
        p1 = closes[base_idx]
        if p0 > 0:
            impulse_pct[k] = (p1 - p0) / p0 * 100

    return {
        "top":       win_high,
        "bottom":    win_low,
        "range_pct": range_pct,
        "top_touch": top_touch.astype(np.int32),
        "bot_touch": bot_touch.astype(np.int32),
        "top_flat":  top_flat_pct,
        "bot_flat":  bot_flat_pct,
        "impulse":   impulse_pct,
        "W":         W,
    }


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

    df = calculate_indicators(df)

    highs  = df["High"].values.astype(float)
    lows   = df["Low"].values.astype(float)
    opens  = df["Open"].values.astype(float)
    closes = df["Close"].values.astype(float)
    n      = len(df)

    tol = CONFIG["TOUCH_TOLERANCE_PCT"] / 100.0
    buf = CONFIG["BREAKOUT_BUFFER_PCT"] / 100.0
    imp_bars = CONFIG["IMPULSE_LOOKBACK"]

    patterns = []
    last_signal_pos = -10**9

    for W in CONFIG["WINDOW_SIZES"]:
        if W + imp_bars + 5 > n:
            continue
        M = _window_metrics(highs, lows, opens, closes, W, tol, imp_bars)
        if M is None:
            continue

        valid = (
            (M["range_pct"] >= CONFIG["MIN_RANGE_PCT"]) &
            (M["range_pct"] <= CONFIG["MAX_RANGE_PCT"]) &
            (M["top_touch"] >= CONFIG["MIN_TOP_TOUCHES"]) &
            (M["bot_touch"] >= CONFIG["MIN_BOT_TOUCHES"]) &
            (M["top_flat"] <= CONFIG["FLATNESS_MAX_PCT"]) &
            (M["bot_flat"] <= CONFIG["FLATNESS_MAX_PCT"]) &
            (np.abs(M["impulse"]) >= CONFIG["MIN_IMPULSE_PCT"])
        )
        valid_idx = np.where(valid)[0]
        if len(valid_idx) == 0:
            continue

        for k in valid_idx:
            end_window = int(k + W - 1)
            breakout_idx = end_window + 1
            if breakout_idx >= n:
                continue
            if breakout_idx - last_signal_pos < CONFIG["MIN_BARS_BETWEEN"]:
                continue

            close_bk = closes[breakout_idx]
            open_bk  = opens[breakout_idx]
            prev_c   = closes[breakout_idx - 1]

            body_pct = abs(close_bk - open_bk) / max(close_bk, 1e-9) * 100
            if body_pct < CONFIG["MIN_BREAKOUT_BODY_PCT"]:
                continue

            box_high = float(M["top"][k])
            box_low  = float(M["bottom"][k])
            impulse  = float(M["impulse"][k])
            up_thr   = box_high * (1 + buf)
            down_thr = box_low  * (1 - buf)

            direction = None
            if prev_c <= up_thr and close_bk > up_thr and close_bk > open_bk:
                direction = "BUY"
            elif prev_c >= down_thr and close_bk < down_thr and close_bk < open_bk:
                direction = "SELL"

            if direction is None:
                continue

            info = {
                "top":         box_high,
                "bottom":      box_low,
                "range_pct":   float(M["range_pct"][k]),
                "top_touch":   int(M["top_touch"][k]),
                "bot_touch":   int(M["bot_touch"][k]),
                "top_flat":    float(M["top_flat"][k]),
                "bot_flat":    float(M["bot_flat"][k]),
                "impulse_pct": impulse,
                "start":       int(k),
                "end":         end_window,
                "W":           W,
            }
            pattern = _build_pattern(df, breakout_idx, info, direction, body_pct,
                                     highs, lows, closes)
            if pattern:
                patterns.append(pattern)
                last_signal_pos = breakout_idx

    patterns.sort(key=lambda p: p["end_pos"])
    return patterns


def _build_pattern(df, idx, info, direction, body_pct,
                   highs, lows, closes):
    """ملاحظة: كل الإحداثيات positions (int) — متوافقة مع reset_index."""
    entry = float(closes[idx])
    box_high = info["top"]
    box_low  = info["bottom"]
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
    start_p = info["start"]
    end_p   = info["end"]

    # ── nodes: positions (int) ───────────────────────────────────────
    tol_vis = CONFIG["TOUCH_TOLERANCE_PCT"] / 100.0 * 1.5
    seg_h = highs[start_p:end_p + 1]
    seg_l = lows [start_p:end_p + 1]

    top_thr = box_high * (1 - tol_vis)
    bot_thr = box_low  * (1 + tol_vis)

    top_hits = np.where(seg_h >= top_thr)[0]
    bot_hits = np.where(seg_l <= bot_thr)[0]

    touch_list = []
    for p in top_hits:
        touch_list.append((int(start_p + p), box_high))
    for p in bot_hits:
        touch_list.append((int(start_p + p), box_low))
    touch_list.sort()

    nodes = [(pos, val) for pos, val in touch_list]
    nodes.append((int(idx), entry))

    # ── arrow: positions (int) ───────────────────────────────────────
    arrow_len = max(8, (end_p - start_p) // 3)
    x1_pos = min(idx + arrow_len, len(df) - 1)
    arrow = {
        "x0": int(idx),      "y0": entry,
        "x1": int(x1_pos),   "y1": tp,
        "direction": direction,
    }

    box_data = {
        "x_start": int(start_p),
        "x_end":   int(idx),
        "high":    round(box_high, 5),
        "low":     round(box_low, 5),
    }

    pattern = {
        "name": "Rectangle Reversal",
        "pattern": (
            f"Rectangle {direction} · "
            f"T{info['top_touch']}/B{info['bot_touch']} · "
            f"imp {info['impulse_pct']:+.2f}%"
        ),
        "bias": bias,
        "direction": direction,
        "match": float(min(100, 55 + (info["top_touch"] + info["bot_touch"]) * 6)),
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
        "channel_start": int(start_p),
        "channel_end":   int(end_p),
        "channel_duration_bars": int(info["W"]),
        "channel_range_pct": round(info["range_pct"], 3),
        "neckline_start_idx": int(start_p),
        "neckline_end_idx":   int(idx),
        "end_pos": int(idx),
        "Entry Conditions": (
            f"Impulse {info['impulse_pct']:+.2f}% → rectangle {info['W']} bars "
            f"({info['range_pct']:.2f}%, T{info['top_touch']}/B{info['bot_touch']}, "
            f"flat {info['top_flat']:.2f}/{info['bot_flat']:.2f}) → close breakout"
        ),
        "consol_high": round(box_high, 5),
        "consol_low":  round(box_low, 5),
        "consol_bars": int(info["W"]),
        "consol_range_pct": round(info["range_pct"], 3),
        "consol_stability_pct": 100.0,
        "breakout_body_pct": round(body_pct, 3),
        "top_touches": info["top_touch"],
        "bot_touches": info["bot_touch"],
        "top_flatness_pct": round(info["top_flat"], 4),
        "bot_flatness_pct": round(info["bot_flat"], 4),
        "impulse_pct": round(info["impulse_pct"], 3),
    }

    pattern.update(simulate_trade_outcome(pattern, df))
    return pattern


def simulate_trade_outcome(pattern, df):
    bias    = pattern["bias"]
    entry   = float(pattern["entry"])
    sl      = float(pattern["sl"])
    tp      = float(pattern["tp"])
    end_idx = pattern["neckline_end_idx"]   # position (int)

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
    lows_arr  = post["Low"].values.astype(float)
    closes_arr = post["Close"].values.astype(float)
    dates_arr = post.index.values

    is_bear = (bias == "Bearish")
    for i in range(1, len(post)):
        high = highs_arr[i]; low = lows_arr[i]
        if is_bear:
            fav = max(0.0, entry - low); adv = max(0.0, high - entry)
        else:
            fav = max(0.0, high - entry); adv = max(0.0, entry - low)

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

    df_active = df.tail(800).copy().reset_index(drop=True)
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
            "Loss Category": p.get("Loss Category"),
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
            "breakout_body_pct": p.get("breakout_body_pct"),
            "top_touches":  p.get("top_touches"),
            "bot_touches":  p.get("bot_touches"),
            "top_flatness_pct": p.get("top_flatness_pct"),
            "bot_flatness_pct": p.get("bot_flatness_pct"),
            "impulse_pct":  p.get("impulse_pct"),
        })
    return trades


def detect_all_head_shoulders(*a, **kw):
    return []


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
        "1. Rectangle + impulse": {"before": len(trades), "after": len(trades), "rejected": 0, "pass_rate": "—"},
        "2. Close breakout":      {"before": len(trades), "after": len(trades), "rejected": 0, "pass_rate": "—"},
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
    print("ENGINE.PY — Rectangle Reversal v14.1 (positions-based)")
    print(f"Windows: {CONFIG['WINDOW_SIZES']}")
    print(f"Touches: top≥{CONFIG['MIN_TOP_TOUCHES']} | bot≥{CONFIG['MIN_BOT_TOUCHES']} | tol ±{CONFIG['TOUCH_TOLERANCE_PCT']}%")
    print(f"Flatness ≤ {CONFIG['FLATNESS_MAX_PCT']}% | Impulse ≥ {CONFIG['MIN_IMPULSE_PCT']}%")
    print(f"Breakout body ≥ {CONFIG['MIN_BREAKOUT_BODY_PCT']}% | TP = {CONFIG['TP_RR']}×")
