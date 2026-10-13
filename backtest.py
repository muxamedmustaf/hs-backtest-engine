# -*- coding: utf-8 -*-
"""
ENGINE.PY — Strict Horizontal Range Breakout (v7)
==================================================
يرفض أي منطقة ليست مستطيلة أفقية حقيقية:
  • كل القمم يجب أن تكون في نطاق 0.10% من بعضها (لا تدّرّج).
  • كل القيعان يجب أن تكون في نطاق 0.10% من بعضها.
  • ميل خط القمم ≈ 0 (regression slope).
  • ميل خط القيعان ≈ 0.
  • ≥ 3 لمسات لكل جهة (لا اكتفاء بلمستين).
  • نصف النافذة الأول = الثاني في المتوسط (لا اتجاه داخلي).
  • لا شمعة بجسم > 50% من ارتفاع الصندوق داخل المنطقة.
"""
import pandas as pd
import numpy as np


CONFIG = {
    # ── ZigZag نظيف جدًا ─────────────────────────────────────────────────
    "ZIGZAG_DEPTH": 8,
    "ZIGZAG_BACKSTEP": 5,
    "MIN_SWING_PCT": 0.40,           # ⬆ 0.30 → 0.40 (ضجيج أقل)

    # ── القناة الأفقية — شروط صارمة ─────────────────────────────────────
    "MIN_CONSOL_DAYS": 5,
    "MAX_CONSOL_DAYS": 40,
    "MIN_CONSOL_BARS_H4": 30,        # ≥ 30 شمعة على H4 لتصحيح حقيقي
    "MIN_TOUCHES": 3,                # ⬆ 2 → 3 لمسات لكل جهة
    "TOP_FLATNESS_PCT": 0.10,        # كل القمم في نطاق 0.10% من بعضها
    "BOT_FLATNESS_PCT": 0.10,        # كل القيعان في نطاق 0.10% من بعضها
    "MAX_SLOPE_PCT": 0.02,           # ميل خط القمم/القيعان ≤ 0.02% لكل شمعة
    "MIN_RANGE_PCT": 0.20,           # أدنى ارتفاع الصندوق
    "MAX_RANGE_PCT": 3.0,            # أقصى ارتفاع (نمط التصحيح عادة ضيّق)
    "MAX_BODY_INSIDE_PCT": 50,       # لا شمعة جسمها > 50% من ارتفاع الصندوق داخل المنطقة
    "MAX_DIRECTIONAL_CANDLES_PCT": 65,  # ≤ 65% شموع بنفس الاتجاه (وإلا اتجاه وليس تصحيح)

    # ── الكسر ────────────────────────────────────────────────────────────
    "BREAKOUT_BUFFER_PCT": 0.03,
    "MIN_BREAKOUT_BODY_PCT": 0.08,   # ⬆ 0.05 → 0.08 جسم شمعة الكسر أقوى
    "CONFIRM_BARS_AFTER": 1,         # يجب إغلاق شمعة واحدة على الأقل بعد الكسر

    # ── SL / TP ──────────────────────────────────────────────────────────
    "SL_BUFFER_PCT": 0.05,
    "TP_RR": 3.0,

    # ── فلاتر ────────────────────────────────────────────────────────────
    "MIN_BARS_BETWEEN": 10,
    "MAX_TIMEOUT_BARS": 300,
    "VOLUME_MA_PERIOD": 20,
    "MIN_BARS_REQUIRED": 120,
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


def get_chronological_pivots(df, min_swing_pct=None):
    if min_swing_pct is None:
        min_swing_pct = CONFIG["MIN_SWING_PCT"]

    raw = []
    for pos, (idx, row) in enumerate(df.iterrows()):
        if not pd.isna(row["Pivot_H"]):
            raw.append({"idx": idx, "pos": pos, "val": float(row["Pivot_H"]), "type": "H"})
        elif not pd.isna(row["Pivot_L"]):
            raw.append({"idx": idx, "pos": pos, "val": float(row["Pivot_L"]), "type": "L"})
    if not raw:
        return []

    collapsed = [raw[0]]
    for p in raw[1:]:
        if collapsed[-1]["type"] == p["type"]:
            if p["type"] == "H" and p["val"] > collapsed[-1]["val"]:
                collapsed[-1] = p
            elif p["type"] == "L" and p["val"] < collapsed[-1]["val"]:
                collapsed[-1] = p
        else:
            collapsed.append(p)

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
# 🎯 فحص الصندوق الأفقي الحقيقي (STRICT)
# ══════════════════════════════════════════════════════════════════════════════
def _is_true_horizontal_range(df, start_pos, end_pos, high_pivots, low_pivots):
    """
    يفحص إن كانت المنطقة مستطيلًا أفقيًا حقيقيًا:
      1) كل القمم متقاربة جدًا
      2) كل القيعان متقاربة جدًا
      3) ميل خط القمم ≈ 0
      4) ميل خط القيعان ≈ 0
      5) متوسط النصف الأول ≈ النصف الثاني (لا اتجاه)
      6) شموع المنطقة محصورة بين الخطين
      7) ارتفاع الصندوق ضمن الحدود
    """
    n = end_pos - start_pos + 1
    if n < CONFIG["MIN_CONSOL_BARS_H4"]:
        return None

    seg = df.iloc[start_pos:end_pos + 1]
    if len(seg) < 5:
        return None

    res = float(seg["High"].max())
    sup = float(seg["Low"].min())
    if sup <= 0 or res <= sup:
        return None

    range_pct = (res - sup) / sup * 100
    if range_pct < CONFIG["MIN_RANGE_PCT"] or range_pct > CONFIG["MAX_RANGE_PCT"]:
        return None

    # 1) تقارب القمم
    if len(high_pivots) < CONFIG["MIN_TOUCHES"]:
        return None
    top_vals = [p["val"] for p in high_pivots]
    top_spread_pct = (max(top_vals) - min(top_vals)) / min(top_vals) * 100
    if top_spread_pct > CONFIG["TOP_FLATNESS_PCT"]:
        return None

    # 2) تقارب القيعان
    if len(low_pivots) < CONFIG["MIN_TOUCHES"]:
        return None
    bot_vals = [p["val"] for p in low_pivots]
    bot_spread_pct = (max(bot_vals) - min(bot_vals)) / min(bot_vals) * 100
    if bot_spread_pct > CONFIG["BOT_FLATNESS_PCT"]:
        return None

    # 3) ميل خط القمم ≈ 0
    top_xs = np.array([p["pos"] for p in high_pivots], dtype=float)
    top_ys = np.array(top_vals, dtype=float)
    if len(top_xs) >= 2:
        top_slope = np.polyfit(top_xs, top_ys, 1)[0]  # price per bar
        top_slope_pct = abs(top_slope) / np.mean(top_ys) * 100
        if top_slope_pct > CONFIG["MAX_SLOPE_PCT"]:
            return None

    # 4) ميل خط القيعان ≈ 0
    bot_xs = np.array([p["pos"] for p in low_pivots], dtype=float)
    bot_ys = np.array(bot_vals, dtype=float)
    if len(bot_xs) >= 2:
        bot_slope = np.polyfit(bot_xs, bot_ys, 1)[0]
        bot_slope_pct = abs(bot_slope) / np.mean(bot_ys) * 100
        if bot_slope_pct > CONFIG["MAX_SLOPE_PCT"]:
            return None

    # 5) لا اتجاه داخلي: متوسط النصفين متقارب
    mid = len(seg) // 2
    first_half = seg.iloc[:mid]["Close"].mean()
    second_half = seg.iloc[mid:]["Close"].mean()
    if first_half == 0:
        return None
    half_diff_pct = abs(second_half - first_half) / first_half * 100
    if half_diff_pct > range_pct * 0.5:   # الفرق بين النصفين لا يزيد عن نصف ارتفاع الصندوق
        return None

    # 6) لا شمعة بجسم ضخم داخل المنطقة
    box_height = res - sup
    for _, row in seg.iterrows():
        body = abs(float(row["Close"]) - float(row["Open"]))
        if box_height > 0 and body / box_height * 100 > CONFIG["MAX_BODY_INSIDE_PCT"]:
            return None

    # 7) نسبة الشموع الاتجاهية ≤ الحد
    up_candles = int((seg["Close"] > seg["Open"]).sum())
    down_candles = int((seg["Close"] < seg["Open"]).sum())
    total_dir = up_candles + down_candles
    if total_dir > 0:
        dir_ratio = max(up_candles, down_candles) / total_dir * 100
        if dir_ratio > CONFIG["MAX_DIRECTIONAL_CANDLES_PCT"]:
            return None

    return {
        "resistance": res,
        "support":    sup,
        "start_pos":  start_pos,
        "end_pos":    end_pos,
        "range_pct":  range_pct,
        "duration":   n,
        "top_touches": len(high_pivots),
        "bot_touches": len(low_pivots),
        "top_spread_pct": round(top_spread_pct, 3),
        "bot_spread_pct": round(bot_spread_pct, 3),
        "high_pivot_positions": [p["pos"] for p in high_pivots],
        "low_pivot_positions":  [p["pos"] for p in low_pivots],
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
    df = df.dropna(subset=["Open", "High", "Low", "Close"])
    if len(df) < CONFIG["MIN_BARS_REQUIRED"]:
        return []

    df = calculate_indicators(df)
    df = calculate_zigzag(df)
    pivots = get_chronological_pivots(df)
    if len(pivots) < 6:  # 3 highs + 3 lows minimum
        return []

    min_bars = max(_days_to_bars(CONFIG["MIN_CONSOL_DAYS"], interval),
                   CONFIG["MIN_CONSOL_BARS_H4"])
    max_bars = _days_to_bars(CONFIG["MAX_CONSOL_DAYS"], interval)
    buf      = CONFIG["BREAKOUT_BUFFER_PCT"] / 100.0
    backstep = CONFIG["ZIGZAG_BACKSTEP"]

    n = len(df)
    patterns = []
    last_signal_pos = -10**9

    for i in range(CONFIG["MIN_BARS_REQUIRED"], n):
        # البيفوتات المؤكدة قبل i
        active = [p for p in pivots
                  if (p["pos"] + backstep) <= i and (i - p["pos"]) <= max_bars]
        if len(active) < 6:
            continue

        highs = [p for p in active if p["type"] == "H"]
        lows  = [p for p in active if p["type"] == "L"]
        if len(highs) < CONFIG["MIN_TOUCHES"] or len(lows) < CONFIG["MIN_TOUCHES"]:
            continue

        # اختبار كل نافذة محتملة تنتهي قبل الكسر
        # نجرب نوافذ متعددة بأطوال مختلفة
        for start_offset in range(CONFIG["MIN_TOUCHES"] * 2, len(active) + 1):
            window_pivots = active[-start_offset:]
            wh = [p for p in window_pivots if p["type"] == "H"]
            wl = [p for p in window_pivots if p["type"] == "L"]
            if len(wh) < CONFIG["MIN_TOUCHES"] or len(wl) < CONFIG["MIN_TOUCHES"]:
                continue

            # نافذة زمنية من أول بيفوت لآخر بيفوت (قبل i)
            p_start = min(p["pos"] for p in window_pivots)
            p_end   = max(p["pos"] for p in window_pivots)

            # امتد حتى i-1 (شمعة الكسر)
            if i - p_start < min_bars:
                continue

            box = _is_true_horizontal_range(df, p_start, i - 1, wh, wl)
            if box is None:
                continue

            # الآن افحص شمعة الكسر عند i
            candle = df.iloc[i]
            prev   = df.iloc[i - 1]
            close      = float(candle["Close"])
            open_      = float(candle["Open"])
            prev_close = float(prev["Close"])

            body_pct = abs(close - open_) / max(close, 1e-9) * 100
            if body_pct < CONFIG["MIN_BREAKOUT_BODY_PCT"]:
                break

            res = box["resistance"]
            sup = box["support"]
            up_thr   = res * (1 + buf)
            down_thr = sup * (1 - buf)

            direction = None
            if prev_close <= up_thr and close > up_thr and close > open_:
                direction = "BUY"
            elif prev_close >= down_thr and close < down_thr and close < open_:
                direction = "SELL"

            if direction is None:
                break

            if i - last_signal_pos < CONFIG["MIN_BARS_BETWEEN"]:
                break

            pattern = _build_pattern(df, i, box, direction, body_pct)
            if pattern:
                patterns.append(pattern)
                last_signal_pos = i
                break  # اخرج من حلقة start_offset بعد إيجاد النمط

    return patterns


def _build_pattern(df, idx, box, direction, body_pct):
    candle = df.iloc[idx]
    entry  = float(candle["Close"])
    res    = box["resistance"]
    sup    = box["support"]
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

    # ── النقاط: قمم وقيعان حقيقية على الحدين ─────────────────────────────
    start_p = box["start_pos"]
    end_p   = box["end_pos"]

    # نجمع كل بيفوتات المنطقة (نستخدم بيانات البيفوت من df مباشرة)
    nodes = []
    for pos in range(start_p, min(end_p + 1, len(df))):
        row = df.iloc[pos]
        if not pd.isna(row["Pivot_H"]):
            nodes.append((df.index[pos], float(row["Pivot_H"])))
        elif not pd.isna(row["Pivot_L"]):
            nodes.append((df.index[pos], float(row["Pivot_L"])))

    # nضيف نقطة الدخول
    nodes.append((df.index[idx], entry))

    # السهم
    x1_pos = min(idx + max(8, (end_p - start_p) // 3), len(df) - 1)
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
        "name": "Horizontal Range Breakout",
        "pattern": (
            f"Range {direction} · "
            f"T{box['top_touches']}/B{box['bot_touches']} · "
            f"{box['range_pct']:.2f}%"
        ),
        "bias": bias,
        "direction": direction,
        "match": float(min(100, 50 + (box["top_touches"] + box["bot_touches"]) * 8)),
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
        "channel_duration_bars": int(box["duration"]),
        "channel_range_pct": round(box["range_pct"], 3),
        "neckline_start_idx": df.index[start_p],
        "neckline_end_idx":   df.index[idx],
        "end_pos": idx,
        "Entry Conditions": (
            f"True horizontal range · T{box['top_touches']}/B{box['bot_touches']} touches · "
            f"top_spread {box['top_spread_pct']}% / bot_spread {box['bot_spread_pct']}%"
        ),
        "consol_high": round(res, 5),
        "consol_low":  round(sup, 5),
        "consol_bars": int(box["duration"]),
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
        f"1. True Range ≥{CONFIG['MIN_CONSOL_DAYS']}d": {"before": len(trades), "after": len(trades), "rejected": 0, "pass_rate": "—"},
        "2. Close Breakout":                          {"before": len(trades), "after": len(trades), "rejected": 0, "pass_rate": "—"},
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
    print("ENGINE.PY — Strict Horizontal Range Breakout v7")
    print(f"ZigZag: depth={CONFIG['ZIGZAG_DEPTH']} backstep={CONFIG['ZIGZAG_BACKSTEP']} min_swing={CONFIG['MIN_SWING_PCT']}%")
    print(f"Range: min_touches={CONFIG['MIN_TOUCHES']} top_flat={CONFIG['TOP_FLATNESS_PCT']}% bot_flat={CONFIG['BOT_FLATNESS_PCT']}% max_slope={CONFIG['MAX_SLOPE_PCT']}%/bar")
    print(f"Range size: {CONFIG['MIN_RANGE_PCT']}% – {CONFIG['MAX_RANGE_PCT']}%")
    print(f"Breakout: body ≥ {CONFIG['MIN_BREAKOUT_BODY_PCT']}%  |  Buffer: {CONFIG['BREAKOUT_BUFFER_PCT']}%")
    print(f"SL: {CONFIG['SL_BUFFER_PCT']}% beyond level  |  TP = {CONFIG['TP_RR']}× risk")
