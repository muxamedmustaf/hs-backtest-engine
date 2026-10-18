# -*- coding: utf-8 -*-
"""
ENGINE.PY — H&S Detector (Multi-Symbol Custom Configuration + No Timeout)
===================================================
- كشف H&S الانعكاسي والاستمراري
- [تحديث]: إلغاء شرط الوقت (Timeout) تماماً. الصفقة تستمر حتى تصيب TP أو SL.
- [تحديث]: إضافة نظام الإعدادات المخصصة لكل زوج (SYMBOL_OVERRIDES)
- [تحديث]: إضافة فلاتر هندسية صارمة لضمان أن النماذج هي "موجات رئيسية"
- [تحديث]: إضافة فلاتر الاختراق (قوة الشمعة + الحجم)
- [تحديث]: التريلينغ الذكي (يبدأ عند 100% ويسمح بالامتداد)
"""
import pandas as pd
import numpy as np

# ══════════════════════════════════════════════════════════════════════════════
# 🌍 الإعدادات الافتراضية (تُطبق على أي زوج لم يتم إدراجه في القائمة أدناه)
# ══════════════════════════════════════════════════════════════════════════════
CONFIG = {
    "ZIGZAG_DEPTH": 7,
    "ZIGZAG_BACKSTEP": 4,
    "MIN_WAVE_CANDLES": 4,
    "NECKLINE_DIFF_MAX_RATIO": 0.25,
    "SHOULDER_DIFF_MAX_RATIO": 0.35,
    "MIN_WAVE_HEIGHT_PCT": 0.015,
    "MIN_WAVE_ATR_MULTIPLE": 2.0,
    "MIN_PATTERN_DURATION_CANDLES": 20,
    "HEAD_PROMINENCE_MIN_RATIO": 0.15,
    "LIVE_MAX_BREAKOUT_CANDLES": 15,
    "BREAKOUT_MIN_PCT": 0.0001,
    "VOLUME_MA_PERIOD": 20,
    "REQUIRE_BREAKOUT_STRENGTH": True,
    "BREAKOUT_ATR_MULTIPLIER": 1.2,
    "REQUIRE_VOLUME_BREAKOUT": True,
    "VOLUME_BREAKOUT_FACTOR": 1.2,
    "REQUIRE_TREND_FILTER": False,
    "TREND_EMA_PERIOD": 200,
    "TP_REACH_FACTOR": 2.0,
    "USE_SAFE_SL": True,
    "SAFE_SL_MARGIN": 0.15,
    "TRAILING_LEVELS_HEAD": [
        (1.00, 0.00),
        (1.50, 0.50),
        (2.00, 1.00),
    ],
    "MEASURE_FULL_EXTENSION": True,
    "ENABLE_REVERSAL": True,
    "ENABLE_CONTINUATION": True,
}

# ══════════════════════════════════════════════════════════════════════════════
# 🎯 الإعدادات المخصصة لكل زوج (Overrides)
# ══════════════════════════════════════════════════════════════════════════════
SYMBOL_OVERRIDES = {
    "BTC-USD": {
        "TP_REACH_FACTOR": 3.0,
        "MIN_WAVE_HEIGHT_PCT": 0.020,
        "MIN_WAVE_ATR_MULTIPLE": 2.5,
        "BREAKOUT_ATR_MULTIPLIER": 1.5,
        "VOLUME_BREAKOUT_FACTOR": 1.5,
        "REQUIRE_TREND_FILTER": False,
        "TRAILING_LEVELS_HEAD": [
            (1.00, 0.00),
            (1.50, 0.50),
            (2.00, 1.00),
            (3.00, 2.00),
        ],
    },
    "GBPUSD=X": {
        "TP_REACH_FACTOR": 1.5,
        "REQUIRE_TREND_FILTER": True,
        "BREAKOUT_ATR_MULTIPLIER": 1.5,
        "TRAILING_LEVELS_HEAD": [
            (0.80, 0.00),
            (1.20, 0.50),
            (1.50, 1.00),
        ],
    },
    "EURUSD=X": {
        "TP_REACH_FACTOR": 1.5,
        "REQUIRE_TREND_FILTER": True,
        "BREAKOUT_ATR_MULTIPLIER": 1.3,
    },
}

def get_symbol_config(symbol):
    base = CONFIG.copy()
    if not symbol: return base
    sym_upper = str(symbol).upper()
    for key, overrides in SYMBOL_OVERRIDES.items():
        if key.upper() in sym_upper or sym_upper in key.upper():
            base.update(overrides)
            break
    return base

REASON_MAP = {
    "immediate_rejection": {"reason": "السعر رفض خط العنق فورًا.", "action": "انتظر إعادة اختبار.", "prevention": "لا تدخل بأول لمسة."},
    "early_reversal": {"reason": "انعكاس مبكر قبل 30%.", "action": "نقل SL للتعادل.", "prevention": "Trailing مبكر."},
    "mid_reversal": {"reason": "انعكاس متوسط.", "action": "خروج جزئي 50%.", "prevention": "TP جزئي."},
    "late_reversal": {"reason": "وصل 70%+ ثم عاد.", "action": "Trailing 30%.", "prevention": "راقب الأخبار."},
    "breakeven": {"reason": "تعادل — حماية رأس المال.", "action": "لا شيء.", "prevention": "استمر."},
    "success": {"reason": "وصل الهدف.", "action": "كرر الإعداد.", "prevention": "—"},
    "trailing_win": {"reason": "خرج بـ Trailing.", "action": "لا شيء.", "prevention": "—"},
    "open": {"reason": "ما زالت مفتوحة.", "action": "راقب.", "prevention": "—"},
}

