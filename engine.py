# -*- coding: utf-8 -*-
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ==============================================================================
#           [1. إعدادات التحكم والمتغيرات القياسية - CONFIGURATION]
# ==============================================================================
CONFIG = {
    # --- إعدادات مؤشر الزيجزاج والموجات ---
    "ZIGZAG_DEPTH": 12,                  # عمق البحث عن القمم والقيعان (عدد الشمعات)
    "ZIGZAG_BACKSTEP": 6,                # خطوة الرجوع للخلف للتحقق من السعر الأقصى
    "MIN_WAVE_CANDLES": 3,               # الحد الأدنى لعدد الشمعات بين نقطتي ارتكاز متتاليتين

    # --- شروط ونسب هندسة نمط الرأس والكتفين (تحديث 5% وتصاعد الحجم) ---
    "SHOULDER_DIFF_MAX_RATIO": 0.05,      # أقصى تفاوت مسموح بين الكتفين مقارنة بارتفاع الرأس (5% فقط)
    "HEAD_PROPORTION_MIN_RATIO": 0.25,    # أدنى نسبة لبروز الرأس عن أعلى كتف (25%)
    "NECKLINE_DIFF_MAX_RATIO": 0.25,      # أقصى تفاوت مسموح في مستوى خط العنق (25%)
    "LIVE_MAX_BREAKOUT_CANDLES": 10,      # أقصى عدد شمعات بعد الاختراق للنمط الحي (10 شمعات)

    # --- إعدادات حجم التداول (Volume) عند الكسر ---
    "REQUIRE_VOLUME_BREAKOUT": True,      # تفعيل اشتراط تصاعد الحجم عند شمعة الكسر
    "VOLUME_MA_PERIOD": 20,               # فترة المتوسط المتحرك لحجم التداول (Volume MA)
    "VOLUME_FACTOR": 1.05,                # نسبة تفوق حجم شمعة الكسر على متوسط الحجم (105%)

    # --- إعدادات المؤشرات الفنية (RSI & EMAs) ---
    "RSI_PERIOD": 14,                    # فترة حساب مؤشر RSI
    "RSI_MIN_BEARISH": 30.0,             # أدنى RSI مسموح عند كتف النمط الهابط
    "RSI_MAX_BEARISH": 75.0,             # أقصى RSI مسموح عند كتف النمط الهابط
    "RSI_MIN_BULLISH": 25.0,             # أدنى RSI مسموح عند كتف النمط الصاعد
    "RSI_MAX_BULLISH": 70.0,             # أقصى RSI مسموح عند كتف النمط الصاعد
    "EMA_FAST_SPAN": 50,                 # المتوسط المتحرك السريع
    "EMA_SLOW_SPAN": 200,                # المتوسط المتحرك البطيء

    # --- إعدادات تقييم الصفقة والحالة (Valid Entry & Near Target) ---
    "VALID_ENTRY_PROGRESS_MAX": 33.33,    # الحد الأقصى لنسبة التحقق لدخول صالح (%)
    "NEAR_TARGET_PROGRESS_MIN": 70.0,     # الحد الأدنى لنسبة التقدم لتصنيف الصفقة كـ "قريبة من الهدف" (%)
}


# ==============================================================================
#                 [2. دوال حساب المؤشرات الفنية والارتكازات]
# ==============================================================================

