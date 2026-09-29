# -*- coding: utf-8 -*-
import pandas as pd
import numpy as np

# ==============================================================================
#                 [تعديل يدوي / CONFIGURATION PARAMETERS]
#  جميع الإعدادات والنسب القابلة للتعديل والتحكم المباشر مجمعة هنا لتسهيل التعديل
# ==============================================================================
CONFIG = {
    # --- 1. إعدادات مؤشرات الزيجزاج والموجات ---
    "ZIGZAG_DEPTH": 12,           # عمق البحث عن القمم والقيعان (عدد الشمعات)
    "ZIGZAG_BACKSTEP": 5,         # خطوة الرجوع للخلف للتحقق من عدم وجود السعر الأقصى
    "MIN_WAVE_CANDLES": 3,        # الحد الأدنى لعدد الشمعات بين نقطتي ارتكاز متعاقبتين

    # --- 2. إعدادات النسب الهندسية لنماذج الرأس والكتفين (العادي والمعكوس) ---
    "SHOULDER_HEIGHT_DIFF_RATIO": 0.05, # الحد الأقصى للتفاوت المسموح بين ارتفاع/عمق الكتفين (05%)
    "SHOULDER_SYMMETRY_RATIO": 0.05,    # الحد الأقصى للتفاوت بين مستويات القمم/القيعان للكتفين
    "HEAD_MIN_PROPORTION": 0.20,        # الحد الأدنى لبروز الرأس مقارنة بالكتفين

    # --- 3. إعدادات تأكيد المؤشرات الفنية (RSI & EMAs) ---
    "RSI_PERIOD": 14,             # فترة حساب مؤشر القوة النسبية RSI (Wilder's RSI)
    "RSI_MIN": 30.0,              # الحد الأدنى المقبول لـ RSI عند كتف النمط
    "RSI_MAX": 75.0,              # الحد الأقصى المقبول لـ RSI عند كتف النمط
    "EMA_FAST_SPAN": 50,          # المتوسط المتحرك السريع EMA
    "EMA_SLOW_SPAN": 200,         # المتوسط المتحرك البطيء EMA

    # --- 4. إعدادات إدارة الصفقة وتقييم الحالة ---
    "VALID_ENTRY_PROGRESS_MAX": 0.3333, # الحد الأقصى لنسبة تحقق الهدف لاعتبار الدخول صالحاً (33.3%)
    "NEAR_TARGET_PROGRESS_MIN": 0.70,   # الحد الأدنى لنسبة التقدم لتصنيف الصفقة كـ "قريبة من الهدف"
}


# ==============================================================================
#                 [دوال حساب المؤشرات والارتكازات الفنية]
# ==============================================================================

