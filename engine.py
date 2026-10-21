# -*- coding: utf-8 -*-
"""
engine.py - محرك تحليل أنماط Box Breakout
نسخة مُعدَّلة بعد إصلاح:
  1. إزالة break المبكر (باكتيست حقيقي لعدة صفقات)
  2. إصلاح Trailing SL (مراحل قابلة للوصول)
  3. تفعيل فلاتر EMA200 + Volume
  4. إزالة التحيز الإيجابي (Same-Candle Bias)
  5. فلتر R:R أدنى
  6. حماية box_start_idx من الـ Spikes
  7. Retest مرن (يسمح بالاختراق المباشر القوي)
  8. استخدام cfg في calculate_indicators
  9. تفعيل diagnose_no_signals
 10. سلامة الفهارس (استخدام iloc / end_pos)
"""
import pandas as pd
import numpy as np

CONFIG = {
    # ── الشروط الأصلية ──
    "IMPULSE_MIN_PCT": 0.025,
    "IMPULSE_MAX_LOOKBACK": 40,
    "BOX_MIN_CANDLES": 10,
    "BOX_MAX_HEIGHT_PCT": 0.05,
    "MAX_RETRACEMENT_PCT": 0.50,
    "BREAKOUT_MIN_BODY_PCT": 0.004,
    "REQUIRE_RETEST": True,
    "RETEST_MAX_CANDLES": 8,
    "RETEST_TOLERANCE": 0.003,
    "RETEST_STRONG_CLOSE_RATIO": 0.5,
    "LIVE_MAX_BREAKOUT_CANDLES": 10,
    "TP_MEASURED_MOVE_FACTOR": 1.0,

    # ── Trailing مُعدَّل ليكون قابلاً للوصول قبل TP ──
    "TRAILING_LEVELS_HEAD": [(0.40, 0.15), (0.70, 0.40), (1.00, 0.70)],

    "SAFE_SL_MARGIN": 0.05,
    "USE_SAFE_SL": True,
    "VOLUME_MA_PERIOD": 20,
    "TREND_EMA_PERIOD": 200,

    # ── إضافات جديدة ──
    "USE_TREND_FILTER":           True,
    "USE_VOLUME_FILTER":          True,
    "VOLUME_BREAKOUT_MULT":       1.5,
    "VOLUME_RETEST_MULT":         1.2,
    "MIN_RR":                     2.0,
    "MIN_IMPULSE_BOX_GAP":        3,
    "MIN_DIRECT_BODY_PCT":        0.008,
    "CONSERVATIVE_SAME_CANDLE":   True,
    "MIN_GAP_BETWEEN_TRADES":     5,
}

REASON_MAP = {
    "immediate_rejection": {"reason": "السعر رفض الصندوق فورًا."},
    "early_reversal":      {"reason": "انعكاس مبكر قبل 30%."},
    "mid_reversal":        {"reason": "انعكاس متوسط."},
    "late_reversal":       {"reason": "وصل 70%+ ثم عاد."},
    "breakeven":           {"reason": "تعادل."},
    "success":             {"reason": "وصل الهدف."},
    "trailing_win":        {"reason": "خرج بـ Trailing."},
    "open":                {"reason": "مفتوحة."},
}


def get_symbol_config(symbol=None, interval=None):
    cfg = CONFIG.copy()
    # تخصيص اختياري حسب الإطار (غير مُفعّل افتراضياً للحفاظ على السلوك)
    # if interval in ("1m", "5m"):
    #     cfg["REQUIRE_RETEST"] = False
    #     cfg["RETEST_MAX_CANDLES"] = 3
    return cfg


def calculate_indicators(df, cfg=None):
    cfg = cfg or CONFIG
    df = df.copy()
    if "Volume" in df.columns:
        v = pd.to_numeric(df["Volume"], errors="coerce").fillna(0.0)
        df["Volume"] = v
        df["Volume_MA"] = v.rolling(cfg.get("VOLUME_MA_PERIOD", 20)).mean().fillna(0.0)
    else:
        df["Volume"] = 0.0
        df["Volume_MA"] = 0.0
    df["EMA50"]  = df["Close"].ewm(span=50, adjust=False).mean()
    df["EMA200"] = df["Close"].ewm(span=cfg.get("TREND_EMA_PERIOD", 200), adjust=False).mean()
    return df


