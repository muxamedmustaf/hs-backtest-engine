# -*- coding: utf-8 -*-
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ==============================================================================
# [1. إعدادات التحكم والمتغيرات القياسية - CONFIGURATION]
# ==============================================================================
CONFIG = {
    # --- إعدادات مؤشر الزيجزاج والموجات ---
    "ZIGZAG_DEPTH": 12,
    "ZIGZAG_BACKSTEP": 6,
    "MIN_WAVE_CANDLES": 3,

    # --- شروط ونسب هندسة نمط الرأس والكتفين ---
    "SHOULDER_DIFF_MAX_RATIO": 0.15,
    "HEAD_PROPORTION_MIN_RATIO": 0.25,
    "NECKLINE_DIFF_MAX_RATIO": 0.25,
    "LIVE_MAX_BREAKOUT_CANDLES": 10,

    # --- إعدادات حجم التداول (Volume) عند الكسر ---
    "REQUIRE_VOLUME_BREAKOUT": False,
    "VOLUME_MA_PERIOD": 20,
    "VOLUME_FACTOR": 1.02,

    # --- إعدادات المؤشرات الفنية (RSI & EMAs) ---
    "RSI_PERIOD": 14,
    "RSI_MIN_BEARISH": 30.0,
    "RSI_MAX_BEARISH": 75.0,
    "RSI_MIN_BULLISH": 25.0,
    "RSI_MAX_BULLISH": 70.0,
    "EMA_FAST_SPAN": 50,
    "EMA_SLOW_SPAN": 200,

    # --- إعدادات تقييم الصفقة والحالة ---
    "VALID_ENTRY_PROGRESS_MAX": 33.33,
    "NEAR_TARGET_PROGRESS_MIN": 70.0,

    # --- إعدادات إضافية للتحسين ---
    "LIVE_ANALYSIS_CANDLES": 500,   # بدلاً من 200 لتفادي قطع الأنماط
    "TREND_FILTER_LOOKBACK": 10,
}

# ==============================================================================
# [2. دوال حساب المؤشرات الفنية والارتكازات]
# ==============================================================================
def calculate_indicators(df, config=CONFIG):
    """حساب المتوسطات، RSI، ATR وحجم التداول."""
    df = df.copy()
    ema_fast = config["EMA_FAST_SPAN"]
    ema_slow = config["EMA_SLOW_SPAN"]
    rsi_period = config["RSI_PERIOD"]
    vol_ma_period = config["VOLUME_MA_PERIOD"]

    df["EMA50"] = df["Close"].ewm(span=ema_fast, adjust=False).mean()
    df["EMA200"] = df["Close"].ewm(span=ema_slow, adjust=False).mean()

    # --- Volume ---
    if "Volume" in df.columns:
        volume_numeric = pd.to_numeric(df["Volume"], errors="coerce").fillna(0.0)
        if volume_numeric.std() > 0:
            df["Volume"] = volume_numeric
            df["Volume_MA"] = df["Volume"].rolling(vol_ma_period).mean().fillna(0.0)
            df["Has_Valid_Volume"] = True
        else:
            df["Volume"] = 0.0
            df["Volume_MA"] = 0.0
            df["Has_Valid_Volume"] = False
    else:
        df["Volume"] = 0.0
        df["Volume_MA"] = 0.0
        df["Has_Valid_Volume"] = False

    # --- RSI (مع Wilder's smoothing القياسي عبر EWM) ---
    delta = df["Close"].diff()
    gain = delta.where(delta > 0, 0.0).ewm(alpha=1.0 / rsi_period, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0.0)).ewm(alpha=1.0 / rsi_period, adjust=False).mean()
    loss_safe = loss.replace(0, 1e-9)
    rs = gain / loss_safe
    df["RSI"] = 100.0 - (100.0 / (1.0 + rs))
    df["RSI"] = df["RSI"].fillna(50.0)

    # --- ATR ---
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
    """تحديد نقاط القمم والقيعان بناءً على إعدادات العمق والرجوع.

    (تحسين الأداء: تم استبدال الحلقة المزدوجة بـ rolling max/min مع الحفاظ
     على نفس المنطق تماماً للحصول على نفس النتائج).
    """
    df = df.copy()
    depth = config["ZIGZAG_DEPTH"]
    backstep = config["ZIGZAG_BACKSTEP"]

    df["Pivot_H"] = np.nan
    df["Pivot_L"] = np.nan

    highs = df["High"].astype(float).values
    lows = df["Low"].astype(float).values
    n = len(df)

    if n < (depth + backstep + 1):
        return df

    # بناء نفس النافذة [i-depth : i+backstep+1] لكن بشكل متجهي
    # نحتاج: current_high == max(window) وعدد التكرارات == 1

    for i in range(depth, n - backstep):
        high_window = highs[i - depth:i + backstep + 1]
        low_window = lows[i - depth:i + backstep + 1]
        current_high = highs[i]
        current_low = lows[i]

        is_high = (current_high == np.max(high_window)) and (np.sum(high_window == current_high) == 1)
        is_low = (current_low == np.min(low_window)) and (np.sum(low_window == current_low) == 1)

        if is_high and not is_low:
            df.iloc[i, df.columns.get_loc("Pivot_H")] = current_high
        elif is_low and not is_high:
            df.iloc[i, df.columns.get_loc("Pivot_L")] = current_low

    return df


