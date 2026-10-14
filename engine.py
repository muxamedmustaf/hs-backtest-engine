# -*- coding: utf-8 -*-
"""
ENGINE.PY — Pivot-Based Rectangle Reversal (v21)
==================================================
نهج جديد كلياً:
  • ZigZag لاكتشاف القمم والقيعان الفعلية
  • القمم = نقاط الانعكاس الحقيقية (swing highs)
  • القيعان = نقاط الانعكاس الحقيقية (swing lows)
  • المستطيل = 3+ قمم متقاربة + 3+ قيعان متقاربة
  • الكسر = إغلاق شمعة خارج الحدين
"""
import numpy as np
import pandas as pd


# ══════════════════════════════════════════════════════════════════════════════
# CONFIG
# ══════════════════════════════════════════════════════════════════════════════
CONFIG = {
    # ── ZigZag ─────────────────────────────────────────────────────────
    "ZIGZAG_DEPTH": 5,           # عمق البيفوت
    "ZIGZAG_BACKSTEP": 3,        # التأخير
    "MIN_SWING_PCT": 0.15,       # أدنى تأرجح بين بيفوتين (%)

    # ── النافذة الزمنية ────────────────────────────────────────────────
    "MIN_WINDOW_BARS": 40,       # ≥ 40 شمعة (~أسبوع H4)
    "MAX_WINDOW_BARS": 300,      # ≤ 300 شمعة (~شهر H4)

    # ── عدد القمم/القيعان ──────────────────────────────────────────────
    "MIN_PEAKS": 3,              # ≥ 3 قمم حقيقية
    "MIN_VALLEYS": 3,            # ≥ 3 قيعان حقيقية
    "MIN_GAP_BETWEEN_PIVOTS": 2, # ≥ 2 شمعة بين أي بيفوتين

    # ── تقارب القمم/القيعان ────────────────────────────────────────────
    "PEAK_TOLERANCE_PCT": 0.30,   # مدى القمم ≤ 0.30% من وسيطها
    "VALLEY_TOLERANCE_PCT": 0.30, # مدى القيعان ≤ 0.30% من وسيطها

    # ── حجم المستطيل ───────────────────────────────────────────────────
    "MIN_RANGE_PCT": 0.20,       # أدنى ارتفاع
    "MAX_RANGE_PCT": 3.00,       # أقصى ارتفاع
    "MIN_ASPECT_RATIO": 1.5,     # عرض/ارتفاع ≥ 1.5 (يرفض العمودي)

    # ── الانطلاقة قبل ──────────────────────────────────────────────────
    "IMPULSE_LOOKBACK": 30,
    "MIN_IMPULSE_PCT": 0.80,

    # ── الكسر ──────────────────────────────────────────────────────────
    "BREAKOUT_BUFFER_PCT": 0.05,
    "MIN_BREAKOUT_BODY_PCT": 0.08,

    # ── SL/TP ──────────────────────────────────────────────────────────
    "SL_BUFFER_PCT": 0.05,
    "MIN_RR_ACCEPTED": 1.2,

    # ── عامة ───────────────────────────────────────────────────────────
    "MIN_BARS_BETWEEN": 15,
    "MAX_TIMEOUT_BARS": 300,
    "MIN_BARS_REQUIRED": 200,
}


_BARS_PER_WEEK = {
    "1h": 120, "4h": 30, "1d": 5, "1wk": 1,
}

def _week_to_bars(interval, weeks=1.0):
    b = _BARS_PER_WEEK.get(interval, 120)
    return max(10, int(b * weeks))