def calculate_indicators(df, config=CONFIG):
    """حساب المتوسطات المتحركة، مؤشر RSI الأسّي القياسي، و ATR"""
    df = df.copy()
    ema_fast = config["EMA_FAST_SPAN"]
    ema_slow = config["EMA_SLOW_SPAN"]
    rsi_period = config["RSI_PERIOD"]

    df["EMA50"] = df["Close"].ewm(span=ema_fast, adjust=False).mean()
    df["EMA200"] = df["Close"].ewm(span=ema_slow, adjust=False).mean()

    # Wilder's RSI (المعادلة القياسية المعتمدة في منصات التداول)
    delta = df["Close"].diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)

    avg_gain = gain.ewm(alpha=1.0/rsi_period, min_periods=rsi_period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0/rsi_period, min_periods=rsi_period, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0, 1e-9)
    df["RSI"] = 100.0 - (100.0 / (1.0 + rs))
    df["RSI"] = df["RSI"].fillna(50.0)

    # حساب ATR للـ Swing الديناميكي
    high_low = df["High"] - df["Low"]
    high_close = np.abs(df["High"] - df["Close"].shift())
    low_close = np.abs(df["Low"] - df["Close"].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = ranges.max(axis=1)
    df["ATR"] = true_range.rolling(14).mean()

    df["Dynamic_Swing"] = (df["ATR"] / df["Close"]) * 0.5
    df["Dynamic_Swing"] = df["Dynamic_Swing"].fillna(0.001)

    if "Volume" in df.columns:
        df["Vol_SMA20"] = df["Volume"].rolling(20).mean()
    else:
        df["Vol_SMA20"] = np.nan

    return df


def calculate_zigzag(df, config=CONFIG):
    """تحديد نقاط الزيجزاج مع معالجة القمم والقيعان المزدوجة المتساوية"""
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

        max_high = np.max(high_window)
        min_low = np.min(low_window)

        # التفتيش عن القمة والقاع مع حل تكرار السعر المزدوج
        is_high = (current_high == max_high) and (np.where(high_window == max_high)[0][0] == depth)
        is_low = (current_low == min_low) and (np.where(low_window == min_low)[0][0] == depth)

        if is_high and not is_low:
            df.iloc[i, df.columns.get_loc("Pivot_H")] = float(current_high)
        elif is_low and not is_high:
            df.iloc[i, df.columns.get_loc("Pivot_L")] = float(current_low)

    return df


def get_chronological_pivots(df):
    """تنقية وربط نقاط الارتكاز المتتابعة زمنياً"""
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
            if p["type"] == "H" and p["val"] > last["val"]:
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
#                 [أنبوب الفلترة ومحاكاة الاختيار والباكتيست]
# ==============================================================================

class PatternValidatorPipeline:
    """أنبوب الفلترة القياسي الموحد للنماذج الهابطة والصاعدة"""

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

    def time_filter(self, p, pattern_type):
        min_candles = self.config["MIN_WAVE_CANDLES"]
        positions = [x["pos"] for x in p]
        for j in range(len(positions) - 1):
            if (positions[j+1] - positions[j]) < min_candles:
                return False, None, None
        return True, None, None

    def trend_filter(self, p, pattern_type):
        idx_0 = p[0]["idx"]
        pre_df = self.df.loc[:idx_0]
        if len(pre_df) > 10:
            if pattern_type == "Bearish":
                past_min = float(pre_df["Low"].iloc[-10:].min())
                if past_min > p[0]["val"]:
                    return False, None, None
            else:
                past_max = float(pre_df["High"].iloc[-10:].max())
                if past_max < p[0]["val"]:
                    return False, None, None
        return True, None, None

    def invalidation_filter(self, p, pattern_type):
        idx_head = p[3]["idx"]
        head_val = p[3]["val"]
        post_head_df = self.df.loc[idx_head:]
        if not post_head_df.empty:
            if pattern_type == "Bearish":
                if float(post_head_df["High"].max()) > head_val:
                    return False, None, None
            else:
                if float(post_head_df["Low"].min()) < head_val:
                    return False, None, None
        return True, None, None

    def indicator_confirmation_filter(self, p, pattern_type):
        idx_shoulder2 = p[5]["idx"]
        if idx_shoulder2 not in self.df.index:
            return False, None, None

        rsi_val = float(self.df.loc[idx_shoulder2, "RSI"])
        rsi_min = self.config["RSI_MIN"]
        rsi_max = self.config["RSI_MAX"]
        if not (rsi_min <= rsi_val <= rsi_max):
            return False, None, None

        ema50 = self.df.loc[idx_shoulder2, "EMA50"]
        ema200 = self.df.loc[idx_shoulder2, "EMA200"]
        if pd.isna(ema50) or pd.isna(ema200):
            return False, None, None

        return True, None, None

    def breakout_filter(self, p, pattern_type):
        idx_shoulder2 = p[5]["idx"]
        neckline_avg = (p[2]["val"] + p[4]["val"]) / 2.0
        post_shoulder_df = self.df.loc[idx_shoulder2:]

        if pattern_type == "Bearish":
            breakout_candles = post_shoulder_df[post_shoulder_df["Close"] < neckline_avg]
        else:
            breakout_candles = post_shoulder_df[post_shoulder_df["Close"] > neckline_avg]

        if breakout_candles.empty:
            return False, None, None

        end_idx = breakout_candles.index[0]
        end_val = float(breakout_candles["Close"].iloc[0])
        return True, end_idx, end_val

    def run(self, p, pattern_type):
        end_idx, end_val = None, None
        for f in self.filters:
            passed, e_idx, e_val = f(p, pattern_type)
            if not passed:
                return False, None, None
            if e_idx is not None:
                end_idx, end_val = e_idx, e_val
        return True, end_idx, end_val


def simulate_backtest_outcome(pattern, df):
    """محاكاة دقيقة لنتائج التداول بناءً على حركة السعر المستقبلي بعد الاختراق"""
    bias = pattern["bias"]
    sl = float(pattern["sl"])
    shoulder_sl = float(pattern.get("shoulder_sl", sl))
    tp = float(pattern["tp"])
    entry = float(pattern.get("entry", 0.0))
    end_idx = pattern["neckline_end_idx"]

    extra_stats = {
        "candles_to_exit": 0,
        "head_result": "OPEN",
        "shoulder_result": "OPEN",
        "candles_to_tp_move": 0
    }

    if end_idx not in df.index:
        return "OPEN", None, None, extra_stats

    post_df = df.loc[end_idx:]

    head_result = "OPEN"
    shoulder_result = "OPEN"
    exit_idx = None
    exit_price = None
    candles_to_exit = 0
    candles_to_tp_move = 0

    head_done = False
    shoulder_done = False
    tp_move_found = False

    total_tp_dist = abs(tp - entry) if entry > 0 else abs(tp - sl)

    for candle_count, (idx, row) in enumerate(post_df.iloc[1:].iterrows(), start=1):
        high = float(row["High"])
        low = float(row["Low"])

        if not tp_move_found and total_tp_dist > 0:
            if bias == "Bearish" and low <= (entry - 0.2 * total_tp_dist):
                candles_to_tp_move = candle_count
                tp_move_found = True
            elif bias == "Bullish" and high >= (entry + 0.2 * total_tp_dist):
                candles_to_tp_move = candle_count
                tp_move_found = True

        if not head_done:
            if bias == "Bearish":
                hit_sl = high >= sl
                hit_tp = low <= tp
                if hit_sl or (hit_sl and hit_tp):
                    head_result = "LOSS"
                    exit_idx, exit_price = idx, sl
                    candles_to_exit = candle_count
                    head_done = True
                elif hit_tp:
                    head_result = "WIN"
                    exit_idx, exit_price = idx, tp
                    candles_to_exit = candle_count
                    head_done = True

            elif bias == "Bullish":
                hit_sl = low <= sl
                hit_tp = high >= tp
                if hit_sl or (hit_sl and hit_tp):
                    head_result = "LOSS"
                    exit_idx, exit_price = idx, sl
                    candles_to_exit = candle_count
                    head_done = True
                elif hit_tp:
                    head_result = "WIN"
                    exit_idx, exit_price = idx, tp
                    candles_to_exit = candle_count
                    head_done = True

        if not shoulder_done:
            if bias == "Bearish":
                hit_ssl = high >= shoulder_sl
                hit_tp = low <= tp
                if hit_ssl or (hit_ssl and hit_tp):
                    shoulder_result = "LOSS"
                    shoulder_done = True
                elif hit_tp:
                    shoulder_result = "WIN"
                    shoulder_done = True

            elif bias == "Bullish":
                hit_ssl = low <= shoulder_sl
                hit_tp = high >= tp
                if hit_ssl or (hit_ssl and hit_tp):
                    shoulder_result = "LOSS"
                    shoulder_done = True
                elif hit_tp:
                    shoulder_result = "WIN"
                    shoulder_done = True

        if head_done and shoulder_done:
            break

    if not head_done:
        candles_to_exit = max(0, len(post_df) - 1)

    if not tp_move_found:
        candles_to_tp_move = candles_to_exit

    extra_stats["candles_to_exit"] = candles_to_exit
    extra_stats["head_result"] = head_result
    extra_stats["shoulder_result"] = shoulder_result
    extra_stats["candles_to_tp_move"] = candles_to_tp_move

    return head_result, exit_idx, exit_price, extra_stats


# ==============================================================================
#                 [دوال اكتشاف نماذج الرأس والكتفين]
# ==============================================================================

def detect_all_head_shoulders_base(pivots, df, config=CONFIG):
    """اكتشاف نمط الرأس والكتفين العادي (النموذج الهابط)"""
    patterns = []
    if len(pivots) < 6:
        return patterns

    validator = PatternValidatorPipeline(df, config)
    latest_close = float(df["Close"].iloc[-1])

    for i in range(len(pivots) - 5):
        p = pivots[i:i + 6]
        if [x["type"] for x in p] != ["L", "H", "L", "H", "L", "H"]:
            continue

        l0, h1, l1, h2, l2, h3 = [x["val"] for x in p]

        if h1 <= l0 or l1 <= l0 or h2 <= h1 or h2 <= h3:
            continue
        if h1 <= max(l0, l1):
            continue

        left_shoulder_height = h1 - min(l0, l1)
        right_shoulder_height = h3 - min(l1, l2)

        if left_shoulder_height <= 0 or right_shoulder_height <= 0:
            continue

        # الفحوصات الهندسية الموحدة
        height_diff_ratio = abs(right_shoulder_height - left_shoulder_height) / max(left_shoulder_height, 1e-9)
        if height_diff_ratio > config["SHOULDER_HEIGHT_DIFF_RATIO"]:
            continue

        if abs(h3 - h1) / max(left_shoulder_height, 1e-9) > config["SHOULDER_SYMMETRY_RATIO"]:
            continue

        neckline_min = min(l1, l2)
        head_height = h2 - neckline_min
        if head_height <= 0 or (h2 - max(h1, h3)) < (head_height * config["HEAD_MIN_PROPORTION"]):
            continue

        passed, end_idx, end_val = validator.run(p, "Bearish")
        if not passed:
            continue

        l1_idx, l2_idx = p[2]["idx"], p[4]["idx"]
        neckline_avg = (l1 + l2) / 2.0
        actual_head_length = h2 - neckline_avg

        entry = neckline_avg
        sl = h2
        shoulder_sl = max(h1, h3)
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
            "end_pos": df.index.get_loc(end_idx),
            "SL": float(round(sl, 5)),
            "Shoulder SL": float(round(shoulder_sl, 5))
        }

        trade_result, exit_idx, exit_price, extra_stats = simulate_backtest_outcome(pattern_dict, df)
        pattern_dict["trade_result"] = trade_result
        pattern_dict["Head Result"] = extra_stats["head_result"]
        pattern_dict["Shoulder Result"] = extra_stats["shoulder_result"]
        pattern_dict["Candles to Exit (Cabdale)"] = extra_stats["candles_to_exit"]
        pattern_dict["Candles to TP Move"] = extra_stats["candles_to_tp_move"]
        pattern_dict["exit_idx"] = exit_idx
        pattern_dict["exit_price"] = exit_price

        # تقييم التقدم التاريخي والحالي بنطاق منطقي
        total_tp_dist = abs(entry - tp)
        if trade_result == "WIN":
            progress_ratio = 1.0
        elif trade_result == "LOSS":
            progress_ratio = 0.0
        else:
            moved_dist = max(0.0, entry - latest_close) if latest_close < entry else 0.0
            progress_ratio = moved_dist / total_tp_dist if total_tp_dist > 0 else 0.0

        post_breakout_df = df.loc[end_idx:]
        hit_sl_live = (post_breakout_df["High"] >= sl).any()

        is_valid_entry = (progress_ratio <= config["VALID_ENTRY_PROGRESS_MAX"]) and not hit_sl_live
        is_near_target = (config["NEAR_TARGET_PROGRESS_MIN"] <= progress_ratio < 1.0) and not hit_sl_live

        pattern_dict["progress_ratio"] = float(round(progress_ratio * 100, 2))
        pattern_dict["is_valid_entry"] = is_valid_entry
        pattern_dict["is_near_target"] = is_near_target
        pattern_dict["status"] = "ACTIVE_ENTRY" if is_valid_entry else ("NEAR_TARGET" if is_near_target else "IN_PROGRESS")

        patterns.append(pattern_dict)

    return patterns