def compute_safe_sl_and_tp(bias, entry, structural_sl, wave_height, cfg=None):
    cfg = cfg or CONFIG
    structural_risk = abs(entry - structural_sl)
    if structural_risk <= 0:
        structural_risk = 1e-8
    if bias == "Bullish":
        safe_sl = structural_sl - (structural_risk * cfg["SAFE_SL_MARGIN"])
    else:
        safe_sl = structural_sl + (structural_risk * cfg["SAFE_SL_MARGIN"])
    final_sl = safe_sl if cfg["USE_SAFE_SL"] else structural_sl
    target = wave_height * cfg["TP_MEASURED_MOVE_FACTOR"]
    tp = entry + target if bias == "Bullish" else entry - target
    return final_sl, tp, safe_sl, structural_sl


def simulate_trade(pattern, df, cfg=None):
    cfg = cfg or CONFIG
    bias  = pattern["bias"]
    entry = float(pattern["entry"])
    sl    = float(pattern["sl"])
    tp    = float(pattern["tp"])

    # ── استخدام موضع رقمي بدل تسمية الفهرس ──
    end_pos = pattern.get("end_pos", None)
    if end_pos is None:
        try:
            end_pos = df.index.get_loc(pattern["neckline_end_idx"])
        except (KeyError, TypeError):
            return {"Result": "OPEN"}

    if end_pos >= len(df) - 1:
        return {"Result": "OPEN"}

    post_df = df.iloc[end_pos:]
    if len(post_df) <= 1:
        return {"Result": "OPEN"}

    stats = {
        "Result":         "OPEN",
        "Max Reach %":    0.0,
        "SL Safety %":    0.0,
        "Entry Date":     str(df.index[end_pos]),
        "Exit Date":      None,
        "candles_to_exit": 0,
        "Trailing Stage": 0,
        "Initial SL":     sl,
        "Final SL":       sl,
        "Loss Category":  None,
        "exit_price":     None,
    }

    total_tp_dist = abs(tp - entry)
    if total_tp_dist <= 0:
        return stats

    max_fav, max_adv = 0.0, 0.0
    exited = False
    conservative = cfg.get("CONSERVATIVE_SAME_CANDLE", True)

    for c, (idx, row) in enumerate(post_df.iloc[1:].iterrows(), start=1):
        h, l = float(row["High"]), float(row["Low"])

        if bias == "Bearish":
            fav = max(0.0, entry - l)
            adv = max(0.0, h - entry)
        else:
            fav = max(0.0, h - entry)
            adv = max(0.0, entry - l)

        prog = (fav / total_tp_dist) if total_tp_dist > 0 else 0.0

        if not exited:
            max_fav = max(max_fav, prog * 100)
            init_risk = abs(entry - stats["Initial SL"])
            if init_risk > 0:
                max_adv = max(max_adv, adv / init_risk * 100)

        if exited:
            continue

        # ── تحديث Trailing ──
        for st_idx, (th, ph) in enumerate(cfg["TRAILING_LEVELS_HEAD"]):
            if prog < th:
                break
            if bias == "Bearish":
                new_sl = entry - ph * total_tp_dist
                if new_sl < sl:
                    sl = new_sl
                    stats["Trailing Stage"] = st_idx + 1
            else:
                new_sl = entry + ph * total_tp_dist
                if new_sl > sl:
                    sl = new_sl
                    stats["Trailing Stage"] = st_idx + 1
        stats["Final SL"] = sl

        if bias == "Bearish":
            hit_sl = h >= sl
            hit_tp = l <= tp
        else:
            hit_sl = l <= sl
            hit_tp = h >= tp

        # ── إزالة التحيز الإيجابي ──
        if hit_sl and hit_tp and conservative:
            hit_tp = False

        if hit_sl and not hit_tp:
            is_prof = (sl < entry) if bias == "Bearish" else (sl > entry)
            if is_prof:
                stats["Result"] = "WIN"
                stats["Loss Category"] = "trailing_win"
            else:
                stats["Result"] = "LOSS"
                if max_fav < 30:   stats["Loss Category"] = "early_reversal"
                elif max_fav < 70: stats["Loss Category"] = "mid_reversal"
                else:              stats["Loss Category"] = "late_reversal"
            stats["exit_price"] = float(sl)
            stats["candles_to_exit"] = c
            stats["Exit Date"] = str(idx)
            exited = True
            continue

        elif hit_tp:
            stats["Result"] = "WIN"
            stats["Loss Category"] = "success"
            stats["exit_price"] = float(tp)
            stats["candles_to_exit"] = c
            stats["Exit Date"] = str(idx)
            exited = True
            continue

    stats["Max Reach %"] = round(max_fav, 1)
    stats["SL Safety %"] = round(100 - max_adv, 1) if max_adv <= 100 else 0.0
    return stats