def _get_max_gap(interval):
    return {"1m": 120, "5m": 50, "15m": 30, "30m": 25, "1h": 20,
            "4h": 15, "1d": 10, "1wk": 5}.get(interval, 50)

def _get_max_pattern_duration(interval):
    return {"1m": 800, "5m": 300, "15m": 200, "30m": 180, "1h": 150,
            "4h": 120, "1d": 90, "1wk": 60}.get(interval, 250)

def compute_safe_sl_and_tp(bias, entry, structural_sl, head_size, cfg):
    structural_risk = abs(entry - structural_sl)
    if bias == "Bullish":
        safe_sl = structural_sl - (structural_risk * cfg["SAFE_SL_MARGIN"])
    else:
        safe_sl = structural_sl + (structural_risk * cfg["SAFE_SL_MARGIN"])
    final_sl = safe_sl if cfg["USE_SAFE_SL"] else structural_sl
    target = head_size * cfg["TP_REACH_FACTOR"]
    tp = entry + target if bias == "Bullish" else entry - target
    return final_sl, tp, safe_sl, structural_sl

def generate_trade_recommendation(bias, entry, sl, tp, structural_sl, head_size, pattern_name, cfg):
    risk = abs(entry - sl)
    reward = abs(tp - entry)
    rr = round(reward / risk, 2) if risk > 0 else 0.0
    factor = cfg["TP_REACH_FACTOR"]
    margin = round(cfg["SAFE_SL_MARGIN"] * 100, 0)
    if bias == "Bullish":
        return (
            f"🟢 {pattern_name}:\n"
            f"- الدخول: اختراق ({entry}).\n"
            f"- SL: ({round(sl, 5)}) = القاع ({round(structural_sl, 5)}) + {margin}%.\n"
            f"- TP: ({round(tp, 5)}) = {factor}× الرأس.\n"
            f"- R:R = 1 : {rr}."
        )
    else:
        return (
            f"🔴 {pattern_name}:\n"
            f"- الدخول: كسر ({entry}).\n"
            f"- SL: ({round(sl, 5)}) = القمة ({round(structural_sl, 5)}) + {margin}%.\n"
            f"- TP: ({round(tp, 5)}) = {factor}× الرأس.\n"
            f"- R:R = 1 : {rr}."
        )

def calculate_indicators(df, cfg):
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
        vol_period = cfg.get("VOLUME_MA_PERIOD", 20)
        df["Volume_MA"] = v.rolling(vol_period).mean().fillna(0.0)
    else:
        df["Volume"] = 0.0
        df["Volume_MA"] = 0.0
    
    ema_period = cfg.get("TREND_EMA_PERIOD", 200)
    df["EMA_Trend"] = df["Close"].ewm(span=ema_period, adjust=False).mean()
    
    return df

def calculate_zigzag(df, depth=10, backstep=4):
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
                        "type": "H", "dynamic_swing": float(row.get("Dynamic_Swing", 0.001))})
        elif not pd.isna(row["Pivot_L"]):
            raw.append({"idx": idx, "pos": pos, "val": float(row["Pivot_L"]),
                        "type": "L", "dynamic_swing": float(row.get("Dynamic_Swing", 0.001))})
    if not raw:
        return []
    clean = []
    for p in raw:
        if not clean:
            clean.append(p); continue
        last = clean[-1]
        ms = p["dynamic_swing"]
        if last["type"] != p["type"]:
            mv = abs(p["val"] - last["val"]) / max(abs(last["val"]), 1e-9)
            if mv >= ms:
                clean.append(p)
            else:
                if last["type"] == "H" and p["val"] > last["val"]: clean[-1] = p
                elif last["type"] == "L" and p["val"] < last["val"]: clean[-1] = p
        else:
            if p["type"] == "H" and p["val"] > last["val"]: clean[-1] = p
            elif p["type"] == "L" and p["val"] < last["val"]: clean[-1] = p
    final = []
    for p in clean:
        if not final:
            final.append(p)
        else:
            if final[-1]["type"] != p["type"]:
                final.append(p)
            else:
                if p["type"] == "H" and p["val"] > final[-1]["val"]: final[-1] = p
                elif p["type"] == "L" and p["val"] < final[-1]["val"]: final[-1] = p
    return final