def calculate_indicators(df, config=CONFIG):
    """حساب المتوسطات، RSI، ATR وحجم التداول (Volume MA)"""
    df = df.copy()
    ema_fast = config["EMA_FAST_SPAN"]
    ema_slow = config["EMA_SLOW_SPAN"]
    rsi_period = config["RSI_PERIOD"]
    vol_ma_period = config["VOLUME_MA_PERIOD"]

    df["EMA50"] = df["Close"].ewm(span=ema_fast, adjust=False).mean()
    df["EMA200"] = df["Close"].ewm(span=ema_slow, adjust=False).mean()

    # حساب Volume MA للتحقق من تصاعد الحجم
    if "Volume" in df.columns:
        df["Volume"] = pd.to_numeric(df["Volume"], errors="coerce").fillna(0.0)
        df["Volume_MA"] = df["Volume"].rolling(vol_ma_period).mean().fillna(0.0)
    else:
        df["Volume"] = 1.0
        df["Volume_MA"] = 1.0

    delta = df["Close"].diff()
    gain = delta.where(delta > 0, 0.0).rolling(rsi_period).mean()
    loss = -delta.where(delta < 0, 0.0).rolling(rsi_period).mean()

    loss_safe = loss.replace(0, 1e-9)
    rs = gain / loss_safe

    df["RSI"] = 100.0 - (100.0 / (1.0 + rs))
    df["RSI"] = df["RSI"].fillna(50.0)

    # حساب Dynamic Swing عبر ATR
    high_low = df["High"] - df["Low"]
    high_close = np.abs(df["High"] - df["Close"].shift())
    low_close = np.abs(df["Low"] - df["Close"].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = ranges.max(axis=1)
    df["ATR"] = true_range.rolling(14).mean()

    df["Dynamic_Swing"] = (df["ATR"] / df["Close"]) * 0.5
    df["Dynamic_Swing"] = df["Dynamic_Swing"].fillna(0.001)

    return df


def calculate_zigzag(df, config=CONFIG):
    """تحديد نقاط القمم والقيعان بناءً على إعدادات العمق والرجوع"""
    df = df.copy()
    depth = config["ZIGZAG_DEPTH"]
    backstep = config["ZIGZAG_BACKSTEP"]

    df["Pivot_H"] = np.nan
    df["Pivot_L"] = np.nan

    highs = df["High"].astype(float).values
    lows = df["Low"].astype(float).values
    n = len(df)

    for i in range(depth, n - backstep):
        high_window = highs[i - depth:i + backstep + 1]
        low_window = lows[i - depth:i + backstep + 1]

        current_high = highs[i]
        current_low = lows[i]

        is_high = (
            current_high == np.max(high_window)
            and np.sum(high_window == current_high) == 1
        )

        is_low = (
            current_low == np.min(low_window)
            and np.sum(low_window == current_low) == 1
        )

        if is_high and not is_low:
            df.iloc[i, df.columns.get_loc("Pivot_H")] = current_high
        elif is_low and not is_high:
            df.iloc[i, df.columns.get_loc("Pivot_L")] = current_low

    return df


def get_chronological_pivots(df):
    """تنقية وربط نقاط الارتكاز المتراتبة زمنياً بناءً على Dynamic_Swing"""
    raw = []

    for pos, (idx, row) in enumerate(df.iterrows()):
        if not pd.isna(row["Pivot_H"]):
            raw.append({
                "idx": idx,
                "pos": pos,
                "val": float(row["Pivot_H"]),
                "type": "H",
                "dynamic_swing": float(row.get("Dynamic_Swing", 0.001))
            })
        elif not pd.isna(row["Pivot_L"]):
            raw.append({
                "idx": idx,
                "pos": pos,
                "val": float(row["Pivot_L"]),
                "type": "L",
                "dynamic_swing": float(row.get("Dynamic_Swing", 0.001))
            })

    if not raw:
        return []

    clean = []
    for p in raw:
        if not clean:
            clean.append(p)
            continue

        last = clean[-1]
        current_min_swing = p["dynamic_swing"]

        if last["type"] != p["type"]:
            movement = abs(p["val"] - last["val"]) / max(abs(last["val"]), 1e-9)
            if movement >= current_min_swing:
                clean.append(p)
            else:
                if last["type"] == "H" and p["val"] > last["val"]:
                    clean[-1] = p
                elif last["type"] == "L" and p["val"] < last["val"]:
                    clean[-1] = p
        elif p["type"] == "H" and p["val"] > last["val"]:
            clean[-1] = p
        elif p["type"] == "L" and p["val"] < last["val"]:
            clean[-1] = p

    final_clean = []
    for p in clean:
        if not final_clean:
            final_clean.append(p)
        else:
            if final_clean[-1]["type"] != p["type"]:
                final_clean.append(p)
            else:
                if p["type"] == "H" and p["val"] > final_clean[-1]["val"]:
                    final_clean[-1] = p
                elif p["type"] == "L" and p["val"] < final_clean[-1]["val"]:
                    final_clean[-1] = p

    return final_clean


# ==============================================================================
#                 [3. أنبوب الفلترة ومحاكاة ناتج التداول]
# ==============================================================================

class PatternValidatorPipeline:
    """أنبوب الفلترة القياسي مع فحص كسر خط العنق واشتراط تصاعد الحجم"""

    def __init__(self, df, config=CONFIG):
        self.df = df
        self.config = config
        self.filters = [
            self.time_filter,
            self.trend_filter,
            self.invalidation_filter,
            self.indicator_confirmation_filter,
            self.breakout_filter
        ]

    def time_filter(self, p, data):
        min_candles = self.config["MIN_WAVE_CANDLES"]
        positions = [x["pos"] for x in p]
        for j in range(len(positions) - 1):
            if (positions[j+1] - positions[j]) < min_candles:
                return False, None, None
        return True, None, None

    def trend_filter(self, p, data):
        idx_start = p[0]["idx"]
        pre_df = data.loc[:idx_start]
        if len(pre_df) > 10:
            if p[0]["type"] == "L": # النمط الهابط
                past_min = pre_df["Low"].iloc[-10:].min()
                if past_min > p[0]["val"]:
                    return False, None, None
            else: # النمط المعكوس
                past_max = pre_df["High"].iloc[-10:].max()
                if past_max < p[0]["val"]:
                    return False, None, None
        return True, None, None

    def invalidation_filter(self, p, data):
        head_val = p[3]["val"]
        idx_head = p[3]["idx"]
        post_head_df = data.loc[idx_head:]

        if not post_head_df.empty:
            if p[3]["type"] == "H":
                if post_head_df["High"].max() > head_val:
                    return False, None, None
            else:
                if post_head_df["Low"].min() < head_val:
                    return False, None, None
        return True, None, None

    def indicator_confirmation_filter(self, p, data):
        idx_shoulder2 = p[5]["idx"]
        if idx_shoulder2 not in data.index:
            return False, None, None

        rsi_val = float(data.loc[idx_shoulder2, "RSI"])
        is_bearish = (p[3]["type"] == "H")

        rsi_min = self.config["RSI_MIN_BEARISH"] if is_bearish else self.config["RSI_MIN_BULLISH"]
        rsi_max = self.config["RSI_MAX_BEARISH"] if is_bearish else self.config["RSI_MAX_BULLISH"]

        if not (rsi_min <= rsi_val <= rsi_max):
            return False, None, None

        ema50 = data.loc[idx_shoulder2, "EMA50"]
        ema200 = data.loc[idx_shoulder2, "EMA200"]
        if pd.isna(ema50) or pd.isna(ema200):
            return False, None, None

        return True, None, None

    def breakout_filter(self, p, data):
        idx_shoulder2 = p[5]["idx"]
        n1, n2 = p[2]["val"], p[4]["val"]
        neckline_avg = (n1 + n2) / 2.0
        post_shoulder_df = data.loc[idx_shoulder2:]
        is_bearish = (p[3]["type"] == "H")

        if is_bearish:
            breakout_candidates = post_shoulder_df[post_shoulder_df["Close"] < neckline_avg]
        else:
            breakout_candidates = post_shoulder_df[post_shoulder_df["Close"] > neckline_avg]

        if breakout_candidates.empty:
            return False, None, None

        # --- إضافة شرط تصاعد الحجم (Volume Surge) عند الكسر ---
        if self.config.get("REQUIRE_VOLUME_BREAKOUT", True) and "Volume" in data.columns:
            valid_breakout_idx = None
            valid_breakout_val = None

            for b_idx, b_row in breakout_candidates.iterrows():
                vol = float(b_row.get("Volume", 0.0))
                vol_ma = float(b_row.get("Volume_MA", 0.0))
                
                pos_in_data = data.index.get_loc(b_idx)
                prev_vol = float(data["Volume"].iloc[pos_in_data - 1]) if pos_in_data > 0 else 0.0

                # يكتمل الكسر إذا كان حجم التداول أعلى من متوسطه وأعلى من الشمعة السابقة
                has_volume_surge = (vol >= vol_ma * self.config.get("VOLUME_FACTOR", 1.0)) and (vol > prev_vol)
                
                if has_volume_surge:
                    valid_breakout_idx = b_idx
                    valid_breakout_val = float(b_row["Close"])
                    break

            if valid_breakout_idx is None:
                return False, None, None
            
            return True, valid_breakout_idx, valid_breakout_val
        else:
            end_idx = breakout_candidates.index[0]
            end_val = float(breakout_candidates["Close"].iloc[0])
            return True, end_idx, end_val

    def run(self, p):
        end_idx, end_val = None, None
        for f in self.filters:
            passed, e_idx, e_val = f(p, self.df)
            if not passed:
                return False, None, None
            if e_idx is not None:
                end_idx, end_val = e_idx, e_val
        return True, end_idx, end_val


def simulate_trade_outcome(pattern, df, config=CONFIG):
    """محاكاة دقيقة وحساب الشمعات والنتائج لوقف خسارة الرأس والكتف"""
    bias = pattern["bias"]
    entry = float(pattern["entry"])
    sl = float(pattern["sl"])
    shoulder_sl = float(pattern.get("shoulder_sl", sl))
    tp = float(pattern["tp"])
    end_idx = pattern["neckline_end_idx"]

    stats = {
        "trade_result": "OPEN",
        "head_result": "OPEN",
        "shoulder_result": "OPEN",
        "progress_ratio": 0.0,
        "candles_to_exit": 0,
        "candles_to_tp_move": 0,
        "exit_idx": None,
        "exit_price": None
    }

    if end_idx not in df.index:
        return stats

    post_df = df.loc[end_idx:]
    if len(post_df) <= 1:
        return stats

    latest_close = float(df["Close"].iloc[-1])
    total_tp_dist = abs(tp - entry)

    head_done = False
    shoulder_done = False
    tp_move_found = False

    for candle_count, (idx, row) in enumerate(post_df.iloc[1:].iterrows(), start=1):
        high = float(row["High"])
        low = float(row["Low"])

        if not tp_move_found and total_tp_dist > 0:
            if bias == "Bearish" and low <= (entry - 0.2 * total_tp_dist):
                stats["candles_to_tp_move"] = candle_count
                tp_move_found = True
            elif bias == "Bullish" and high >= (entry + 0.2 * total_tp_dist):
                stats["candles_to_tp_move"] = candle_count
                tp_move_found = True

        if not head_done:
            if bias == "Bearish":
                hit_sl = high >= sl
                hit_tp = low <= tp
                if hit_sl:
                    stats["head_result"] = "LOSS"
                    stats["trade_result"] = "LOSS"
                    stats["exit_idx"], stats["exit_price"] = idx, sl
                    stats["candles_to_exit"] = candle_count
                    head_done = True
                elif hit_tp:
                    stats["head_result"] = "WIN"
                    stats["trade_result"] = "WIN"
                    stats["exit_idx"], stats["exit_price"] = idx, tp
                    stats["candles_to_exit"] = candle_count
                    head_done = True
            elif bias == "Bullish":
                hit_sl = low <= sl
                hit_tp = high >= tp
                if hit_sl:
                    stats["head_result"] = "LOSS"
                    stats["trade_result"] = "LOSS"
                    stats["exit_idx"], stats["exit_price"] = idx, sl
                    stats["candles_to_exit"] = candle_count
                    head_done = True
                elif hit_tp:
                    stats["head_result"] = "WIN"
                    stats["trade_result"] = "WIN"
                    stats["exit_idx"], stats["exit_price"] = idx, tp
                    stats["candles_to_exit"] = candle_count
                    head_done = True

        if not shoulder_done:
            if bias == "Bearish":
                if high >= shoulder_sl:
                    stats["shoulder_result"] = "LOSS"
                    shoulder_done = True
                elif low <= tp:
                    stats["shoulder_result"] = "WIN"
                    shoulder_done = True
            elif bias == "Bullish":
                if low <= shoulder_sl:
                    stats["shoulder_result"] = "LOSS"
                    shoulder_done = True
                elif high >= tp:
                    stats["shoulder_result"] = "WIN"
                    shoulder_done = True

        if head_done and shoulder_done:
            break

    if not head_done:
        stats["candles_to_exit"] = max(0, len(post_df) - 1)

    if not tp_move_found:
        stats["candles_to_tp_move"] = stats["candles_to_exit"]

    if stats["head_result"] == "WIN":
        stats["progress_ratio"] = 100.0
    elif stats["head_result"] == "LOSS":
        stats["progress_ratio"] = 0.0
    else:
        if bias == "Bearish":
            moved = max(0.0, entry - latest_close) if latest_close < entry else 0.0
        else:
            moved = max(0.0, latest_close - entry) if latest_close > entry else 0.0
        stats["progress_ratio"] = round((moved / total_tp_dist) * 100, 2) if total_tp_dist > 0 else 0.0

    return stats


# ==============================================================================
#                 [4. اكتشاف الأنماط (تطبيق شرط 5% للكتفين والحجم)]
# ==============================================================================

def detect_all_head_shoulders_base(pivots, df, config=CONFIG, is_backtest=False):
    """اكتشاف نمط الرأس والكتفين الهابط بتطبيق التفاوت 5% والحجم"""
    patterns = []
    if len(pivots) < 6:
        return patterns

    validator = PatternValidatorPipeline(df, config)
    total_candles = len(df)

    for i in range(len(pivots) - 5):
        p = pivots[i:i + 6]
        if [x["type"] for x in p] != ["L", "H", "L", "H", "L", "H"]:
            continue

        l0, h1, l1, h2, l2, h3 = [x["val"] for x in p]

        if h1 <= l0 or l1 <= l0 or h2 <= h1 or h2 <= h3:
            continue

        neckline_min = min(l1, l2)
        head_height = h2 - neckline_min
        if head_height <= 0:
            continue

        # --- تطبيق نسبة تفاوت القمم والقيعان للكتفين 5% فقط ---
        if abs(h1 - h3) > (head_height * config["SHOULDER_DIFF_MAX_RATIO"]):
            continue

        max_shoulder = max(h1, h3)
        if (h2 - max_shoulder) < (head_height * config["HEAD_PROPORTION_MIN_RATIO"]):
            continue

        if abs(l1 - l2) > (head_height * config["NECKLINE_DIFF_MAX_RATIO"]):
            continue

        passed, end_idx, end_val = validator.run(p)
        if not passed:
            continue

        end_pos = df.index.get_loc(end_idx)
        if not is_backtest and (total_candles - end_pos) > config["LIVE_MAX_BREAKOUT_CANDLES"]:
            continue

        l1_idx, l2_idx = p[2]["idx"], p[4]["idx"]
        neckline_avg = (l1 + l2) / 2.0
        actual_head_length = h2 - neckline_avg

        entry = neckline_avg
        sl = h2
        shoulder_sl = max_shoulder
        tp = entry - actual_head_length

        nodes = [(x["idx"], x["val"]) for x in p]
        nodes.append((end_idx, float(end_val)))

        neckline_nodes = [(l1_idx, l1), (l2_idx, l2)]
        target_nodes = [(end_idx, float(round(entry, 5))), (end_idx, float(round(tp, 5)))]

        pattern_dict = {
            "name": "Head and Shoulders",
            "pattern": "Head and Shoulders",
            "bias": "Bearish",
            "match": 100.0,
            "nodes": nodes,
            "entry": float(round(entry, 5)),
            "entry_trigger": float(round(entry, 5)),
            "sl": float(round(sl, 5)),
            "shoulder_sl": float(round(shoulder_sl, 5)),
            "tp": float(round(tp, 5)),
            "neckline_start_idx": l1_idx,
            "neckline_end_idx": end_idx,
            "neckline_nodes": neckline_nodes,
            "target_nodes": target_nodes,
            "end_pos": p[5]["pos"],
            "SL": float(round(sl, 5)),
            "Shoulder SL": float(round(shoulder_sl, 5))
        }

        sim_res = simulate_trade_outcome(pattern_dict, df, config)
        pattern_dict.update(sim_res)
        pattern_dict["Head Result"] = sim_res["head_result"]
        pattern_dict["Shoulder Result"] = sim_res["shoulder_result"]
        pattern_dict["Candles to Exit (Cabdale)"] = sim_res["candles_to_exit"]
        pattern_dict["Candles to TP Move"] = sim_res["candles_to_tp_move"]

        prog = sim_res["progress_ratio"]
        hit_sl_live = (df.loc[end_idx:, "High"] >= sl).any()

        is_valid = (prog <= config["VALID_ENTRY_PROGRESS_MAX"]) and not hit_sl_live
        is_near = (config["NEAR_TARGET_PROGRESS_MIN"] <= prog < 100.0) and not hit_sl_live

        pattern_dict["is_valid_entry"] = is_valid
        pattern_dict["is_near_target"] = is_near
        pattern_dict["status"] = "ACTIVE_ENTRY" if is_valid else ("NEAR_TARGET" if is_near else "IN_PROGRESS")

        patterns.append(pattern_dict)

    return patterns


def detect_all_inverse_head_shoulders(pivots, df, config=CONFIG, is_backtest=False):
    """اكتشاف نمط الرأس والكتفين المعكوس بتطبيق التفاوت 5% والحجم"""
    patterns = []
    if len(pivots) < 6:
        return patterns

    validator = PatternValidatorPipeline(df, config)
    total_candles = len(df)

    for i in range(len(pivots) - 5):
        p = pivots[i:i + 6]
        if [x["type"] for x in p] != ["H", "L", "H", "L", "H", "L"]:
            continue

        h0, l1, h1, l2, h2, l3 = [x["val"] for x in p]
        if l2 >= l1 or l2 >= l3:
            continue

        neckline_max = max(h1, h2)
        head_depth = neckline_max - l2
        if head_depth <= 0:
            continue

        # --- تطبيق نسبة تفاوت القيعان للكتفين 5% فقط ---
        if abs(l1 - l3) > (head_depth * config["SHOULDER_DIFF_MAX_RATIO"]):
            continue

        min_shoulder = min(l1, l3)
        if (min_shoulder - l2) < (head_depth * config["HEAD_PROPORTION_MIN_RATIO"]):
            continue

        if abs(h1 - h2) > (head_depth * config["NECKLINE_DIFF_MAX_RATIO"]):
            continue

        passed, end_idx, end_val = validator.run(p)
        if not passed:
            continue

        end_pos = df.index.get_loc(end_idx)
        if not is_backtest and (total_candles - end_pos) > config["LIVE_MAX_BREAKOUT_CANDLES"]:
            continue

        h1_idx, h2_idx = p[2]["idx"], p[4]["idx"]
        neckline_avg = (h1 + h2) / 2.0

        entry = neckline_avg
        sl = l2
        shoulder_sl = min_shoulder
        actual_head_length = neckline_avg - l2
        tp = entry + actual_head_length

        nodes = [(x["idx"], x["val"]) for x in p]
        nodes.append((end_idx, float(end_val)))

        neckline_nodes = [(h1_idx, h1), (h2_idx, h2)]
        target_nodes = [(end_idx, float(round(entry, 5))), (end_idx, float(round(tp, 5)))]

        pattern_dict = {
            "name": "Inverse Head and Shoulders",
            "pattern": "Inverse Head and Shoulders",
            "bias": "Bullish",
            "match": 100.0,
            "nodes": nodes,
            "entry": float(round(entry, 5)),
            "entry_trigger": float(round(entry, 5)),
            "sl": float(round(sl, 5)),
            "shoulder_sl": float(round(shoulder_sl, 5)),
            "tp": float(round(tp, 5)),
            "neckline_start_idx": h1_idx,
            "neckline_end_idx": end_idx,
            "neckline_nodes": neckline_nodes,
            "target_nodes": target_nodes,
            "end_pos": p[5]["pos"],
            "SL": float(round(sl, 5)),
            "Shoulder SL": float(round(shoulder_sl, 5))
        }

        sim_res = simulate_trade_outcome(pattern_dict, df, config)
        pattern_dict.update(sim_res)
        pattern_dict["Head Result"] = sim_res["head_result"]
        pattern_dict["Shoulder Result"] = sim_res["shoulder_result"]
        pattern_dict["Candles to Exit (Cabdale)"] = sim_res["candles_to_exit"]
        pattern_dict["Candles to TP Move"] = sim_res["candles_to_tp_move"]

        prog = sim_res["progress_ratio"]
        hit_sl_live = (df.loc[end_idx:, "Low"] <= sl).any()

        is_valid = (prog <= config["VALID_ENTRY_PROGRESS_MAX"]) and not hit_sl_live
        is_near = (config["NEAR_TARGET_PROGRESS_MIN"] <= prog < 100.0) and not hit_sl_live

        pattern_dict["is_valid_entry"] = is_valid
        pattern_dict["is_near_target"] = is_near
        pattern_dict["status"] = "ACTIVE_ENTRY" if is_valid else ("NEAR_TARGET" if is_near else "IN_PROGRESS")

        patterns.append(pattern_dict)

    return patterns


def detect_all_head_shoulders(pivots, df, config=CONFIG, is_backtest=False):
    """دمج الأنماط الهابطة والصاعدة وترتيبها زمنياً"""
    normal_patterns = detect_all_head_shoulders_base(pivots, df, config, is_backtest)
    inverse_patterns = detect_all_inverse_head_shoulders(pivots, df, config, is_backtest)

    all_patterns = normal_patterns + inverse_patterns
    all_patterns.sort(key=lambda x: x.get("end_pos", -1))
    return all_patterns


# ==============================================================================
#                 [5. دالة رسم الأنماط والمؤشرات بـ Plotly]
# ==============================================================================

def render_pattern_chart(df, patterns_to_draw=None, max_candles=500):
    """رسم الشموع، المتوسطات، هيكل الأنماط، خط العنق ومؤشر RSI"""
    if df is None or df.empty:
        return None

    df_chart = df.tail(max_candles).copy() if (max_candles and len(df) > max_candles) else df.copy()

    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.04,
        subplot_titles=('الشارت الرئيسي وهيكل النمط', 'مؤشر القوة النسبية RSI'),
        row_width=[0.25, 0.75]
    )

    fig.add_trace(
        go.Candlestick(
            x=df_chart.index, open=df_chart['Open'], high=df_chart['High'],
            low=df_chart['Low'], close=df_chart['Close'], name='السعر'
        ), row=1, col=1
    )

    if "EMA50" in df_chart.columns:
        fig.add_trace(go.Scatter(x=df_chart.index, y=df_chart["EMA50"], mode='lines', name='EMA 50', line=dict(color='#FFB300', width=1.2)), row=1, col=1)
    if "EMA200" in df_chart.columns:
        fig.add_trace(go.Scatter(x=df_chart.index, y=df_chart["EMA200"], mode='lines', name='EMA 200', line=dict(color='#1E88E5', width=1.5)), row=1, col=1)

    if patterns_to_draw:
        for idx, pat in enumerate(patterns_to_draw):
            nodes = pat.get("nodes", [])
            bias = pat.get("bias", "Bearish")
            is_latest = (idx == len(patterns_to_draw) - 1)

            line_color = ("#00E676" if bias == "Bullish" else "#FF1744") if is_latest else "rgba(158, 158, 158, 0.45)"
            line_width = 3 if is_latest else 1.5

            labels = ["L0", "LS", "N1", "Head", "N2", "RS", "Breakout"] if bias == "Bearish" else ["H0", "LS", "N1", "Head", "N2", "RS", "Breakout"]

            x_coords, y_coords, text_labels = [], [], []
            for i, node in enumerate(nodes):
                if node[0] in df_chart.index:
                    x_coords.append(node[0])
                    y_coords.append(node[1])
                    if i < len(labels):
                        text_labels.append(labels[i])

            if len(x_coords) >= 2:
                fig.add_trace(
                    go.Scatter(
                        x=x_coords, y=y_coords,
                        mode='lines+markers+text' if (is_latest and text_labels) else 'lines+markers',
                        name=f"{pat['pattern']} (#{idx+1})",
                        line=dict(color=line_color, width=line_width),
                        marker=dict(size=7, color=line_color, symbol="circle"),
                        text=text_labels if is_latest else None,
                        textposition="top center" if bias == "Bearish" else "bottom center",
                        textfont=dict(size=11, color="white")
                    ), row=1, col=1
                )

            neckline_nodes = pat.get("neckline_nodes", [])
            if neckline_nodes:
                neck_x = [n[0] for n in neckline_nodes if n[0] in df_chart.index]
                neck_y = [n[1] for n in neckline_nodes if n[0] in df_chart.index]
                if len(neck_x) >= 2:
                    fig.add_trace(go.Scatter(x=neck_x, y=neck_y, mode='lines', name=f"Neckline #{idx+1}", line=dict(color='#00E5FF', width=2, dash='dash'), showlegend=is_latest), row=1, col=1)

            target_nodes = pat.get("target_nodes", [])
            if target_nodes and is_latest:
                target_x = [n[0] for n in target_nodes if n[0] in df_chart.index]
                target_y = [n[1] for n in target_nodes if n[0] in df_chart.index]
                if len(target_x) >= 2:
                    fig.add_trace(go.Scatter(x=target_x, y=target_y, mode='lines+markers', name="Target (TP)", line=dict(color='#FF007F', width=2, dash='dot'), marker=dict(size=6, color='#FF007F', symbol='diamond')), row=1, col=1)

    if "RSI" in df_chart.columns:
        fig.add_trace(go.Scatter(x=df_chart.index, y=df_chart["RSI"], mode='lines', name='RSI', line=dict(color='#AB47BC', width=1.5)), row=2, col=1)
        fig.add_hline(y=70, line_dash="dash", line_color="#FF5252", row=2, col=1)
        fig.add_hline(y=30, line_dash="dash", line_color="#69F0AE", row=2, col=1)

    fig.update_layout(xaxis_rangeslider_visible=False, template="plotly_dark", height=720, margin=dict(l=10, r=10, t=35, b=10))
    return fig