def detect_box_breakouts(df, symbol=None, is_backtest=True, interval=None):
    patterns = []
    n = len(df)
    if n < 100:
        return patterns

    cfg = get_symbol_config(symbol, interval)

    highs  = df["High"].values
    lows   = df["Low"].values
    closes = df["Close"].values
    opens  = df["Open"].values

    ema200 = df["EMA200"].values    if "EMA200"    in df.columns else None
    vol    = df["Volume"].values    if "Volume"    in df.columns else None
    vol_ma = df["Volume_MA"].values if "Volume_MA" in df.columns else None

    last_entry_pos = -10_000
    min_gap = cfg.get("MIN_GAP_BETWEEN_TRADES", 5)

    for i in range(60, n):
        # ── منع التداخل بين الصفقات ──
        if i - last_entry_pos < min_gap:
            continue

        candle_body = abs(closes[i] - opens[i])
        if candle_body < (closes[i] * cfg["BREAKOUT_MIN_BODY_PCT"]):
            continue

        is_bull_breakout = closes[i] > opens[i]
        is_bear_breakout = closes[i] < opens[i]
        if not (is_bull_breakout or is_bear_breakout):
            continue

        # ── تحقق الاندفاع ──
        lookback_start = max(0, i - cfg["IMPULSE_MAX_LOOKBACK"])
        if is_bull_breakout:
            impulse_start_idx   = lookback_start + int(np.argmin(lows[lookback_start:i]))
            impulse_start_price = lows[impulse_start_idx]
            impulse_move        = closes[i] - impulse_start_price
            if impulse_start_price <= 0: continue
            if (impulse_move / impulse_start_price) < cfg["IMPULSE_MIN_PCT"]: continue
        else:
            impulse_start_idx   = lookback_start + int(np.argmax(highs[lookback_start:i]))
            impulse_start_price = highs[impulse_start_idx]
            impulse_move        = impulse_start_price - closes[i]
            if impulse_start_price <= 0: continue
            if (impulse_move / impulse_start_price) < cfg["IMPULSE_MIN_PCT"]: continue

        # ── بداية الصندوق: استخدام قمة/قاع الإغلاق بدل High/Low الخام ──
        seg = closes[impulse_start_idx:i]
        if len(seg) == 0:
            continue
        if is_bull_breakout:
            box_start_idx = impulse_start_idx + int(np.argmax(seg))
        else:
            box_start_idx = impulse_start_idx + int(np.argmin(seg))

        if box_start_idx >= i: continue
        if (i - box_start_idx) < cfg["BOX_MIN_CANDLES"]: continue
        if (box_start_idx - impulse_start_idx) < cfg.get("MIN_IMPULSE_BOX_GAP", 3): continue

        box_highs   = highs[box_start_idx:i]
        box_lows    = lows[box_start_idx:i]
        box_top     = float(np.max(box_highs))
        box_bottom  = float(np.min(box_lows))
        box_height  = box_top - box_bottom
        box_mid     = (box_top + box_bottom) / 2
        if box_mid <= 0: continue

        if box_height == 0 or (box_height / box_mid) > cfg["BOX_MAX_HEIGHT_PCT"]: continue
        if impulse_move == 0 or (box_height / impulse_move) > cfg["MAX_RETRACEMENT_PCT"]: continue

        # ── فلتر الاتجاه العام ──
        if cfg.get("USE_TREND_FILTER", True) and ema200 is not None:
            if is_bull_breakout and closes[i] < ema200[i]: continue
            if is_bear_breakout and closes[i] > ema200[i]: continue

        # ── فلتر الحجم على شمعة الاختراق ──
        if cfg.get("USE_VOLUME_FILTER", True) and vol_ma is not None:
            if vol_ma[i] > 0 and vol[i] < cfg["VOLUME_BREAKOUT_MULT"] * vol_ma[i]:
                continue

        actual_entry_idx    = i
        actual_entry_price  = closes[i]
        structural_sl       = lows[i] if is_bull_breakout else highs[i]
        retest_confirmed    = False

        # ── إعادة الاختبار ──
        if cfg.get("REQUIRE_RETEST", False):
            for j in range(i + 1, min(n, i + 1 + cfg["RETEST_MAX_CANDLES"])):
                if is_bull_breakout:
                    if lows[j] <= box_top * (1 + cfg["RETEST_TOLERANCE"]) and closes[j] > box_top:
                        rng = highs[j] - lows[j]
                        if rng > 0 and (closes[j] - lows[j]) / rng >= cfg["RETEST_STRONG_CLOSE_RATIO"]:
                            if cfg.get("USE_VOLUME_FILTER", True) and vol_ma is not None:
                                if vol_ma[j] > 0 and vol[j] < cfg["VOLUME_RETEST_MULT"] * vol_ma[j]:
                                    continue
                            retest_confirmed    = True
                            actual_entry_idx    = j
                            actual_entry_price  = closes[j]
                            structural_sl       = lows[j]
                            break
                elif is_bear_breakout:
                    if highs[j] >= box_bottom * (1 - cfg["RETEST_TOLERANCE"]) and closes[j] < box_bottom:
                        rng = highs[j] - lows[j]
                        if rng > 0 and (highs[j] - closes[j]) / rng >= cfg["RETEST_STRONG_CLOSE_RATIO"]:
                            if cfg.get("USE_VOLUME_FILTER", True) and vol_ma is not None:
                                if vol_ma[j] > 0 and vol[j] < cfg["VOLUME_RETEST_MULT"] * vol_ma[j]:
                                    continue
                            retest_confirmed    = True
                            actual_entry_idx    = j
                            actual_entry_price  = closes[j]
                            structural_sl       = highs[j]
                            break

            # ── مسار الاختراق المباشر (Retest مرن) ──
            if not retest_confirmed:
                if is_bull_breakout:
                    body_pct = (closes[i] - opens[i]) / opens[i] if opens[i] > 0 else 0
                else:
                    body_pct = (opens[i] - closes[i]) / opens[i] if opens[i] > 0 else 0
                if body_pct < cfg.get("MIN_DIRECT_BODY_PCT", 0.008):
                    continue
                if cfg.get("USE_VOLUME_FILTER", True) and vol_ma is not None:
                    if vol_ma[i] > 0 and vol[i] < 2.0 * vol_ma[i]:
                        continue
                actual_entry_idx   = i
                actual_entry_price = closes[i]
                structural_sl      = lows[i] if is_bull_breakout else highs[i]

        # ── تحقق نهائي من موقع الدخول ──
        if is_bull_breakout and actual_entry_price <= box_top:    continue
        if is_bear_breakout and actual_entry_price >= box_bottom: continue

        # ── SL / TP / R:R ──
        bias = "Bullish" if is_bull_breakout else "Bearish"
        final_sl, tp, safe_sl, struct_sl = compute_safe_sl_and_tp(
            bias, actual_entry_price, structural_sl, impulse_move, cfg
        )

        risk   = abs(actual_entry_price - final_sl)
        reward = abs(tp - actual_entry_price)
        rr     = (reward / risk) if risk > 0 else 0.0
        if rr < cfg.get("MIN_RR", 2.0):
            continue

        box_nodes = [
            (df.index[box_start_idx],     box_top),
            (df.index[actual_entry_idx],  box_top),
            (df.index[box_start_idx],     box_bottom),
            (df.index[actual_entry_idx],  box_bottom),
        ]
        trend_nodes = [
            (df.index[impulse_start_idx], impulse_start_price),
            (df.index[box_start_idx],     box_bottom if is_bull_breakout else box_top),
            (df.index[actual_entry_idx],  actual_entry_price),
        ]

        pattern = {
            "name":             "Macro Box Breakout",
            "pattern":          "Box Breakout",
            "pattern_type":     "Continuation",
            "bias":             bias,
            "match":            100.0,
            "nodes":            trend_nodes,
            "entry":            float(round(actual_entry_price, 5)),
            "sl":               float(round(final_sl, 5)),
            "tp":               float(round(tp, 5)),
            "structural_sl":    float(round(struct_sl, 5)),
            "safe_sl":          float(round(safe_sl, 5)),
            "box_height":       float(box_height),
            "rr":               float(round(rr, 2)),
            "neckline_nodes":   box_nodes,
            "end_pos":          int(actual_entry_idx),
            "neckline_end_idx": df.index[actual_entry_idx],
            "Entry":            float(round(actual_entry_price, 5)),
            "Pattern":          f"Box Breakout ({bias})",
        }
        pattern.update(simulate_trade(pattern, df, cfg))

        emoji = "🟢" if is_bull_breakout else "🔴"
        pattern["Trade Recommendation"] = (
            f"{emoji} Box Breakout + Retest:\n"
            f"- الدخول: {pattern['entry']}\n"
            f"- SL: {pattern['sl']}\n"
            f"- TP: {pattern['tp']}"
        )

        patterns.append(pattern)
        last_entry_pos = actual_entry_idx
        # ← لا break: نستمر لاكتشاف صفقات لاحقة

    return patterns