def detect_all_inverse_head_shoulders(pivots, df, config=CONFIG):
    """اكتشاف نمط الرأس والكتفين المعكوس (النموذج الصاعد) - بشكل متناظر تماماً"""
    patterns = []
    if len(pivots) < 6:
        return patterns

    validator = PatternValidatorPipeline(df, config)
    latest_close = float(df["Close"].iloc[-1])

    for i in range(len(pivots) - 5):
        p = pivots[i:i + 6]
        if [x["type"] for x in p] != ["H", "L", "H", "L", "H", "L"]:
            continue

        h0, l1, h1, l2, h2, l3 = [x["val"] for x in p]

        if l2 >= l1 or l2 >= l3 or l1 >= min(h0, h1):
            continue

        left_shoulder_depth = max(h0, h1) - l1
        right_shoulder_depth = max(h1, h2) - l3

        if left_shoulder_depth <= 0 or right_shoulder_depth <= 0:
            continue

        # الفحوصات الهندسية الموحدة
        depth_diff_ratio = abs(right_shoulder_depth - left_shoulder_depth) / max(left_shoulder_depth, 1e-9)
        if depth_diff_ratio > config["SHOULDER_HEIGHT_DIFF_RATIO"]:
            continue

        if abs(l3 - l1) / max(left_shoulder_depth, 1e-9) > config["SHOULDER_SYMMETRY_RATIO"]:
            continue

        neckline_max = max(h1, h2)
        head_depth = neckline_max - l2
        if head_depth <= 0 or (min(l1, l3) - l2) < (head_depth * config["HEAD_MIN_PROPORTION"]):
            continue

        passed, end_idx, end_val = validator.run(p, "Bullish")
        if not passed:
            continue

        h1_idx, h2_idx = p[2]["idx"], p[4]["idx"]
        neckline_avg = (h1 + h2) / 2.0

        entry = neckline_avg
        sl = l2
        shoulder_sl = min(l1, l3)
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
            "end_pos": df.index.get_loc(end_idx),
            "SL": float(round(sl, 5)),
            "Shoulder SL": float(round(shoulder_sl, 5))
        }

        trade_result, exit_idx, exit_price, extra_stats = simulate_backtest_outcome(pattern_dict, df)
        pattern_dict["trade_result"] = trade_result
        pattern_dict["Head Result"] = extra_stats["head_result"]
        pattern_dict["Shoulder Result"] = extra_stats["shoulder_result"]
        pattern_dict["Candles to Exit (Cabdale)"] = extra_stats["candles_to_exit"]
        pattern_dict["Candles to TP Move"] = extra_stats["candles_to_tp_move"]
        pattern_dict["exit_idx"] = exit_idx
        pattern_dict["exit_price"] = exit_price

        # تقييم التقدم التاريخي والحالي بنطاق منطقي
        total_tp_dist = abs(tp - entry)
        if trade_result == "WIN":
            progress_ratio = 1.0
        elif trade_result == "LOSS":
            progress_ratio = 0.0
        else:
            moved_dist = max(0.0, latest_close - entry) if latest_close > entry else 0.0
            progress_ratio = moved_dist / total_tp_dist if total_tp_dist > 0 else 0.0

        post_breakout_df = df.loc[end_idx:]
        hit_sl_live = (post_breakout_df["Low"] <= sl).any()

        is_valid_entry = (progress_ratio <= config["VALID_ENTRY_PROGRESS_MAX"]) and not hit_sl_live
        is_near_target = (config["NEAR_TARGET_PROGRESS_MIN"] <= progress_ratio < 1.0) and not hit_sl_live

        pattern_dict["progress_ratio"] = float(round(progress_ratio * 100, 2))
        pattern_dict["is_valid_entry"] = is_valid_entry
        pattern_dict["is_near_target"] = is_near_target
        pattern_dict["status"] = "ACTIVE_ENTRY" if is_valid_entry else ("NEAR_TARGET" if is_near_target else "IN_PROGRESS")

        patterns.append(pattern_dict)

    return patterns