def simulate_trade_outcome(pattern, df, cfg):
    bias = pattern["bias"]
    entry = float(pattern["entry"])
    initial_sl = float(pattern["sl"])
    sl = initial_sl
    tp = float(pattern["tp"])
    end_idx = pattern["neckline_end_idx"]

    head_size = abs(tp - entry) / cfg["TP_REACH_FACTOR"]
    head_pct = (head_size / entry * 100) if entry > 0 else 0
    MIN_HEAD_PCT = 0.10
    MAX_HEAD_PCT = 10.00

    if head_pct < MIN_HEAD_PCT:
        return {"Result": "SKIPPED", "Head Result": "SKIPPED", "Loss Category": "too_small",
                "Skip Reason": f"Head small ({head_pct:.3f}%)",
                "Max Reach %": 0, "Max Extension %": 0, "Extension Beyond TP %": 0,
                "SL Safety %": 0, "Entry Date": str(end_idx), "Exit Date": None,
                "candles_to_exit": 0, "progress_ratio": 0}
    if head_pct > MAX_HEAD_PCT:
        return {"Result": "SKIPPED", "Head Result": "SKIPPED", "Loss Category": "too_large",
                "Skip Reason": f"Head large ({head_pct:.3f}%)",
                "Max Reach %": 0, "Max Extension %": 0, "Extension Beyond TP %": 0,
                "SL Safety %": 0, "Entry Date": str(end_idx), "Exit Date": None,
                "candles_to_exit": 0, "progress_ratio": 0}

    nodes = pattern.get("nodes", [])
    if len(nodes) >= 6:
        try:
            fp = df.index.get_loc(nodes[0][0])
            hp = df.index.get_loc(nodes[-2][0])
            pattern_duration = max(1, hp - fp)
        except KeyError:
            pattern_duration = 50
    else:
        pattern_duration = 50

    TRAILING = cfg["TRAILING_LEVELS_HEAD"]

    breakeven_activated = False
    trailing_stage = 0
    stats = {
        "Result": "OPEN", "Head Result": "OPEN",
        "progress_ratio": 0.0, "candles_to_exit": 0,
        "exit_idx": None, "exit_price": None,
        "Entry Date": None, "Exit Date": None,
        "Max Reach %": 0.0, "SL Safety %": 0.0,
        "Max Extension %": 0.0, "Extension Beyond TP %": 0.0,
        "TP Hit At Candle": None, "Extension Duration Candles": 0,
        "Pattern Duration": pattern_duration, "Timeout Used": 0,
        "Breakeven Activated": False, "Breakeven Exit": False,
        "Trailing Stage": 0, "Initial SL": initial_sl, "Final SL": initial_sl,
        "Loss Category": None,
    }

    if end_idx not in df.index: return stats
    post_df = df.loc[end_idx:]
    if len(post_df) <= 1: return stats

    stats["Entry Date"] = str(end_idx)
    total_tp_dist = abs(tp - entry)
    total_sl_dist = abs(initial_sl - entry)
    max_favorable = 0.0; max_adverse = 0.0; full_window_max = 0.0
    tp_hit_candle = None; max_ext_candle = 0; exited = False

    highs = post_df["High"].values
    lows = post_df["Low"].values
    closes = post_df["Close"].values
    indices = post_df.index

    # 🚀 إلغاء الـ Timeout: الحلقة تستمر حتى نهاية البيانات أو اصطدام TP/SL
    for candle_count in range(1, len(highs)):
        high = highs[candle_count]
        low = lows[candle_count]
        close = closes[candle_count]
        idx = indices[candle_count]

        if bias == "Bearish":
            favorable = max(0.0, entry - low); adverse = max(0.0, high - entry)
        else:
            favorable = max(0.0, high - entry); adverse = max(0.0, entry - low)
        progress = (favorable / total_tp_dist) if total_tp_dist > 0 else 0.0
        progress_head = (favorable / head_size) if head_size > 0 else 0.0

        if cfg.get("MEASURE_FULL_EXTENSION", True) and total_tp_dist > 0:
            if progress * 100 > full_window_max:
                full_window_max = progress * 100; max_ext_candle = candle_count

        if not exited:
            if total_tp_dist > 0: max_favorable = max(max_favorable, progress * 100)
            if total_sl_dist > 0: max_adverse = max(max_adverse, adverse / total_sl_dist * 100)
        if exited:
            continue # استمر في حساب الامتدادات حتى النهاية ولكن لا تتداول

        for stage_idx, (th, ph) in enumerate(TRAILING):
            if stage_idx < trailing_stage: continue
            if progress_head < th: break
            if ph == 0.0:
                new_sl = entry
            else:
                new_sl = entry - ph * head_size if bias == "Bearish" else entry + ph * head_size
            if bias == "Bearish":
                if new_sl < sl:
                    sl = new_sl; trailing_stage = stage_idx + 1
                    if ph == 0.0: breakeven_activated = True; stats["Breakeven Activated"] = True
            else:
                if new_sl > sl:
                    sl = new_sl; trailing_stage = stage_idx + 1
                    if ph == 0.0: breakeven_activated = True; stats["Breakeven Activated"] = True

        stats["Trailing Stage"] = trailing_stage; stats["Final SL"] = sl

        if bias == "Bearish":
            hit_sl = high >= sl; hit_tp = low <= tp
        else:
            hit_sl = low <= sl; hit_tp = high >= tp

        if hit_sl and not hit_tp:
            if bias == "Bearish":
                is_profit = sl < entry - 1e-9; is_be = abs(sl - entry) < 1e-9
            else:
                is_profit = sl > entry + 1e-9; is_be = abs(sl - entry) < 1e-9
            if is_be:
                stats["Result"] = "BREAKEVEN"; stats["Head Result"] = "BREAKEVEN"
                stats["Breakeven Exit"] = True; stats["Loss Category"] = "breakeven"
            elif is_profit:
                stats["Result"] = "WIN"; stats["Head Result"] = "WIN"
                stats["Loss Category"] = "trailing_win"
            else:
                stats["Result"] = "LOSS"; stats["Head Result"] = "LOSS"
                r = max_favorable
                if r < 5: stats["Loss Category"] = "immediate_rejection"
                elif r < 30: stats["Loss Category"] = "early_reversal"
                elif r < 70: stats["Loss Category"] = "mid_reversal"
                else: stats["Loss Category"] = "late_reversal"
            stats["exit_idx"] = idx; stats["exit_price"] = sl
            stats["candles_to_exit"] = candle_count; stats["Exit Date"] = str(idx)
            exited = True; continue

        elif hit_tp:
            stats["Result"] = "WIN"; stats["Head Result"] = "WIN"
            stats["Loss Category"] = "success"
            stats["exit_idx"] = idx; stats["exit_price"] = tp
            stats["candles_to_exit"] = candle_count; stats["Exit Date"] = str(idx)
            tp_hit_candle = candle_count; exited = True; continue

    else:
        # 🚀 ماذا يحدث إذا انتهت البيانات والصفقة لم تصل لـ TP أو SL؟
        # تبقى مفتوحة (OPEN)
        stats["candles_to_exit"] = max(0, len(post_df) - 1)
        stats["Exit Date"] = str(df.index[-1]); stats["Loss Category"] = "open"
        if stats["Result"] == "OPEN":
            moved = max(0.0, entry - closes[-1]) if bias == "Bearish" else max(0.0, closes[-1] - entry)
            if total_tp_dist > 0:
                stats["progress_ratio"] = round(moved / total_tp_dist * 100, 2)

    stats["Max Reach %"] = round(max_favorable, 1)
    stats["SL Safety %"] = round(100 - max_adverse, 1) if max_adverse <= 100 else 0.0
    stats["Max Extension %"] = round(full_window_max, 1)
    stats["Extension Beyond TP %"] = round(max(0.0, full_window_max - 100.0), 1)
    stats["TP Hit At Candle"] = tp_hit_candle
    stats["Extension Duration Candles"] = max(0, max_ext_candle - tp_hit_candle) if tp_hit_candle else 0

    if stats["Result"] == "WIN":
        stats["progress_ratio"] = 100.0
    elif stats["Result"] in ["LOSS", "BREAKEVEN"]:
        stats["progress_ratio"] = 0.0
    return stats