# ==============================================================================
#                 [6. منافذ التشغيل الرئيسية والباكتيست]
# ==============================================================================

def backtest_strategy(df, config=CONFIG):
    """دالة إجراء باكتيست شامل على كافة البيانات التاريخية"""
    if df is None or df.empty or len(df) < 30:
        return []

    df_calc = calculate_indicators(df, config)
    df_calc = calculate_zigzag(df_calc, config)

    pivots = get_chronological_pivots(df_calc)
    all_patterns = detect_all_head_shoulders(pivots, df_calc, config, is_backtest=True)
    return all_patterns


def run_full_analysis(df, config=CONFIG, is_backtest=False):
    """الدالة الموحدة للتحليل الحي والمباشر وتوليد الشارت"""
    default_res = {
        "df": df, "signal": "WAITING", "pattern": "NO PATTERN DETECTED",
        "bias": "Neutral", "entry": None, "entry_trigger": None, "sl": None,
        "shoulder_sl": None, "tp": None, "nodes": [], "match": 0.0,
        "neckline_start_idx": None, "neckline_nodes": [], "target_nodes": [],
        "all_patterns": [], "near_target_patterns": [], "trade_result": "N/A",
        "SL": None, "Shoulder SL": None, "Head Result": "N/A", "Shoulder Result": "N/A",
        "Candles to Exit (Cabdale)": 0, "Candles to TP Move": 0, "progress_ratio": 0.0,
        "is_near_target": False, "status": "NONE", "fig": None, "chart": None
    }

    if df is None or df.empty:
        return default_res

    df = df.copy()
    required = ["Open", "High", "Low", "Close"]

    for col in required:
        if col not in df.columns:
            raise ValueError(f"Missing required column: {col}")
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=required)
    if len(df) < 30:
        default_res["df"] = df
        return default_res

    df_active = df if is_backtest else df.tail(200).copy()
    df_active = calculate_indicators(df_active, config)
    df_active = calculate_zigzag(df_active, config)

    pivots = get_chronological_pivots(df_active)
    all_patterns = detect_all_head_shoulders(pivots, df_active, config, is_backtest=is_backtest)

    if not all_patterns:
        fig_empty = render_pattern_chart(df_active, patterns_to_draw=[], max_candles=500)
        default_res["df"] = df_active
        default_res["fig"] = fig_empty
        default_res["chart"] = fig_empty
        return default_res

    near_target_patterns = [p for p in all_patterns if p.get("is_near_target", False)]
    active_entry_patterns = [p for p in all_patterns if p.get("is_valid_entry", False)]

    if active_entry_patterns:
        latest_pattern = active_entry_patterns[-1]
        signal = "STRONG BUY" if latest_pattern["bias"] == "Bullish" else "STRONG SELL"
    else:
        latest_pattern = all_patterns[-1]
        signal = "STRONG BUY" if latest_pattern["bias"] == "Bullish" else "STRONG SELL"

    fig = render_pattern_chart(df_active, patterns_to_draw=all_patterns, max_candles=500)

    return {
        "df": df_active,
        "signal": signal,
        "pattern": latest_pattern["pattern"],
        "bias": latest_pattern["bias"],
        "entry": latest_pattern["entry"],
        "entry_trigger": latest_pattern["entry_trigger"],
        "sl": latest_pattern["sl"],
        "shoulder_sl": latest_pattern.get("shoulder_sl", latest_pattern["sl"]),
        "tp": latest_pattern["tp"],
        "nodes": latest_pattern["nodes"],
        "match": latest_pattern["match"],
        "neckline_start_idx": latest_pattern["neckline_start_idx"],
        "neckline_nodes": latest_pattern.get("neckline_nodes", []),
        "target_nodes": latest_pattern.get("target_nodes", []),
        "all_patterns": all_patterns,
        "near_target_patterns": near_target_patterns,
        "trade_result": latest_pattern.get("trade_result", "OPEN"),
        "SL": latest_pattern.get("SL"),
        "Shoulder SL": latest_pattern.get("Shoulder SL"),
        "Head Result": latest_pattern.get("Head Result", "OPEN"),
        "Shoulder Result": latest_pattern.get("Shoulder Result", "OPEN"),
        "Candles to Exit (Cabdale)": latest_pattern.get("Candles to Exit (Cabdale)", 0),
        "Candles to TP Move": latest_pattern.get("Candles to TP Move", 0),
        "progress_ratio": latest_pattern.get("progress_ratio", 0.0),
        "is_near_target": latest_pattern.get("is_near_target", False),
        "status": latest_pattern.get("status", "NONE"),
        "fig": fig,
        "chart": fig
    }


if __name__ == "__main__":
    print("ENGINE.PY updated with 5% Shoulder Equality & Volume Surge Breakout Confirmation.")