def detect_all_head_shoulders(pivots, df, config=CONFIG):
    """دمج واكتشاف كافة النماذج الهابطة والصاعدة وترتيبها زمنياً"""
    normal_patterns = detect_all_head_shoulders_base(pivots, df, config)
    inverse_patterns = detect_all_inverse_head_shoulders(pivots, df, config)

    all_patterns = normal_patterns + inverse_patterns
    all_patterns.sort(key=lambda x: x.get("end_pos", -1))
    return all_patterns


# ==============================================================================
#                 [دوال الواجهة والـ Backtest الرئيسية]
# ==============================================================================

def backtest_strategy(df, interval=None, config=CONFIG, **kwargs):
    """تشغيل باكتيست شامل للفيلم السعري الممرر"""
    if df is None or df.empty or len(df) < 30:
        return []

    df = df.copy()
    required = ["Open", "High", "Low", "Close"]

    for col in required:
        if col not in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=required)

    df_active = calculate_indicators(df, config)
    df_active = calculate_zigzag(df_active, config)

    pivots = get_chronological_pivots(df_active)
    all_patterns = detect_all_head_shoulders(pivots, df_active, config)

    trades = []
    for pat in all_patterns:
        trade_result, exit_idx, exit_price, extra_stats = simulate_backtest_outcome(pat, df_active)
        trade_record = {
            "Pattern": pat["pattern"],
            "Bias": pat["bias"],
            "Entry": pat["entry"],
            "SL": pat["sl"],
            "Shoulder SL": pat.get("shoulder_sl", pat["sl"]),
            "TP": pat["tp"],
            "Head Result": extra_stats["head_result"],
            "Shoulder Result": extra_stats["shoulder_result"],
            "Candles to Exit (Cabdale)": extra_stats["candles_to_exit"],
            "Candles to TP Move": extra_stats["candles_to_tp_move"],
            "Hit Shoulder SL": extra_stats["shoulder_result"] == "LOSS",
            "Hit Head SL": extra_stats["head_result"] == "LOSS",
            "Exit Index": exit_idx,
            "Exit Price": exit_price,
            "nodes": pat.get("nodes", []),
            "trade_result": trade_result,
            "Progress Ratio (%)": pat.get("progress_ratio", 0.0),
            "Valid Entry": pat.get("is_valid_entry", False),
            "Near Target": pat.get("is_near_target", False)
        }
        trades.append(trade_record)

    return trades