# ══════════════════════════════════════════════════════════════════════════════
# 🎯 ZigZag — اكتشاف القمم والقيعان الفعلية
# ══════════════════════════════════════════════════════════════════════════════
def calculate_zigzag(df, depth=5, backstep=3):
    """يرجع df مع أعمدة Pivot_H و Pivot_L."""
    df = df.copy()
    df["Pivot_H"] = np.nan
    df["Pivot_L"] = np.nan

    highs = df["High"].values.astype(float)
    lows  = df["Low"].values.astype(float)
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
    """
    يرجع قائمة مرتبة زمنياً من البيفوتات الحقيقية:
    [{"pos": int, "val": float, "type": "H"/"L", "idx": timestamp}]
    """
    if min_swing_pct is None:
        min_swing_pct = CONFIG["MIN_SWING_PCT"]

    raw = []
    ph = df["Pivot_H"].values
    pl = df["Pivot_L"].values
    for pos in range(len(df)):
        if not pd.isna(ph[pos]):
            raw.append({"pos": pos, "val": float(ph[pos]), "type": "H", "idx": df.index[pos]})
        elif not pd.isna(pl[pos]):
            raw.append({"pos": pos, "val": float(pl[pos]), "type": "L", "idx": df.index[pos]})

    if not raw:
        return []

    # دمج البيفوتات من نفس النوع (نأخذ الأقصى/الأدنى)
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
    return filtered


# ══════════════════════════════════════════════════════════════════════════════
# 🎯 البحث عن مستطيل من البيفوتات
# ══════════════════════════════════════════════════════════════════════════════
def find_rectangles_from_pivots(pivots, interval="4h"):
    """
    يبحث عن جميع المستطيلات الممكنة من القمم والقيعان.
    يرجع قائمة من الديكشنري:
      {
        "start_pos": int, "end_pos": int,
        "peaks": [...], "valleys": [...],
        "top": float, "bottom": float,
        "peak_spread_pct": float, "valley_spread_pct": float,
        "width_bars": int, "aspect_ratio": float,
      }
    """
    results = []
    min_bars = max(CONFIG["MIN_WINDOW_BARS"], _week_to_bars(interval, 1.0))
    n = len(pivots)
    if n < CONFIG["MIN_PEAKS"] + CONFIG["MIN_VALLEYS"]:
        return results

    # ── لكل نقطة بداية محتملة ───────────────────────────────────────────
    for i in range(n):
        # ── لكل نقطة نهاية (بعد ≥ min_bars من i) ──────────────────────
        for j in range(i + CONFIG["MIN_PEAKS"] + CONFIG["MIN_VALLEYS"], n):
            start_pos = pivots[i]["pos"]
            end_pos = pivots[j]["pos"]
            width = end_pos - start_pos

            if width < min_bars:
                continue
            if width > CONFIG["MAX_WINDOW_BARS"]:
                break  # النافذة كبيرة جداً

            # ── اجمع القمم والقيعان داخل النافذة ──────────────────────
            window_pivots = pivots[i:j + 1]
            peaks = [p for p in window_pivots if p["type"] == "H"]
            valleys = [p for p in window_pivots if p["type"] == "L"]

            if len(peaks) < CONFIG["MIN_PEAKS"]: continue
            if len(valleys) < CONFIG["MIN_VALLEYS"]: continue

            # ── تحقق أن البيفوتات متباعدة زمنياً ─────────────────────
            peak_positions = [p["pos"] for p in peaks]
            valley_positions = [p["pos"] for p in valleys]
            if not _spaced(peak_positions, CONFIG["MIN_GAP_BETWEEN_PIVOTS"]): continue
            if not _spaced(valley_positions, CONFIG["MIN_GAP_BETWEEN_PIVOTS"]): continue

            # ── احسب وسيط القمم والقيعان ────────────────────────────
            peak_vals = [p["val"] for p in peaks]
            valley_vals = [p["val"] for p in valleys]
            top = float(np.median(peak_vals))
            bottom = float(np.median(valley_vals))

            if top <= bottom: continue

            # ── تحقق من تقارب القمم والقيعان ─────────────────────────
            peak_spread = (max(peak_vals) - min(peak_vals)) / top * 100
            valley_spread = (max(valley_vals) - min(valley_vals)) / bottom * 100

            if peak_spread > CONFIG["PEAK_TOLERANCE_PCT"]: continue
            if valley_spread > CONFIG["VALLEY_TOLERANCE_PCT"]: continue

            # ── حجم المستطيل ────────────────────────────────────────
            range_pct = (top - bottom) / bottom * 100
            if not (CONFIG["MIN_RANGE_PCT"] <= range_pct <= CONFIG["MAX_RANGE_PCT"]): continue

            # ── نسبة العرض/الارتفاع ────────────────────────────────
            aspect_ratio = width / max(range_pct, 0.01)
            if aspect_ratio < CONFIG["MIN_ASPECT_RATIO"]: continue

            # ── تحقق من الانطلاقة قبل المستطيل ─────────────────────
            impulse = _check_impulse(pivots, i, start_pos)
            if abs(impulse) < CONFIG["MIN_IMPULSE_PCT"]: continue

            results.append({
                "start_pos": start_pos,
                "end_pos": end_pos,
                "start_idx": pivots[i]["idx"],
                "end_idx": pivots[j]["idx"],
                "peaks": peaks,
                "valleys": valleys,
                "top": top,
                "bottom": bottom,
                "peak_spread_pct": peak_spread,
                "valley_spread_pct": valley_spread,
                "width_bars": width,
                "range_pct": range_pct,
                "aspect_ratio": aspect_ratio,
                "impulse_pct": impulse,
                "n_peaks": len(peaks),
                "n_valleys": len(valleys),
            })

    return results