def run_full_analysis(df, interval="1h", symbol=None):
    df = calculate_indicators(df)
    patterns = detect_box_breakouts(df, symbol, is_backtest=False, interval=interval)

    if not patterns:
        return {"signal": "WAITING", "pattern": "NO PATTERN", "bias": "Neutral", "df": df}

    recent_patterns = []
    last_idx_pos = len(df) - 1
    for p in patterns:
        p_pos = p.get("end_pos")
        if p_pos is None:
            try:
                p_pos = df.index.get_loc(p["neckline_end_idx"])
            except (KeyError, TypeError):
                continue
        if (last_idx_pos - p_pos) <= CONFIG["LIVE_MAX_BREAKOUT_CANDLES"]:
            recent_patterns.append(p)

    if not recent_patterns:
        return {"signal": "WAITING", "pattern": "NO RECENT PATTERN", "bias": "Neutral", "df": df}

    latest = recent_patterns[-1]
    return {
        "df":                   df,
        "signal":               "STRONG BUY" if latest["bias"] == "Bullish" else "STRONG SELL",
        "pattern":              latest["pattern"],
        "bias":                 latest["bias"],
        "entry":                latest["entry"],
        "sl":                   latest["sl"],
        "tp":                   latest["tp"],
        "nodes":                latest["nodes"],
        "neckline_nodes":       latest["neckline_nodes"],
        "Trade Recommendation": latest["Trade Recommendation"],
    }