class PatternValidatorPipeline:
    def __init__(self, df, cfg):
        self.df = df
        self.cfg = cfg

    def breakout_filter(self, p, is_bearish, neckline):
        idx_h3 = p[-1]["idx"]
        post = self.df.loc[idx_h3:]
        if is_bearish:
            br = post[post["Close"] < neckline]
        else:
            br = post[post["Close"] > neckline]
        if br.empty: return None
        return br.index[0], float(br["Close"].iloc[0])

    def breakout_strength_filter(self, breakout_idx):
        if not self.cfg.get("REQUIRE_BREAKOUT_STRENGTH", False): return True
        try:
            row = self.df.loc[breakout_idx]
            body = abs(float(row["Close"]) - float(row["Open"]))
            atr = float(row.get("ATR", 0))
            if atr <= 0: return True
            return body >= (atr * self.cfg.get("BREAKOUT_ATR_MULTIPLIER", 1.2))
        except Exception: return True
    
    def volume_breakout_filter(self, breakout_idx):
        if not self.cfg.get("REQUIRE_VOLUME_BREAKOUT", False): return True
        try:
            row = self.df.loc[breakout_idx]
            vol = float(row.get("Volume", 0))
            vol_ma = float(row.get("Volume_MA", 0))
            if vol_ma <= 0 or vol <= 0: return True
            return vol >= (vol_ma * self.cfg.get("VOLUME_BREAKOUT_FACTOR", 1.2))
        except Exception: return True
    
    def trend_filter(self, breakout_idx, is_bearish):
        if not self.cfg.get("REQUIRE_TREND_FILTER", False): return True
        try:
            row = self.df.loc[breakout_idx]
            price = float(row["Close"])
            ema = float(row.get("EMA_Trend", price))
            if is_bearish:
                return price < ema
            else:
                return price > ema
        except Exception: return True