def _spaced(positions, min_gap):
    """تحقق أن المواضع متباعدة بـ ≥ min_gap."""
    if len(positions) < 2: return True
    sorted_pos = sorted(positions)
    for i in range(1, len(sorted_pos)):
        if sorted_pos[i] - sorted_pos[i-1] < min_gap:
            return False
    return True


def _check_impulse(pivots, pivot_idx, start_pos):
    """حركة السعر قبل البيفوت الأول من النافذة."""
    lookback = CONFIG["IMPULSE_LOOKBACK"]
    if pivot_idx == 0:
        return 0.0
    # ابحث عن بيفوت يسبق بداية النافذة بـ lookback شمعة
    target_pos = start_pos - lookback
    prev = None
    for p in pivots[:pivot_idx]:
        if p["pos"] <= target_pos:
            prev = p
        else:
            break
    if prev is None:
        prev = pivots[0]

    first = pivots[pivot_idx]
    if prev["val"] <= 0: return 0.0
    return (first["val"] - prev["val"]) / prev["val"] * 100


# ══════════════════════════════════════════════════════════════════════════════
# 🎯 الكشف عن الكسر
# ══════════════════════════════════════════════════════════════════════════════
def detect_breakout(df, rectangle, direction_check=True):
    """
    يبحث عن أول شمعة تكسر المستطيل بعد end_pos.
    يرجع dict أو None.
    """
    closes = df["Close"].values.astype(float)
    opens = df["Open"].values.astype(float)
    n = len(df)
    buf = CONFIG["BREAKOUT_BUFFER_PCT"] / 100.0
    end_pos = rectangle["end_pos"]
    top = rectangle["top"]
    bottom = rectangle["bottom"]

    up_thr = top * (1 + buf)
    down_thr = bottom * (1 - buf)

    for i in range(end_pos + 1, n):
        close = closes[i]; open_ = opens[i]; prev_c = closes[i-1]
        body_pct = abs(close - open_) / max(close, 1e-9) * 100
        if body_pct < CONFIG["MIN_BREAKOUT_BODY_PCT"]:
            continue

        if prev_c <= up_thr and close > up_thr and close > open_:
            return {"direction": "BUY", "breakout_idx": i, "entry": close, "body_pct": body_pct}
        if prev_c >= down_thr and close < down_thr and close < open_:
            return {"direction": "SELL", "breakout_idx": i, "entry": close, "body_pct": body_pct}
    return None