def backtest_strategy(df, interval="1h", symbol=None):
    df = calculate_indicators(df)
    patterns = detect_box_breakouts(df, symbol, is_backtest=True, interval=interval)
    trades = []
    for p in patterns:
        p["Symbol"]       = symbol
        p["Entry Price"]  = p["entry"]
        p["Stop Loss"]    = p["sl"]
        p["Take Profit"]  = p["tp"]
        trades.append(p)
    return trades


def diagnose_no_signals(df, interval="1h", symbol=None, is_backtest=True):
    if df is None or len(df) < 100:
        return {
            "reason": "بيانات غير كافية",
            "counts": {"candles": len(df) if df is not None else 0},
        }

    df = calculate_indicators(df)
    cfg = get_symbol_config(symbol, interval)
    n = len(df)

    highs  = df["High"].values
    lows   = df["Low"].values
    closes = df["Close"].values
    opens  = df["Open"].values
    ema200 = df["EMA200"].values    if "EMA200"    in df.columns else None
    vol    = df["Volume"].values    if "Volume"    in df.columns else None
    vol_ma = df["Volume_MA"].values if "Volume_MA" in df.columns else None

    counts = {
        "candles":                  n,
        "impulses":                 0,
        "boxes":                    0,
        "breakouts_passed_filters": 0,
        "filtered_by_trend":        0,
        "filtered_by_volume":       0,
        "filtered_by_box_height":   0,
        "filtered_by_retracement":  0,
        "filtered_by_retest":       0,
    }

    for i in range(60, n):
        body = abs(closes[i] - opens[i])
        if body < closes[i] * cfg["BREAKOUT_MIN_BODY_PCT"]:
            continue

        is_bull = closes[i] > opens[i]
        is_bear = closes[i] < opens[i]
        if not (is_bull or is_bear):
            continue

        lb = max(0, i - cfg["IMPULSE_MAX_LOOKBACK"])
        if is_bull:
            imp_idx   = lb + int(np.argmin(lows[lb:i]))
            imp_price = lows[imp_idx]
            imp_move  = closes[i] - imp_price
        else:
            imp_idx   = lb + int(np.argmax(highs[lb:i]))
            imp_price = highs[imp_idx]
            imp_move  = imp_price - closes[i]

        if imp_price <= 0:
            continue
        if imp_move / imp_price < cfg["IMPULSE_MIN_PCT"]:
            continue
        counts["impulses"] += 1

        seg = closes[imp_idx:i]
        if len(seg) == 0:
            continue
        box_start = imp_idx + (int(np.argmax(seg)) if is_bull else int(np.argmin(seg)))

        if box_start >= i or (i - box_start) < cfg["BOX_MIN_CANDLES"]:
            continue
        if (box_start - imp_idx) < cfg.get("MIN_IMPULSE_BOX_GAP", 3):
            continue

        box_top    = float(np.max(highs[box_start:i]))
        box_bottom = float(np.min(lows[box_start:i]))
        box_height = box_top - box_bottom
        box_mid    = (box_top + box_bottom) / 2
        if box_mid <= 0 or box_height == 0:
            continue

        if box_height / box_mid > cfg["BOX_MAX_HEIGHT_PCT"]:
            counts["filtered_by_box_height"] += 1
            continue
        if imp_move == 0 or box_height / imp_move > cfg["MAX_RETRACEMENT_PCT"]:
            counts["filtered_by_retracement"] += 1
            continue

        counts["boxes"] += 1

        if cfg.get("USE_TREND_FILTER", True) and ema200 is not None:
            if (is_bull and closes[i] < ema200[i]) or (is_bear and closes[i] > ema200[i]):
                counts["filtered_by_trend"] += 1
                continue

        if cfg.get("USE_VOLUME_FILTER", True) and vol_ma is not None:
            if vol_ma[i] > 0 and vol[i] < cfg["VOLUME_BREAKOUT_MULT"] * vol_ma[i]:
                counts["filtered_by_volume"] += 1
                continue

        if is_bull and closes[i] <= box_top:
            continue
        if is_bear and closes[i] >= box_bottom:
            continue

        counts["breakouts_passed_filters"] += 1

    return {
        "reason": "لا إشارات مطابقة",
        "counts": counts,
        "recommendation": (
            "إذا كان filtered_by_volume مرتفعاً، خفّف VOLUME_BREAKOUT_MULT. "
            "إذا كان filtered_by_trend مرتفعاً، عطّل USE_TREND_FILTER. "
            "إذا كان filtered_by_retracement مرتفعاً، ارفع MAX_RETRACEMENT_PCT."
        ),
    }


def diagnose_filters(df, interval="1h", symbol=None):
    trades = backtest_strategy(df, interval, symbol)
    wins   = [t for t in trades if "WIN"  in str(t.get("Result", "")).upper()]
    losses = [t for t in trades if "LOSS" in str(t.get("Result", "")).upper()]
    total  = len(wins) + len(losses)
    wr     = round(len(wins) / total * 100, 1) if total > 0 else 0
    verdict = "لا توجد صفقات كافية" if total == 0 else f"معدل الربح: {wr}% (على {total} صفقة)"
    return {
        "smart_diagnosis": {
            "verdict":         verdict,
            "win_breakdown":   {},
            "loss_breakdown":  {},
            "action_plan":     [],
        }
    }