def detect_head_shoulders(pivots, df, is_backtest=False, max_gap=50, max_pattern_duration=200, cfg=None):
    patterns = []
    if cfg is None: cfg = CONFIG
    if len(pivots) < 6: return patterns
    validator = PatternValidatorPipeline(df, cfg)
    total_candles = len(df)

    for i in range(len(pivots) - 5):
        p = pivots[i:i + 6]
        if [x["type"] for x in p] != ["L", "H", "L", "H", "L", "H"]: continue
        
        l0, h1, l1, h2, l2, h3 = [x["val"] for x in p]
        
        if h1 <= l0 or l1 <= l0: continue
        if h2 <= h1 or h2 <= h3: continue
        
        neckline_min = min(l1, l2)
        head_height = h2 - neckline_min
        if head_height <= 0: continue

        if (p[5]["pos"] - p[0]["pos"]) < cfg["MIN_PATTERN_DURATION_CANDLES"]: continue
        if (head_height / h2) < cfg["MIN_WAVE_HEIGHT_PCT"]: continue
        try:
            atr_at_head = float(df.loc[p[3]["idx"], "ATR"])
            if head_height < (atr_at_head * cfg["MIN_WAVE_ATR_MULTIPLE"]): continue
        except Exception: pass
        max_shoulder = max(h1, h3)
        if (h2 - max_shoulder) < (head_height * cfg["HEAD_PROMINENCE_MIN_RATIO"]): continue
        if abs(l1 - l2) > (head_height * cfg["NECKLINE_DIFF_MAX_RATIO"]): continue
        if abs(h1 - h3) > (head_height * cfg["SHOULDER_DIFF_MAX_RATIO"]): continue

        neckline = (l1 + l2) / 2.0
        br = validator.breakout_filter(p, is_bearish=True, neckline=neckline)
        if br is None: continue
        end_idx, end_val = br
        if end_idx not in df.index: continue
        end_pos = df.index.get_loc(end_idx)

        if not is_backtest and (total_candles - end_pos) > cfg["LIVE_MAX_BREAKOUT_CANDLES"]: continue
        if not validator.breakout_strength_filter(end_idx): continue
        if not validator.volume_breakout_filter(end_idx): continue
        if not validator.trend_filter(end_idx, is_bearish=True): continue

        l1_idx, l2_idx = p[2]["idx"], p[4]["idx"]
        actual_head = h2 - neckline
        entry = neckline
        structural_sl = h2
        final_sl, tp, safe_sl, _ = compute_safe_sl_and_tp("Bearish", entry, structural_sl, actual_head, cfg)

        nodes = [(x["idx"], x["val"]) for x in p] + [(end_idx, float(end_val))]
        pattern = {
            "name": "Head and Shoulders", "pattern": "Head and Shoulders", "pattern_type": "Reversal",
            "bias": "Bearish", "match": 100.0, "nodes": nodes,
            "entry": float(round(entry, 5)), "entry_trigger": float(round(entry, 5)),
            "sl": float(round(final_sl, 5)), "tp": float(round(tp, 5)),
            "structural_sl": float(round(structural_sl, 5)), "safe_sl": float(round(safe_sl, 5)),
            "neckline_start_idx": l1_idx, "neckline_end_idx": end_idx,
            "neckline_nodes": [(l1_idx, l1), (l2_idx, l2)],
            "target_nodes": [(end_idx, float(round(entry, 5))), (end_idx, float(round(tp, 5)))],
            "end_pos": p[5]["pos"], "SL": float(round(final_sl, 5)), "TP": float(round(tp, 5)),
            "Entry": float(round(entry, 5)), "Pattern": f"Head and Shoulders (Reversal)",
            "Entry Conditions": "Major Wave + Geometry + Breakout",
        }
        pattern.update(simulate_trade_outcome(pattern, df, cfg))
        pattern["Trade Recommendation"] = generate_trade_recommendation(
            "Bearish", entry, final_sl, tp, structural_sl, actual_head, f"H&S Reversal", cfg)
        patterns.append(pattern)
    return patterns