# ══════════════════════════════════════════════════════════════════════════════
# 🎯 build pattern from rectangle + breakout
# ══════════════════════════════════════════════════════════════════════════════
def build_pattern(df, rectangle, breakout):
    entry = breakout["entry"]
    direction = breakout["direction"]
    top = rectangle["top"]
    bottom = rectangle["bottom"]
    sl_buf = CONFIG["SL_BUFFER_PCT"] / 100.0

    if direction == "BUY":
        sl = bottom * (1 - sl_buf)
        if sl >= entry: return None
        risk = entry - sl
    else:
        sl = top * (1 + sl_buf)
        if sl <= entry: return None
        risk = sl - entry
    if risk <= 0: return None

    # TP = impulse size
    impulse_dist = abs(rectangle["impulse_pct"]) / 100.0 * entry
    if impulse_dist < 0.5 * risk:
        impulse_dist = 2.0 * risk
    tp = entry + impulse_dist if direction == "BUY" else entry - impulse_dist

    rr = abs(tp - entry) / risk
    if rr < CONFIG["MIN_RR_ACCEPTED"]: return None

    # ── nodes (positions) ───────────────────────────────────────────
    top_nodes = [(int(p["pos"]), float(p["val"])) for p in rectangle["peaks"]]
    bot_nodes = [(int(p["pos"]), float(p["val"])) for p in rectangle["valleys"]]

    # lines
    start_p = rectangle["start_pos"]
    end_p = rectangle["end_pos"]
    top_line = [(start_p, top), (end_p, top)]
    bot_line = [(start_p, bottom), (end_p, bottom)]

    # entry node
    entry_pos = breakout["breakout_idx"]
    nodes = [(entry_pos, entry)]

    # arrow
    arrow_len = max(8, (end_p - start_p) // 3)
    x1_pos = min(entry_pos + arrow_len, len(df) - 1)
    arrow = {"x0": entry_pos, "y0": entry, "x1": x1_pos, "y1": tp, "direction": direction}

    box_data = {"x_start": start_p, "x_end": end_p, "high": top, "low": bottom}

    bias = "Bullish" if direction == "BUY" else "Bearish"

    pattern = {
        "name": "Pivot Rectangle Reversal",
        "pattern": f"Pivot Rect {direction} · P{rectangle['n_peaks']}/V{rectangle['n_valleys']} · W{rectangle['width_bars']}bars",
        "bias": bias,
        "direction": direction,
        "entry": round(entry, 5),
        "entry_trigger": round(entry, 5),
        "sl": round(sl, 5),
        "tp": round(tp, 5),
        "SL": round(sl, 5),
        "TP": round(tp, 5),
        "Entry": round(entry, 5),
        "R:R": round(rr, 2),
        "tp_source": "impulse_size",
        "impulse_distance": round(impulse_dist, 5),
        "nodes": nodes,
        "top_nodes": top_nodes,
        "bot_nodes": bot_nodes,
        "top_line": top_line,
        "bot_line": bot_line,
        "arrow": arrow,
        "consolidation_box": box_data,
        "resistance": round(top, 5),
        "support": round(bottom, 5),
        "level_price": round(top if direction == "BUY" else bottom, 5),
        "channel_start": start_p,
        "channel_end": end_p,
        "channel_duration_bars": rectangle["width_bars"],
        "channel_range_pct": round(rectangle["range_pct"], 3),
        "neckline_start_idx": start_p,
        "neckline_end_idx": entry_pos,
        "end_pos": entry_pos,
        "Entry Conditions": f"P{rectangle['n_peaks']} peaks / V{rectangle['n_valleys']} valleys · spread {rectangle['peak_spread_pct']:.2f}/{rectangle['valley_spread_pct']:.2f}%",
        "consol_high": round(top, 5),
        "consol_low": round(bottom, 5),
        "consol_bars": rectangle["width_bars"],
        "consol_range_pct": round(rectangle["range_pct"], 3),
        "consol_stability_pct": 100.0,
        "breakout_body_pct": round(breakout["body_pct"], 3),
        "top_touches": rectangle["n_peaks"],
        "bot_touches": rectangle["n_valleys"],
        "impulse_pct": round(rectangle["impulse_pct"], 3),
        "peak_spread_pct": round(rectangle["peak_spread_pct"], 3),
        "valley_spread_pct": round(rectangle["valley_spread_pct"], 3),
        "aspect_ratio": round(rectangle["aspect_ratio"], 2),
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

    highs_arr = post["High"].values.astype(float); lows_arr = post["Low"].values.astype(float)
    closes_arr = post["Close"].values.astype(float); dates_arr = post.index.values
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
    elif stats["Result"] in ["LOSS", "BREAKEVEN"]: stats["progress_ratio"] = 0.0
    return stats


# ══════════════════════════════════════════════════════════════════════════════
# 🎯 المحرك الرئيسي
# ══════════════════════════════════════════════════════════════════════════════
def detect_all_patterns(df, interval="1h", symbol=None, **kwargs):
    if df is None or df.empty or len(df) < CONFIG["MIN_BARS_REQUIRED"]: return []

    df = df.copy()
    for c in ["Open", "High", "Low", "Close"]:
        if c not in df.columns: return []
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["Open", "High", "Low", "Close"]).reset_index(drop=True)

    # ═══ الخطوة 1: ZigZag ═══
    df = calculate_zigzag(df, CONFIG["ZIGZAG_DEPTH"], CONFIG["ZIGZAG_BACKSTEP"])

    # ═══ الخطوة 2: البيفوتات ═══
    pivots = get_chronological_pivots(df)
    if len(pivots) < CONFIG["MIN_PEAKS"] + CONFIG["MIN_VALLEYS"]:
        return []

    # ═══ الخطوة 3: المستطيلات ═══
    rectangles = find_rectangles_from_pivots(pivots, interval)
    if not rectangles:
        return []

    # ═══ الخطوة 4: الكسر + بناء النمط ═══
    patterns = []
    last_pos = -10**9
    for rect in rectangles:
        if rect["end_pos"] - last_pos < CONFIG["MIN_BARS_BETWEEN"]:
            continue
        breakout = detect_breakout(df, rect)
        if breakout is None: continue
        if breakout["breakout_idx"] - last_pos < CONFIG["MIN_BARS_BETWEEN"]:
            continue
        p = build_pattern(df, rect, breakout)
        if p:
            patterns.append(p)
            last_pos = breakout["breakout_idx"]

    patterns.sort(key=lambda p: p["end_pos"])
    return patterns


def run_full_analysis(df, interval="1h", symbol=None):
    default_empty = {
        "df": df, "symbol": symbol or "N/A",
        "signal": "WAITING", "pattern": "NO PATTERN DETECTED",
        "bias": "Neutral", "entry": None, "sl": None, "tp": None,
        "nodes": [], "pattern_nodes": [], "all_patterns": [], "error": None,
    }
    if df is None or df.empty: return default_empty
    df = df.copy()
    for c in ["Open", "High", "Low", "Close"]:
        if c not in df.columns:
            default_empty["error"] = f"Missing column: {c}"; return default_empty
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["Open", "High", "Low", "Close"])
    if len(df) < CONFIG["MIN_BARS_REQUIRED"]:
        default_empty["error"] = f"Insufficient data: {len(df)}"; return default_empty

    df_active = df.tail(1200).copy().reset_index(drop=True)
    all_patterns = detect_all_patterns(df_active, interval=interval, symbol=symbol)

    if not all_patterns:
        default_empty["df"] = df_active; return default_empty

    latest = all_patterns[-1]
    signal = "STRONG BUY" if latest["bias"] == "Bullish" else "STRONG SELL"

    return {
        "df": df_active, "symbol": symbol or "N/A",
        "signal": signal, "pattern": latest["pattern"], "bias": latest["bias"],
        "entry": latest["entry"], "entry_trigger": latest["entry_trigger"],
        "sl": latest["sl"], "tp": latest["tp"],
        "nodes": latest.get("nodes", []),
        "pattern_nodes": latest.get("nodes", []),
        "top_nodes": latest.get("top_nodes", []),
        "bot_nodes": latest.get("bot_nodes", []),
        "top_line": latest.get("top_line"), "bot_line": latest.get("bot_line"),
        "arrow": latest.get("arrow"),
        "consolidation_box": latest.get("consolidation_box"),
        "resistance": latest.get("resistance"), "support": latest.get("support"),
        "all_patterns": all_patterns, "match": 100.0,
        "Result": latest.get("Result", "OPEN"),
        "Entry Date": latest.get("Entry Date"),
        "Exit Date": latest.get("Exit Date"),
        "Max Reach %": latest.get("Max Reach %", 0),
        "error": None,
    }


