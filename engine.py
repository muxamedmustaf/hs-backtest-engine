# -*- coding: utf-8 -*-
"""
ENGINE.PY — Horizontal Channel Breakout (v4)
=============================================
منطق الإشارة (مطابق للصور):
  1) حصر السعر 5 أيام+ في قناة أفقية (قمم متساوية + قيعان متساوية).
  2) انتظار إغلاق شمعة فوق المقاومة الأخيرة (BUY) أو تحت الدعم (SELL).
  3) الوقف تحت القاع / فوق القمة، الهدف = 3× الوقف.
  4) خط متعرج يربط نقاط التصحيح داخل الصندوق + سهم بطول الهدف.
"""
import pandas as pd
import numpy as np


CONFIG = {
    "ZIGZAG_DEPTH": 5,
    "ZIGZAG_BACKSTEP": 3,
    # ── نافذة التجميع الأفقي ─────────────────────────────────────────────
    "MIN_CONSOL_DAYS": 5,            # أقل مدة للحصر (أيام)
    "MAX_CONSOL_DAYS": 40,           # سقف منطقي
    "LEVEL_TOLERANCE_PCT": 0.35,     # % التقارب بين القمم (أو القيعان)
    "MIN_TOUCHES": 2,                # كل جهة تحتاج لمستين على الأقل
    "MAX_RANGE_PCT": 4.0,            # أقصى ارتفاع للقناة كنسبة من السعر
    # ── الكسر ────────────────────────────────────────────────────────────
    "BREAKOUT_BUFFER_PCT": 0.02,     # الإغلاق يجب أن يتجاوز المستوى بـ %
    "MIN_BREAKOUT_BODY_PCT": 0.05,   # جسم شمعة الكسر
    # ── SL / TP ──────────────────────────────────────────────────────────
    "SL_BUFFER_PCT": 0.05,           # هامش صغير تحت/فوق المستوى
    "TP_RR": 3.0,                    # الهدف = 3× الوقف
    # ── فلاتر ────────────────────────────────────────────────────────────
    "MIN_BARS_BETWEEN": 5,
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
    """قدّر عدد الشموع لعدد الأيام حسب الإطار الزمني."""
    bars_per_day = {
        "1m": 1440, "2m": 720, "3m": 480, "4m": 360, "5m": 288,
        "10m": 144, "15m": 96, "30m": 48, "45m": 32,
        "1h": 24, "2h": 12, "3h": 8, "4h": 6, "6h": 4, "8h": 3, "12h": 2,
        "1d": 1, "2d": 0.5, "3d": 0.33, "1wk": 0.2, "1mo": 0.05,
    }
    bpd = bars_per_day.get(interval, 24)
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


def calculate_zigzag(df, depth=5, backstep=3):
    df = df.copy()
    df["Pivot_H"] = np.nan
    df["Pivot_L"] = np.nan
    highs = df["High"].astype(float).values
    lows = df["Low"].astype(float).values
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
            raw.append({"idx": idx, "pos": pos, "val": float(row["Pivot_H"]),
                        "type": "H"})
        elif not pd.isna(row["Pivot_L"]):
            raw.append({"idx": idx, "pos": pos, "val": float(row["Pivot_L"]),
                        "type": "L"})
    if not raw:
        return []
    # احتفظ بالتناوب فقط H-L-H-L... مع اختيار الأقصى/الأدنى عند التكرار
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
# Clustering — تجميع القمم/القيعان في خطوط أفقية
# ══════════════════════════════════════════════════════════════════════════════
def cluster_levels(pivots, tolerance):
    if not pivots:
        return []
    sorted_p = sorted(pivots, key=lambda p: p["val"])
    levels = []
    for p in sorted_p:
        merged = False
        for lvl in levels:
            if abs(p["val"] - lvl["price"]) / max(lvl["price"], 1e-9) <= tolerance:
                lvl["values"].append(p["val"])
                lvl["price"] = float(np.mean(lvl["values"]))
                lvl["touches"] += 1
                lvl["first_pos"] = min(lvl["first_pos"], p["pos"])
                lvl["last_pos"]  = max(lvl["last_pos"],  p["pos"])
                lvl["members"].append(p)
                merged = True
                break
        if not merged:
            levels.append({
                "price":     p["val"],
                "values":    [p["val"]],
                "touches":   1,
                "first_pos": p["pos"],
                "last_pos":  p["pos"],
                "members":   [p],
            })
    return levels


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
    df = df.dropna(subset=["Open", "High", "Low", "Close"])
    if len(df) < CONFIG["MIN_BARS_REQUIRED"]:
        return []

    df = calculate_indicators(df)
    df = calculate_zigzag(df, CONFIG["ZIGZAG_DEPTH"], CONFIG["ZIGZAG_BACKSTEP"])
    pivots = get_chronological_pivots(df)
    if len(pivots) < 4:
        return []

    min_bars = _days_to_bars(CONFIG["MIN_CONSOL_DAYS"], interval)
    max_bars = _days_to_bars(CONFIG["MAX_CONSOL_DAYS"], interval)
    tol      = CONFIG["LEVEL_TOLERANCE_PCT"] / 100.0
    buf      = CONFIG["BREAKOUT_BUFFER_PCT"] / 100.0
    backstep = CONFIG["ZIGZAG_BACKSTEP"]

    n = len(df)
    patterns = []
    last_signal_pos = -10**9

    for i in range(CONFIG["MIN_BARS_REQUIRED"], n):
        # البيفوتات المتاحة (مؤكدة + داخل نافذة زمنية)
        active = [p for p in pivots
                  if (p["pos"] + backstep) <= i and (i - p["pos"]) <= max_bars]
        if len(active) < 4:
            continue

        highs = [p for p in active if p["type"] == "H"]
        lows  = [p for p in active if p["type"] == "L"]
        if len(highs) < CONFIG["MIN_TOUCHES"] or len(lows) < CONFIG["MIN_TOUCHES"]:
            continue

        # جمّع القمم في خط مقاومة، والقيعان في خط دعم
        high_levels = cluster_levels(highs, tol)
        low_levels  = cluster_levels(lows,  tol)
        high_levels = [l for l in high_levels if l["touches"] >= CONFIG["MIN_TOUCHES"]]
        low_levels  = [l for l in low_levels  if l["touches"] >= CONFIG["MIN_TOUCHES"]]
        if not high_levels or not low_levels:
            continue

        # اختر أفضل قناة: أطول مدة + أكثر لمسات
        best = None
        for h in high_levels:
            for l in low_levels:
                if h["price"] <= l["price"]:
                    continue
                first    = min(h["first_pos"], l["first_pos"])
                last     = max(h["last_pos"],  l["last_pos"])
                duration = last - first
                if duration < min_bars:
                    continue
                range_pct = (h["price"] - l["price"]) / l["price"] * 100
                if range_pct > CONFIG["MAX_RANGE_PCT"]:
                    continue
                score = h["touches"] + l["touches"] + duration / 20.0
                if best is None or score > best["score"]:
                    best = {
                        "resistance": h, "support": l,
                        "start_pos": first, "end_pos": last,
                        "score": score, "range_pct": range_pct,
                        "duration_bars": duration,
                    }

        if best is None:
            continue

        # فحص شمعة الكسر عند i
        candle = df.iloc[i]
        prev   = df.iloc[i - 1]
        close      = float(candle["Close"])
        open_      = float(candle["Open"])
        prev_close = float(prev["Close"])

        body_pct = abs(close - open_) / max(close, 1e-9) * 100
        if body_pct < CONFIG["MIN_BREAKOUT_BODY_PCT"]:
            continue

        res = float(best["resistance"]["price"])
        sup = float(best["support"]["price"])
        up_thr   = res * (1 + buf)
        down_thr = sup * (1 - buf)

        direction = None
        if prev_close <= up_thr and close > up_thr and close > open_:
            direction = "BUY"
        elif prev_close >= down_thr and close < down_thr and close < open_:
            direction = "SELL"

        if direction is None:
            continue

        if i - last_signal_pos < CONFIG["MIN_BARS_BETWEEN"]:
            continue

        pattern = _build_channel_pattern(df, i, best, direction, body_pct)
        if pattern:
            patterns.append(pattern)
            last_signal_pos = i

    return patterns


def _build_channel_pattern(df, idx, channel, direction, body_pct):
    candle = df.iloc[idx]
    entry  = float(candle["Close"])

    res = float(channel["resistance"]["price"])
    sup = float(channel["support"]["price"])
    sl_buf = CONFIG["SL_BUFFER_PCT"] / 100.0

    if direction == "BUY":
        # الوقف تحت القاع الأفقي (الدعم)
        sl = sup * (1 - sl_buf)
        if sl >= entry:
            return None
        risk = entry - sl
        if risk <= 0:
            return None
        tp = entry + CONFIG["TP_RR"] * risk
    else:
        # الوقف فوق القمة الأفقية (المقاومة)
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

    # ── نقاط التعرج (ZigZag) داخل الصندوق ─────────────────────────────
    start_p = channel["start_pos"]
    end_p   = channel["end_pos"]
    inner_pivots = []
    for _, row in df.iloc[start_p:end_p + 1].iterrows():
        pass
    # نستخدم البيفوتات الخام مباشرة
    inner = []
    for pos in range(start_p, min(end_p + 1, len(df))):
        row = df.iloc[pos]
        if not pd.isna(row["Pivot_H"]):
            inner.append((df.index[pos], float(row["Pivot_H"])))
        elif not pd.isna(row["Pivot_L"]):
            inner.append((df.index[pos], float(row["Pivot_L"])))

    nodes = inner + [(df.index[idx], entry)]

    # ضمان وجود 3 نقاط على الأقل لعرض الزجزاج
    if len(nodes) < 3:
        nodes = [
            (df.index[start_p], res),
            (df.index[(start_p + end_p) // 2], sup),
            (df.index[end_p], res),
            (df.index[idx], entry),
        ]

    # ── بيانات السهم (Arrow) من الدخول إلى الهدف ─────────────────────
    arrow = {
        "x0": df.index[idx],
        "y0": entry,
        "x1": df.index[min(idx + 20, len(df) - 1)],
        "y1": tp,
        "direction": direction,
    }

    # ── صندوق القناة (Consolidation Box) ─────────────────────────────
    box = {
        "x_start": start_p,
        "x_end":   end_p,
        "high":    res,
        "low":     sup,
    }

    pattern = {
        "name": "Horizontal Channel Breakout",
        "pattern": f"Channel → {direction} Breakout ({channel['resistance']['touches']}/{channel['support']['touches']} touches)",
        "bias": bias,
        "direction": direction,
        "match": float(min(100, 60 + (channel["resistance"]["touches"] + channel["support"]["touches"]) * 5)),
        "entry": round(entry, 5),
        "entry_trigger": round(entry, 5),
        "sl": round(sl, 5),
        "tp": round(tp, 5),
        "SL": round(sl, 5),
        "TP": round(tp, 5),
        "Entry": round(entry, 5),
        "nodes": nodes,
        "arrow": arrow,
        "consolidation_box": box,
        "resistance": round(res, 5),
        "support":    round(sup, 5),
        "level_price": round(res if direction == "BUY" else sup, 5),
        "level_touches": (channel["resistance"]["touches"] if direction == "BUY"
                          else channel["support"]["touches"]),
        "channel_start": df.index[start_p],
        "channel_end":   df.index[end_p],
        "channel_duration_bars": channel["duration_bars"],
        "channel_duration_days": round(channel["duration_bars"] / max(_days_to_bars(1, "1h") / 24, 1), 1),
        "channel_range_pct": round(channel["range_pct"], 3),
        "neckline_start_idx": df.index[start_p],
        "neckline_end_idx":   df.index[idx],
        "end_pos": idx,
        "Entry Conditions": (
            f"5d+ horizontal channel ({channel['resistance']['touches']} R / "
            f"{channel['support']['touches']} S touches) → close breakout"
        ),
        "consol_high": round(res, 5),
        "consol_low":  round(sup, 5),
        "consol_bars": int(channel["duration_bars"]),
        "consol_range_pct": round(channel["range_pct"], 3),
        "consol_stability_pct": 100.0,
        "breakout_body_pct": round(body_pct, 3),
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


# ══════════════════════════════════════════════════════════════════════════════
# Backward-compat alias (يستخدمه التطبيق في detect_near_signals)
# ══════════════════════════════════════════════════════════════════════════════
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
        "1. Horizontal Channel (5d+)": {"before": len(trades), "after": len(trades), "rejected": 0, "pass_rate": "—"},
        "2. Close Breakout":           {"before": len(trades), "after": len(trades), "rejected": 0, "pass_rate": "—"},
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
    print("ENGINE.PY — Horizontal Channel Breakout v4")
    print(f"Channel: ≥{CONFIG['MIN_CONSOL_DAYS']} days | tolerance: {CONFIG['LEVEL_TOLERANCE_PCT']}% | min touches/side: {CONFIG['MIN_TOUCHES']}")
    print(f"Breakout: close beyond level by {CONFIG['BREAKOUT_BUFFER_PCT']}% | body ≥ {CONFIG['MIN_BREAKOUT_BODY_PCT']}%")
    print(f"SL: {CONFIG['SL_BUFFER_PCT']}% beyond opposite side | TP = {CONFIG['TP_RR']}× risk (1:{CONFIG['TP_RR']:.0f})")