def run_full_analysis(df, interval=None, config=CONFIG, **kwargs):
    """المنفذ الرئيسي المعتمد للفحص والتحليل الفوري"""
    default_response = {
        "df": df,
        "signal": "WAITING",
        "pattern": "NO PATTERN DETECTED",
        "bias": "Neutral",
        "entry": None,
        "entry_trigger": None,
        "sl": None,
        "shoulder_sl": None,
        "tp": None,
        "nodes": [],
        "match": 0.0,
        "neckline_start_idx": None,
        "neckline_nodes": [],
        "target_nodes": [],
        "all_patterns": [],
        "near_target_patterns": [],
        "trade_result": "N/A",
        "SL": None,
        "Shoulder SL": None,
        "Head Result": "N/A",
        "Shoulder Result": "N/A",
        "Candles to Exit (Cabdale)": 0,
        "Candles to TP Move": 0,
        "progress_ratio": 0.0,
        "is_near_target": False,
        "status": "NONE"
    }

    if df is None or df.empty:
        return default_response

    df = df.copy()
    required = ["Open", "High", "Low", "Close"]

    for col in required:
        if col not in df.columns:
            raise ValueError(f"Missing required column: {col}")
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=required)

    if len(df) < 30:
        default_response["df"] = df
        return default_response

    df_active = calculate_indicators(df, config)
    df_active = calculate_zigzag(df_active, config)

    pivots = get_chronological_pivots(df_active)
    all_patterns = detect_all_head_shoulders(pivots, df_active, config)

    if not all_patterns:
        default_response["df"] = df_active
        return default_response

    near_target_patterns = [p for p in all_patterns if p.get("is_near_target", False)]
    active_entry_patterns = [p for p in all_patterns if p.get("is_valid_entry", False)]

    if active_entry_patterns:
        latest_pattern = active_entry_patterns[-1]
        signal = "STRONG SELL" if latest_pattern["bias"] == "Bearish" else "STRONG BUY"
    elif all_patterns:
        latest_pattern = all_patterns[-1]
        signal = "WAITING"
    else:
        return default_response

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
        "status": latest_pattern.get("status", "NONE")
    }