def detect_inverse_head_shoulders(pivots, df, is_backtest=False, max_gap=50, max_pattern_duration=200, cfg=None):
    patterns = []
    if cfg is None: cfg = CONFIG
    if len(pivots) < 6: return patterns
    validator = PatternValidatorPipeline(df, cfg)
    total_candles = len(df)

    for i in range(len(pivots) - 5):
        p = pivots[i:i + 6]
        if [x["type"] for x in p] != ["H", "L", "H", "L", "H", "L"]: continue
        
        h0, l1, h1, l2, h2, l3 = [x["val"] for x in p]
        
        if l2 >= l1 or l2 >= l3: continue
        
        neckline_max = max(h1, h2)
        head_depth = neckline_max - l2
        if head_depth <= 0: continue

        if (p[5]["pos"] - p[0]["pos"]) < cfg["MIN_PATTERN_DURATION_CANDLES"]: continue
        if (head_depth / l2) < cfg["MIN_WAVE_HEIGHT_PCT"]: continue
        try:
            atr_at_head = float(df.loc[p[3]["idx"], "ATR"])
            if head_depth < (atr_at_head * cfg["MIN_WAVE_ATR_MULTIPLE"]): continue
        except Exception: pass
        min_shoulder = min(l1, l3)
        if (min_shoulder - l2) < (head_depth * cfg["HEAD_PROMINENCE_MIN_RATIO"]): continue
        if abs(h1 - h2) > (head_depth * cfg["NECKLINE_DIFF_MAX_RATIO"]): continue
        if abs(l1 - l3) > (head_depth * cfg["SHOULDER_DIFF_MAX_RATIO"]): continue

        neckline = (h1 + h2) / 2.0
        br = validator.breakout_filter(p, is_bearish=False, neckline=neckline)
        if br is None: continue
        end_idx, end_val = br
        if end_idx not in df.index: continue
        end_pos = df.index.get_loc(end_idx)

        if not is_backtest and (total_candles - end_pos) > cfg["LIVE_MAX_BREAKOUT_CANDLES"]: continue
        if not validator.breakout_strength_filter(end_idx): continue
        if not validator.volume_breakout_filter(end_idx): continue
        if not validator.trend_filter(end_idx, is_bearish=False): continue

        h1_idx, h2_idx = p[2]["idx"], p[4]["idx"]
        actual_head = neckline - l2
        entry = neckline
        structural_sl = l2
        final_sl, tp, safe_sl, _ = compute_safe_sl_and_tp("Bullish", entry, structural_sl, actual_head, cfg)

        nodes = [(x["idx"], x["val"]) for x in p] + [(end_idx, end_val)]
        pattern = {
            "name": "Inverse Head and Shoulders", "pattern": "Inverse Head and Shoulders", "pattern_type": "Reversal",
            "bias": "Bullish", "match": 100.0, "nodes": nodes,
            "entry": float(round(entry, 5)), "entry_trigger": float(round(entry, 5)),
            "sl": float(round(final_sl, 5)), "tp": float(round(tp, 5)),
            "structural_sl": float(round(structural_sl, 5)), "safe_sl": float(round(safe_sl, 5)),
            "neckline_start_idx": h1_idx, "neckline_end_idx": end_idx,
            "neckline_nodes": [(h1_idx, h1), (h2_idx, h2)],
            "target_nodes": [(end_idx, float(round(entry, 5))), (end_idx, float(round(tp, 5)))],
            "end_pos": p[5]["pos"], "SL": float(round(final_sl, 5)), "TP": float(round(tp, 5)),
            "Entry": float(round(entry, 5)), "Pattern": f"Inverse Head and Shoulders (Reversal)",
            "Entry Conditions": "Major Wave + Geometry + Breakout",
        }
        pattern.update(simulate_trade_outcome(pattern, df, cfg))
        pattern["Trade Recommendation"] = generate_trade_recommendation(
            "Bullish", entry, final_sl, tp, structural_sl, actual_head, f"نموذج معكوس Reversal", cfg)
        patterns.append(pattern)
    return patterns


def detect_all_head_shoulders(pivots, df, is_backtest=False, max_gap=50, max_pattern_duration=200, cfg=None):
    a = detect_head_shoulders(pivots, df, is_backtest, max_gap, max_pattern_duration, cfg)
    b = detect_inverse_head_shoulders(pivots, df, is_backtest, max_gap, max_pattern_duration, cfg)
    all_p = a + b
    all_p.sort(key=lambda x: x.get("end_pos", -1))
    return all_p


def run_full_analysis(df, interval="1h", symbol=None):
    cfg = get_symbol_config(symbol)
    default_empty = {
        "df": df, "symbol": symbol or "N/A", "signal": "WAITING", "pattern": "NO PATTERN DETECTED",
        "bias": "Neutral", "entry": None, "sl": None, "tp": None,
        "nodes": [], "pattern_nodes": [], "all_patterns": [], "error": None,
    }
    if df is None or df.empty: return default_empty
    df = df.copy()
    required = ["Open", "High", "Low", "Close"]
    for col in required:
        if col not in df.columns:
            default_empty["error"] = f"Missing column: {col}"; return default_empty
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=required)
    if len(df) < 30:
        default_empty["error"] = f"Insufficient data: {len(df)}"; return default_empty

    df_active = df.tail(200).copy()
    df_active = calculate_indicators(df_active, cfg)
    df_active = calculate_zigzag(df_active, cfg["ZIGZAG_DEPTH"], cfg["ZIGZAG_BACKSTEP"])
    pivots = get_chronological_pivots(df_active)
    max_gap = _get_max_gap(interval)
    max_pattern_dur = _get_max_pattern_duration(interval)
    all_patterns = detect_all_head_shoulders(pivots, df_active, is_backtest=False, max_gap=max_gap, max_pattern_duration=max_pattern_dur, cfg=cfg)
    if not all_patterns:
        default_empty["df"] = df_active; return default_empty

    latest = all_patterns[-1]
    signal = "STRONG BUY" if latest["bias"] == "Bullish" else "STRONG SELL"

    return {
        "df": df_active, "symbol": symbol or "N/A", "signal": signal, "pattern": latest["pattern"], "bias": latest["bias"],
        "entry": latest["entry"], "entry_trigger": latest["entry_trigger"],
        "sl": latest["sl"], "tp": latest["tp"],
        "nodes": latest["nodes"], "pattern_nodes": latest["nodes"],
        "neckline_nodes": latest.get("neckline_nodes", []), "target_nodes": latest.get("target_nodes", []),
        "all_patterns": all_patterns, "match": latest.get("match", 100.0),
        "Result": latest.get("Result", "OPEN"), "Entry Date": latest.get("Entry Date"),
        "Exit Date": latest.get("Exit Date"), "Trade Recommendation": latest.get("Trade Recommendation", ""),
        "Max Reach %": latest.get("Max Reach %", 0), "error": None,
    }