def backtest_strategy(df, interval="1h", symbol=None):
    if df is None or df.empty or len(df) < CONFIG["MIN_BARS_REQUIRED"]: return []
    df = df.copy()
    for c in ["Open", "High", "Low", "Close"]:
        if c not in df.columns: return []
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["Open", "High", "Low", "Close"])
    if len(df) < CONFIG["MIN_BARS_REQUIRED"]: return []

    patterns = detect_all_patterns(df, interval=interval, symbol=symbol)

    trades = []
    for p in patterns:
        trades.append({
            "Symbol": symbol or "N/A", "symbol": symbol or "N/A",
            "Pattern": p["pattern"], "pattern": p["pattern"],
            "Bias": p["bias"], "bias": p["bias"], "Direction": p.get("direction", "BUY"),
            "Result": p.get("Result", "OPEN"), "Head Result": p.get("Head Result", "OPEN"),
            "Entry": p["entry"], "Entry Price": p["entry"],
            "SL": p["sl"], "Stop Loss": p["sl"],
            "TP": p["tp"], "Take Profit": p["tp"],
            "R:R": p.get("R:R"),
            "Entry Date": p.get("Entry Date"), "Exit Date": p.get("Exit Date"),
            "Exit Price": p.get("exit_price"),
            "time": p.get("Entry Date"), "close_time": p.get("Exit Date"),
            "Max Reach %": p.get("Max Reach %", 0.0), "SL Safety %": p.get("SL Safety %", 0.0),
            "Entry Conditions": p.get("Entry Conditions", ""),
            "nodes": p.get("nodes", []), "top_nodes": p.get("top_nodes", []),
            "bot_nodes": p.get("bot_nodes", []), "top_line": p.get("top_line"),
            "bot_line": p.get("bot_line"), "arrow": p.get("arrow"),
            "consolidation_box": p.get("consolidation_box"),
            "candles_to_exit": p.get("candles_to_exit", 0),
            "progress_ratio": p.get("progress_ratio", 0.0),
            "neckline_end_idx": p["neckline_end_idx"], "Loss Category": p.get("Loss Category"),
            "resistance": p.get("resistance"), "support": p.get("support"),
            "channel_start": p.get("channel_start"), "channel_end": p.get("channel_end"),
            "channel_duration_bars": p.get("channel_duration_bars"),
            "channel_range_pct": p.get("channel_range_pct"),
            "top_touches": p.get("top_touches"), "bot_touches": p.get("bot_touches"),
            "impulse_pct": p.get("impulse_pct"),
            "peak_spread_pct": p.get("peak_spread_pct"),
            "valley_spread_pct": p.get("valley_spread_pct"),
            "aspect_ratio": p.get("aspect_ratio"),
        })
    return trades