def get_chronological_pivots(df):
    """تنقية وربط نقاط الارتكاز المتراتبة زمنياً بناءً على Dynamic_Swing."""
    raw = []
    for pos, (idx, row) in enumerate(df.iterrows()):
        if not pd.isna(row["Pivot_H"]):
            raw.append({
                "idx": idx, "pos": pos, "val": float(row["Pivot_H"]),
                "type": "H",
                "dynamic_swing": float(row.get("Dynamic_Swing", 0.001))
            })
        elif not pd.isna(row["Pivot_L"]):
            raw.append({
                "idx": idx, "pos": pos, "val": float(row["Pivot_L"]),
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
        else:
            # نفس النوع: نستبدل الأخير إن كان الجديد أكثر تطرفاً
            # (الفروع السابقة كانت مكررة وغير قابلة للوصول)
            if last["type"] == "H" and p["val"] > last["val"]:
                clean[-1] = p
            elif last["type"] == "L" and p["val"] < last["val"]:
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
# [3. أنبوب الفلترة ومحاكاة ناتج التداول]
# ==============================================================================
class PatternValidatorPipeline:
    """أنبوب الفلترة القياسي مع فحص كسر خط العنق."""

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
            if (positions[j + 1] - positions[j]) < min_candles:
                return False, None, None
        return True, None, None

    def trend_filter(self, p, data):
        """فلتر الاتجاه: يتحقق من سياق السعر قبل بداية النمط.

        - نمط هابط: يجب وجود قمة سابقة أعلى من نقطة البداية (l0).
        - نمط صاعد: يجب وجود قاع سابق أدنى من نقطة البداية (h0).
        """
        idx_start = p[0]["idx"]
        if idx_start not in data.index:
            return True, None, None

        pre_df = data.loc[:idx_start]
        lookback = self.config.get("TREND_FILTER_LOOKBACK", 10)

        if len(pre_df) > lookback:
            if p[0]["type"] == "L":
                past_max = pre_df["High"].iloc[-lookback:].max()
                if past_max <= p[0]["val"]:
                    return False, None, None
            else:
                past_min = pre_df["Low"].iloc[-lookback:].min()
                if past_min >= p[0]["val"]:
                    return False, None, None
        return True, None, None

    def invalidation_filter(self, p, data):
        head_val = p[3]["val"]
        idx_head = p[3]["idx"]
        if idx_head not in data.index:
            return False, None, None

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

        if is_bearish:
            rsi_min = self.config["RSI_MIN_BEARISH"]
            rsi_max = self.config["RSI_MAX_BEARISH"]
        else:
            rsi_min = self.config["RSI_MIN_BULLISH"]
            rsi_max = self.config["RSI_MAX_BULLISH"]

        if not (rsi_min <= rsi_val <= rsi_max):
            return False, None, None
        return True, None, None

    def breakout_filter(self, p, data):
        idx_shoulder2 = p[5]["idx"]
        n1 = p[2]["val"]
        n2 = p[4]["val"]
        neckline_avg = (n1 + n2) / 2.0
        post_shoulder_df = data.loc[idx_shoulder2:]

        is_bearish = (p[3]["type"] == "H")

        if is_bearish:
            breakout_candidates = post_shoulder_df[post_shoulder_df["Close"] < neckline_avg]
        else:
            breakout_candidates = post_shoulder_df[post_shoulder_df["Close"] > neckline_avg]

        if breakout_candidates.empty:
            return False, None, None

        req_vol = self.config.get("REQUIRE_VOLUME_BREAKOUT", False)
        has_valid_vol = False
        if "Has_Valid_Volume" in data.columns and len(data) > 0:
            has_valid_vol = bool(data["Has_Valid_Volume"].iloc[0])

        if req_vol and has_valid_vol:
            valid_breakout_idx = None
            valid_breakout_val = None
            for b_idx, b_row in breakout_candidates.iterrows():
                # معالجة صحيحة لقيم Volume و Volume_MA مع NaN
                vol_raw = b_row["Volume"] if "Volume" in b_row.index else 0.0
                vol_ma_raw = b_row["Volume_MA"] if "Volume_MA" in b_row.index else 0.0
                vol = float(vol_raw) if not pd.isna(vol_raw) else 0.0
                vol_ma = float(vol_ma_raw) if not pd.isna(vol_ma_raw) else 0.0

                pos_in_data = data.index.get_loc(b_idx)
                if pos_in_data > 0:
                    prev_vol_raw = data["Volume"].iloc[pos_in_data - 1]
                    prev_vol = float(prev_vol_raw) if not pd.isna(prev_vol_raw) else 0.0
                else:
                    prev_vol = 0.0

                if vol >= vol_ma * self.config.get("VOLUME_FACTOR", 1.0) and vol > prev_vol:
                    valid_breakout_idx = b_idx
                    valid_breakout_val = float(b_row["Close"])
                    break

            if valid_breakout_idx is None:
                return False, None, None
            return True, valid_breakout_idx, valid_breakout_val

        end_idx = breakout_candidates.index[0]
        end_val = float(breakout_candidates["Close"].iloc[0])
        return True, end_idx, end_val

    def run(self, p):
        end_idx = None
        end_val = None
        for f in self.filters:
            passed, e_idx, e_val = f(p, self.df)
            if not passed:
                return False, None, None
            if e_idx is not None:
                end_idx = e_idx
                end_val = e_val
        return True, end_idx, end_val


def _compute_match_score_bearish(h1, h2, h3, l1, l2):
    """حساب نسبة تطابق نمط H&S الهابط بناءً على الجودة الهندسية."""
    neckline_min = min(l1, l2)
    head_height = h2 - neckline_min
    if head_height <= 0:
        return 0.0

    shoulder_symmetry = 1.0 - min(abs(h1 - h3) / head_height, 1.0)
    max_shoulder = max(h1, h3)
    head_prominence = min((h2 - max_shoulder) / head_height, 1.0)
    neckline_flatness = 1.0 - min(abs(l1 - l2) / head_height, 1.0)

    score = (shoulder_symmetry * 0.4 + head_prominence * 0.3 + neckline_flatness * 0.3) * 100.0
    return round(float(score), 2)


def _compute_match_score_bullish(h1, h2, l1, l2, l3):
    """حساب نسبة تطابق نمط Inverse H&S الصاعد."""
    neckline_max = max(h1, h2)
    head_depth = neckline_max - l2
    if head_depth <= 0:
        return 0.0

    shoulder_symmetry = 1.0 - min(abs(l1 - l3) / head_depth, 1.0)
    min_shoulder = min(l1, l3)
    head_prominence = min((min_shoulder - l2) / head_depth, 1.0)
    neckline_flatness = 1.0 - min(abs(h1 - h2) / head_depth, 1.0)

    score = (shoulder_symmetry * 0.4 + head_prominence * 0.3 + neckline_flatness * 0.3) * 100.0
    return round(float(score), 2)


def simulate_trade_outcome(pattern, df, config=CONFIG):
    """محاكاة نتيجة الصفقة بعد كسر خط العنق.

    ملاحظة: في حال لمس SL و TP في نفس الشمعة تُعطى الأولوية لـ SL (تحفظي).
    """
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

        if (not tp_move_found) and total_tp_dist > 0:
            if bias == "Bearish":
                if low <= (entry - 0.2 * total_tp_dist):
                    stats["candles_to_tp_move"] = candle_count
                    tp_move_found = True
            else:
                if high >= (entry + 0.2 * total_tp_dist):
                    stats["candles_to_tp_move"] = candle_count
                    tp_move_found = True

        if not head_done:
            if bias == "Bearish":
                hit_sl = high >= sl
                hit_tp = low <= tp
                if hit_sl:
                    stats["head_result"] = "LOSS"
                    stats["trade_result"] = "LOSS"
                    stats["exit_idx"] = idx
                    stats["exit_price"] = sl
                    stats["candles_to_exit"] = candle_count
                    head_done = True
                elif hit_tp:
                    stats["head_result"] = "WIN"
                    stats["trade_result"] = "WIN"
                    stats["exit_idx"] = idx
                    stats["exit_price"] = tp
                    stats["candles_to_exit"] = candle_count
                    head_done = True
            else:
                hit_sl = low <= sl
                hit_tp = high >= tp
                if hit_sl:
                    stats["head_result"] = "LOSS"
                    stats["trade_result"] = "LOSS"
                    stats["exit_idx"] = idx
                    stats["exit_price"] = sl
                    stats["candles_to_exit"] = candle_count
                    head_done = True
                elif hit_tp:
                    stats["head_result"] = "WIN"
                    stats["trade_result"] = "WIN"
                    stats["exit_idx"] = idx
                    stats["exit_price"] = tp
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
            else:
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
        if total_tp_dist > 0:
            stats["progress_ratio"] = round((moved / total_tp_dist) * 100, 2)

    return stats


# ==============================================================================
# [4. اكتشاف الأنماط]
# ==============================================================================
def detect_all_head_shoulders_base(pivots, df, config=CONFIG, is_backtest=False):
    """اكتشاف نمط الرأس والكتفين الهابط."""
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

        if (h1 <= l0 or l1 <= l0 or h2 <= h1 or h2 <= h3):
            continue

        neckline_min = min(l1, l2)
        head_height = (h2 - neckline_min)
        if head_height <= 0:
            continue

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

        if end_idx not in df.index:
            continue

        end_pos = df.index.get_loc(end_idx)
        if (not is_backtest and (total_candles - end_pos) > config["LIVE_MAX_BREAKOUT_CANDLES"]):
            continue

        l1_idx = p[2]["idx"]
        l2_idx = p[4]["idx"]
        neckline_avg = (l1 + l2) / 2.0
        actual_head_length = (h2 - neckline_avg)
        entry = neckline_avg
        sl = h2
        shoulder_sl = max_shoulder
        tp = (entry - actual_head_length)

        nodes = [(x["idx"], x["val"]) for x in p]
        nodes.append((end_idx, float(end_val)))
        neckline_nodes = [(l1_idx, l1), (l2_idx, l2)]
        target_nodes = [
            (end_idx, float(round(entry, 5))),
            (end_idx, float(round(tp, 5)))
        ]

        match_score = _compute_match_score_bearish(h1, h2, h3, l1, l2)

        pattern_dict = {
            "name": "Head and Shoulders",
            "pattern": "Head and Shoulders",
            "bias": "Bearish",
            "match": match_score,
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
        is_valid = (prog <= config["VALID_ENTRY_PROGRESS_MAX"] and not hit_sl_live)
        is_near = (config["NEAR_TARGET_PROGRESS_MIN"] <= prog < 100.0 and not hit_sl_live)

        pattern_dict["is_valid_entry"] = is_valid
        pattern_dict["is_near_target"] = is_near
        pattern_dict["status"] = (
            "ACTIVE_ENTRY" if is_valid
            else ("NEAR_TARGET" if is_near else "IN_PROGRESS")
        )

        patterns.append(pattern_dict)

    return patterns


def detect_all_inverse_head_shoulders(pivots, df, config=CONFIG, is_backtest=False):
    """اكتشاف نمط الرأس والكتفين المعكوس."""
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

        if (l2 >= l1 or l2 >= l3):
            continue

        neckline_max = max(h1, h2)
        head_depth = (neckline_max - l2)
        if head_depth <= 0:
            continue

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

        if end_idx not in df.index:
            continue

        end_pos = df.index.get_loc(end_idx)
        if (not is_backtest and (total_candles - end_pos) > config["LIVE_MAX_BREAKOUT_CANDLES"]):
            continue

        h1_idx = p[2]["idx"]
        h2_idx = p[4]["idx"]
        neckline_avg = (h1 + h2) / 2.0
        entry = neckline_avg
        sl = l2
        shoulder_sl = min_shoulder
        actual_head_length = (neckline_avg - l2)
        tp = (entry + actual_head_length)

        nodes = [(x["idx"], x["val"]) for x in p]
        nodes.append((end_idx, float(end_val)))
        neckline_nodes = [(h1_idx, h1), (h2_idx, h2)]
        target_nodes = [
            (end_idx, float(round(entry, 5))),
            (end_idx, float(round(tp, 5)))
        ]

        match_score = _compute_match_score_bullish(h1, h2, l1, l2, l3)

        pattern_dict = {
            "name": "Inverse Head and Shoulders",
            "pattern": "Inverse Head and Shoulders",
            "bias": "Bullish",
            "match": match_score,
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
        is_valid = (prog <= config["VALID_ENTRY_PROGRESS_MAX"] and not hit_sl_live)
        is_near = (config["NEAR_TARGET_PROGRESS_MIN"] <= prog < 100.0 and not hit_sl_live)

        pattern_dict["is_valid_entry"] = is_valid
        pattern_dict["is_near_target"] = is_near
        pattern_dict["status"] = (
            "ACTIVE_ENTRY" if is_valid
            else ("NEAR_TARGET" if is_near else "IN_PROGRESS")
        )

        patterns.append(pattern_dict)

    return patterns


def detect_all_head_shoulders(pivots, df, config=CONFIG, is_backtest=False):
    """دمج الأنماط الهابطة والصاعدة وترتيبها زمنياً."""
    normal_patterns = detect_all_head_shoulders_base(pivots, df, config, is_backtest)
    inverse_patterns = detect_all_inverse_head_shoulders(pivots, df, config, is_backtest)
    all_patterns = normal_patterns + inverse_patterns
    all_patterns.sort(key=lambda x: x.get("end_pos", -1))
    return all_patterns


# ==============================================================================
# [5. دالة رسم الأنماط والمؤشرات بـ Plotly]
# ==============================================================================
def render_pattern_chart(df, patterns_to_draw=None, max_candles=500):
    """رسم الشموع والأنماط وخطوط العنق والأهداف."""
    if df is None or df.empty:
        return None

    df_chart = df.tail(max_candles).copy() if (max_candles and len(df) > max_candles) else df.copy()

    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.04,
        subplot_titles=("Main Chart & Pattern Structure", "RSI"),
        row_width=[0.25, 0.75]
    )

    # --- Price ---
    fig.add_trace(
        go.Candlestick(
            x=df_chart.index,
            open=df_chart["Open"], high=df_chart["High"],
            low=df_chart["Low"], close=df_chart["Close"],
            name="Price"
        ),
        row=1, col=1
    )

    # --- EMAs ---
    if "EMA50" in df_chart.columns:
        fig.add_trace(
            go.Scatter(
                x=df_chart.index, y=df_chart["EMA50"],
                mode="lines", name="EMA 50",
                line=dict(color="#FFB300", width=1.2)
            ),
            row=1, col=1
        )
    if "EMA200" in df_chart.columns:
        fig.add_trace(
            go.Scatter(
                x=df_chart.index, y=df_chart["EMA200"],
                mode="lines", name="EMA 200",
                line=dict(color="#1E88E5", width=1.5)
            ),
            row=1, col=1
        )

    # --- Pattern Colors ---
    pattern_colors = [
        "#FF1744", "#00E676", "#2979FF", "#FF9100", "#D500F9",
        "#00E5FF", "#FFEA00", "#76FF03", "#F50057", "#651FFF",
        "#00BFA5", "#FF6D00",
    ]

    if patterns_to_draw:
        for idx, pat in enumerate(patterns_to_draw):
            nodes = pat.get("nodes", [])
            bias = pat.get("bias", "Bearish")
            is_latest = (idx == len(patterns_to_draw) - 1)

            pattern_color = pattern_colors[idx % len(pattern_colors)]
            line_width =