def backtest_strategy(df, interval="1h", symbol=None):
    cfg = get_symbol_config(symbol)
    if df is None or df.empty or len(df) < 30: return []
    df = df.copy()
    for col in ["Open", "High", "Low", "Close"]:
        if col not in df.columns: return []
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["Open", "High", "Low", "Close"])
    if len(df) < 30: return []

    df = calculate_indicators(df, cfg)
    df = calculate_zigzag(df, cfg["ZIGZAG_DEPTH"], cfg["ZIGZAG_BACKSTEP"])
    pivots = get_chronological_pivots(df)
    patterns = detect_all_head_shoulders(
        pivots, df, is_backtest=True,
        max_gap=_get_max_gap(interval), max_pattern_duration=_get_max_pattern_duration(interval), cfg=cfg)

    trades = []
    for p in patterns:
        trades.append({
            "Symbol": symbol or "N/A", "symbol": symbol or "N/A",
            "Pattern": p["pattern"], "pattern": p["pattern"],
            "Pattern Type": p.get("pattern_type", "Reversal"),
            "Bias": p["bias"], "bias": p["bias"],
            "Result": p.get("Result", "OPEN"), "Head Result": p.get("Head Result", "OPEN"),
            "Entry": p["entry"], "Entry Price": p["entry"],
            "SL": p["sl"], "Stop Loss": p["sl"],
            "TP": p["tp"], "Take Profit": p["tp"],
            "Structural SL": p.get("structural_sl"), "Safe SL": p.get("safe_sl"),
            "TP Factor Used": cfg["TP_REACH_FACTOR"],
            "Entry Date": p.get("Entry Date"), "Exit Date": p.get("Exit Date"),
            "Exit Price": p.get("exit_price"), "time": p.get("Entry Date"), "close_time": p.get("Exit Date"),
            "Max Reach %": p.get("Max Reach %", 0.0), "Max Extension %": p.get("Max Extension %", 0.0),
            "Extension Beyond TP %": p.get("Extension Beyond TP %", 0.0),
            "TP Hit At Candle": p.get("TP Hit At Candle"), "Extension Duration Candles": p.get("Extension Duration Candles", 0),
            "SL Safety %": p.get("SL Safety %", 0.0), "Entry Conditions": p.get("Entry Conditions", ""),
            "nodes": p["nodes"], "candles_to_exit": p.get("candles_to_exit", 0),
            "progress_ratio": p.get("progress_ratio", 0.0), "neckline_end_idx": p["neckline_end_idx"],
            "Pattern Duration": p.get("Pattern Duration", 0), "Timeout Used": p.get("Timeout Used", 0),
            "Breakeven Activated": p.get("Breakeven Activated", False), "Breakeven Exit": p.get("Breakeven Exit", False),
            "Loss Category": p.get("Loss Category"), "Trailing Stage": p.get("Trailing Stage", 0),
            "Initial SL": p.get("Initial SL"), "Final SL": p.get("Final SL"),
            "Trade Recommendation": p.get("Trade Recommendation", ""),
        })
    return trades


def diagnose_filters(df, interval="1h", symbol=None):
    cfg = get_symbol_config(symbol)
    result = {"error": None, "total_raw_candidates": 0, "final_count": 0, "smart_diagnosis": {}, "recommendations": [], "trade_analysis": [], "by_pattern_type": {}, "tp_distribution": {}, "extension_analysis": {}}
    if df is None or df.empty or len(df) < 30: return {"error": "بيانات غير كافية"}
    
    trades = backtest_strategy(df, interval=interval, symbol=symbol)
    result["final_count"] = len(trades)
    wins = [t for t in trades if "WIN" in str(t.get("Result","")).upper()]
    losses = [t for t in trades if "LOSS" in str(t.get("Result","")).upper()]
    
    total_closed = len(wins) + len(losses)
    win_rate = round(len(wins) / total_closed * 100, 1) if total_closed else 0
    verdict = "لا توجد صفقات كافية" if total_closed == 0 else f"معدل الربح: {win_rate}%"
    
    result["smart_diagnosis"] = {"verdict": verdict, "win_breakdown": {}, "loss_breakdown": {}, "action_plan": []}
    return result