def detect_all_head_shoulders(*a, **kw): return []


def diagnose_filters(df, interval="1h", symbol=None):
    return {
        "error": None, "total_raw_candidates": 0, "final_count": 0,
        "stages": {}, "smart_diagnosis": {}, "recommendations": [],
        "trade_analysis": [], "rejection_samples": {},
    }


# ══════════════════════════════════════════════════════════════════════════════
# Helper functions متوافقة
# ══════════════════════════════════════════════════════════════════════════════
def calculate_indicators(df):
    df = df.copy()
    hl = df["High"] - df["Low"]
    hc = np.abs(df["High"] - df["Close"].shift())
    lc = np.abs(df["Low"] - df["Close"].shift())
    tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    df["ATR"] = tr.rolling(14).mean()
    return df


def _get_max_gap(interval): return 50
def _get_max_pattern_duration(interval): return 200


if __name__ == "__main__":
    print("ENGINE.PY — Pivot-Based Rectangle v21")
    print(f"Pivots: ZigZag depth={CONFIG['ZIGZAG_DEPTH']} backstep={CONFIG['ZIGZAG_BACKSTEP']}")
    print(f"Peaks: ≥{CONFIG['MIN_PEAKS']} · Valleys: ≥{CONFIG['MIN_VALLEYS']}")
    print(f"Tolerance: ±{CONFIG['PEAK_TOLERANCE_PCT']}% peaks · ±{CONFIG['VALLEY_TOLERANCE_PCT']}% valleys")
    print(f"Aspect ratio: ≥{CONFIG['MIN_ASPECT_RATIO']}")