def diagnose_no_signals(df, interval="1h", symbol=None, is_backtest=True):
    cfg = get_symbol_config(symbol)
    if df is None or df.empty or len(df) < 30: return {"error": "بيانات غير كافية"}
    
    df = df.copy()
    for col in ["Open", "High", "Low", "Close"]:
        if col not in df.columns: return {"error": f"مفقود: {col}"}
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["Open", "High", "Low", "Close"])

    df = calculate_indicators(df, cfg)
    df = calculate_zigzag(df, cfg["ZIGZAG_DEPTH"], cfg["ZIGZAG_BACKSTEP"])
    pivots = get_chronological_pivots(df)

    stats = {
        "total_pivots": len(pivots), "raw_candidates": 0,
        "rejected_pattern_structure": 0, "rejected_duration": 0, "rejected_size": 0, "rejected_atr": 0,
        "rejected_head_prom": 0, "rejected_neckline_shoulder": 0,
        "rejected_no_breakout": 0, "rejected_breakout_confirm": 0, "rejected_trend": 0, "passed": 0
    }

    if len(pivots) < 6: return stats
    validator = PatternValidatorPipeline(df, cfg)
    total_candles = len(df)

    for i in range(len(pivots) - 5):
        p = pivots[i:i + 6]
        is_bearish = [x["type"] for x in p] == ["L", "H", "L", "H", "L", "H"]
        is_bullish = [x["type"] for x in p] == ["H", "L", "H", "L", "H", "L"]
        
        if not (is_bearish or is_bullish):
            stats["rejected_pattern_structure"] += 1; continue
        stats["raw_candidates"] += 1

        if is_bearish:
            l0, h1, l1, h2, l2, h3 = [x["val"] for x in p]
            if h1 <= l0 or l1 <= l0 or h2 <= h1 or h2 <= h3:
                stats["rejected_pattern_structure"] += 1; continue
            
            neckline_min = min(l1, l2)
            head_height = h2 - neckline_min
            if head_height <= 0:
                stats["rejected_pattern_structure"] += 1; continue
            
            if (p[5]["pos"] - p[0]["pos"]) < cfg["MIN_PATTERN_DURATION_CANDLES"]:
                stats["rejected_duration"] += 1; continue
            
            if (head_height / h2) < cfg["MIN_WAVE_HEIGHT_PCT"]:
                stats["rejected_size"] += 1; continue
            
            try:
                atr_at_head = float(df.loc[p[3]["idx"], "ATR"])
                if head_height < (atr_at_head * cfg["MIN_WAVE_ATR_MULTIPLE"]):
                    stats["rejected_atr"] += 1; continue
            except Exception: pass
            
            max_shoulder = max(h1, h3)
            if (h2 - max_shoulder) < (head_height * cfg["HEAD_PROMINENCE_MIN_RATIO"]):
                stats["rejected_head_prom"] += 1; continue
            
            if abs(l1 - l2) > (head_height * cfg["NECKLINE_DIFF_MAX_RATIO"]) or abs(h1 - h3) > (head_height * cfg["SHOULDER_DIFF_MAX_RATIO"]):
                stats["rejected_neckline_shoulder"] += 1; continue
            
            neckline = (l1 + l2) / 2.0
            br = validator.breakout_filter(p, is_bearish=True, neckline=neckline)
            if br is None:
                stats["rejected_no_breakout"] += 1; continue
            
            end_idx, end_val = br
            if end_idx not in df.index: continue
            end_pos = df.index.get_loc(end_idx)
            
            if not is_backtest and (total_candles - end_pos) > cfg["LIVE_MAX_BREAKOUT_CANDLES"]:
                stats["rejected_no_breakout"] += 1; continue
            if not validator.breakout_strength_filter(end_idx) or not validator.volume_breakout_filter(end_idx):
                stats["rejected_breakout_confirm"] += 1; continue
            if not validator.trend_filter(end_idx, is_bearish=True):
                stats["rejected_trend"] += 1; continue
            
            stats["passed"] += 1

        else: # Bullish
            h0, l1, h1, l2, h2, l3 = [x["val"] for x in p]
            if l2 >= l1 or l2 >= l3:
                stats["rejected_pattern_structure"] += 1; continue
            
            neckline_max = max(h1, h2)
            head_depth = neckline_max - l2
            if head_depth <= 0:
                stats["rejected_pattern_structure"] += 1; continue
            
            if (p[5]["pos"] - p[0]["pos"]) < cfg["MIN_PATTERN_DURATION_CANDLES"]:
                stats["rejected_duration"] += 1; continue
            
            if (head_depth / l2) < cfg["MIN_WAVE_HEIGHT_PCT"]:
                stats["rejected_size"] += 1; continue
            
            try:
                atr_at_head = float(df.loc[p[3]["idx"], "ATR"])
                if head_depth < (atr_at_head * cfg["MIN_WAVE_ATR_MULTIPLE"]):
                    stats["rejected_atr"] += 1; continue
            except Exception: pass
            
            min_shoulder = min(l1, l3)
            if (min_shoulder - l2) < (head_depth * cfg["HEAD_PROMINENCE_MIN_RATIO"]):
                stats["rejected_head_prom"] += 1; continue
            
            if abs(h1 - h2) > (head_depth * cfg["NECKLINE_DIFF_MAX_RATIO"]) or abs(l1 - l3) > (head_depth * cfg["SHOULDER_DIFF_MAX_RATIO"]):
                stats["rejected_neckline_shoulder"] += 1; continue
            
            neckline = (h1 + h2) / 2.0
            br = validator.breakout_filter(p, is_bearish=False, neckline=neckline)
            if br is None:
                stats["rejected_no_breakout"] += 1; continue
            
            end_idx, end_val = br
            if end_idx not in df.index: continue
            end_pos = df.index.get_loc(end_idx)
            
            if not is_backtest and (total_candles - end_pos) > cfg["LIVE_MAX_BREAKOUT_CANDLES"]:
                stats["rejected_no_breakout"] += 1; continue
            if not validator.breakout_strength_filter(end_idx) or not validator.volume_breakout_filter(end_idx):
                stats["rejected_breakout_confirm"] += 1; continue
            if not validator.trend_filter(end_idx, is_bearish=False):
                stats["rejected_trend"] += 1; continue
            
            stats["passed"] += 1
    return stats


if __name__ == "__main__":
    print("ENGINE.PY — H&S Detector (No Timeout + Multi-Symbol Configuration)")
