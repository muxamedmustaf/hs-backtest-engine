# -*- coding: utf-8 -*-
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ==========================================================
# ENGINE.PY - DYNAMIC SWING SCANNER WITH VOLUME & LABELS (v4.7)
# ==========================================================

MIN_WAVE_CANDLES = 3

CONFIG = {
    "ZIGZAG_DEPTH": 12,
    "ZIGZAG_BACKSTEP": 6,
    "MIN_WAVE_CANDLES": MIN_WAVE_CANDLES,
    "RSI_BEARISH_MIN": 30.0,
    "RSI_BEARISH_MAX": 75.0,
    "RSI_BULLISH_MIN": 25.0,
    "RSI_BULLISH_MAX": 70.0,
    "MAX_RECENCY_CANDLES": 10,
    "VALID_ENTRY_PROGRESS_MAX": 0.3333,
    "NEAR_TARGET_PROGRESS_MIN": 0.70,
    "VOLUME_BREAKOUT_FACTOR": 1.0  # حجم التداول عند الكسر يجب أن يكون أعلى من المتوسط
}


def calculate_indicators(df):
    """حساب المتوسطات، مؤشر RSI، حجم التداول، و Dynamic Swing بناءً على ATR"""
    df = df.copy()
    df["EMA50"] = df["Close"].ewm(span=50, adjust=False).mean()
    df["EMA200"] = df["Close"].ewm(span=200, adjust=False).mean()

    # RSI
    delta = df["Close"].diff()
    gain = delta.where(delta > 0, 0.0).rolling(14).mean()
    loss = -delta.where(delta < 0, 0.0).rolling(14).mean()
    loss_safe = loss.replace(0, 1e-9)
    rs = gain / loss_safe
    df["RSI"] = 100 - (100 / (1 + rs))
    df["RSI"] = df["RSI"].fillna(50.0)

    # ATR & Dynamic Swing
    high_low = df["High"] - df["Low"]
    high_close = np.abs(df["High"] - df["Close"].shift())
    low_close = np.abs(df["Low"] - df["Close"].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = ranges.max(axis=1)
    df["ATR"] = true_range.rolling(14).mean()

    df["Dynamic_Swing"] = (df["ATR"] / df["Close"]) * 0.5
    df["Dynamic_Swing"] = df["Dynamic_Swing"].fillna(0.001)

    # Volume Indicator
    if "Volume" in df.columns:
        df["Volume_SMA20"] = df["Volume"].rolling(20).mean().fillna(0)
    else:
        df["Volume"] = 1.0
        df["Volume_SMA20"] = 1.0

    return df


def calculate_zigzag(df, depth=12, backstep=6):
    """تحديد نقاط الارتكاز للزيجزاج"""
    df = df.copy()
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
    """فلترة نقاط الارتكاز الزمني بحسب Dynamic Swing"""
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


class PatternValidatorPipeline:
    """أنبوب الفحص الموحد شاملاً شروط الكسر، الاتجاه، وتأكيد حجم التداول"""

    def __init__(self, df):
        self.df = df
        self.filters = [
            self.time_filter,
            self.trend_filter,
            self.invalidation_filter,
            self.indicator_confirmation_filter,
            self.breakout_filter,
            self.volume_filter
        ]

    def time_filter(self, p, data, pattern_type="Bearish"):
        positions = [x["pos"] for x in p]
        for j in range(len(positions) - 1):
            if (positions[j+1] - positions[j]) < MIN_WAVE_CANDLES:
                return False, None, None
        return True, None, None

    def trend_filter(self, p, data, pattern_type="Bearish"):
        idx_0 = p[0]["idx"]
        pre_df = data.loc[:idx_0]

        if len(pre_df) > 10:
            if pattern_type == "Bearish":
                past_min = pre_df["Low"].iloc[-10:].min()
                if past_min > p[0]["val"]:
                    return False, None, None
            else:
                past_max = pre_df["High"].iloc[-10:].max()
                if past_max < p[0]["val"]:
                    return False, None, None

        return True, None, None

    def invalidation_filter(self, p, data, pattern_type="Bearish"):
        idx_head = p[3]["idx"]
        head_val = p[3]["val"]

        post_head_df = data.loc[idx_head:]

        if not post_head_df.empty:
            if pattern_type == "Bearish":
                if post_head_df["High"].max() > head_val:
                    return False, None, None
            else:
                if post_head_df["Low"].min() < head_val:
                    return False, None, None

        return True, None, None

    def indicator_confirmation_filter(self, p, data, pattern_type="Bearish"):
        idx_shoulder2 = p[5]["idx"]
        if idx_shoulder2 not in data.index:
            return False, None, None

        rsi_val = data.loc[idx_shoulder2, "RSI"]
        rsi_min = CONFIG["RSI_BEARISH_MIN"] if pattern_type == "Bearish" else CONFIG["RSI_BULLISH_MIN"]
        rsi_max = CONFIG["RSI_BEARISH_MAX"] if pattern_type == "Bearish" else CONFIG["RSI_BULLISH_MAX"]

        if not (rsi_min <= rsi_val <= rsi_max):
            return False, None, None

        ema50 = data.loc[idx_shoulder2, "EMA50"]
        ema200 = data.loc[idx_shoulder2, "EMA200"]

        if pd.isna(ema50) or pd.isna(ema200):
            return False, None, None

        return True, None, None

    def breakout_filter(self, p, data, pattern_type="Bearish"):
        idx_shoulder2 = p[5]["idx"]
        neckline_avg = (p[2]["val"] + p[4]["val"]) / 2.0

        post_shoulder_df = data.loc[idx_shoulder2:]

        if pattern_type == "Bearish":
            breakout_candles = post_shoulder_df[post_shoulder_df["Close"] < neckline_avg]
        else:
            breakout_candles = post_shoulder_df[post_shoulder_df["Close"] > neckline_avg]

        if breakout_candles.empty:
            return False, None, None

        end_idx = breakout_candles.index[0]
        end_val = breakout_candles["Close"].iloc[0]

        return True, end_idx, end_val

    def volume_filter(self, p, data, pattern_type="Bearish"):
        """شرط زيادة حجم التداول في شمعة الكسر وما بعدها"""
        # الفحص يحتاج معرفة شمعة الكسر
        passed_breakout, end_idx, _ = self.breakout_filter(p, data, pattern_type)

        if not passed_breakout or end_idx not in data.index:
            return False, None, None

        if "Volume" not in data.columns or "Volume_SMA20" not in data.columns:
            return True, end_idx, None  # استمرار التجاور إذا لم تتوفر بيانات الفوليوم

        # فحص الشمعة المسؤولة عن الكسر وشمعة المتابعة الكائنة بعدها
        breakout_pos = data.index.get_loc(end_idx)
        check_candles = data.iloc[breakout_pos:min(breakout_pos + 3, len(data))]

        # اشتراط وجود زيادة في حجم التداول مقارنة بـ SMA20 بحد أدنى
        has_volume_spike = (
            check_candles["Volume"] >= (check_candles["Volume_SMA20"] * CONFIG["VOLUME_BREAKOUT_FACTOR"])
        ).any()

        if not has_volume_spike:
            return False, None, None

        return True, end_idx, None

    def run(self, p, pattern_type="Bearish"):
        end_idx, end_val = None, None

        for f in self.filters:
            passed, e_idx, e_val = f(p, self.df, pattern_type)

            if not passed:
                return False, None, None

            if e_idx is not None:
                end_idx = e_idx
            if e_val is not None:
                end_val = e_val

        if end_val is None and end_idx is not None:
            end_val = self.df.loc[end_idx, "Close"]

        return True, end_idx, end_val


def simulate_backtest_outcome(pattern, df):
    """محاكاة نتائج الصفقات المكتشفة"""
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
                if hit_sl:
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
                if hit_sl:
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
                if hit_ssl:
                    shoulder_result = "LOSS"
                    shoulder_done = True
                elif hit_tp:
                    shoulder_result = "WIN"
                    shoulder_done = True
            elif bias == "Bullish":
                hit_ssl = low <= shoulder_sl
                hit_tp = high >= tp
                if hit_ssl:
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


def detect_all_head_shoulders_base(pivots, df):
    """اكتشاف نموذج الرأس والكتفين الهابط مع تسمية النقاط L0, H1(LS), L1(N1), H2(Head), L2(N2), H3(RS), Breakout"""
    patterns = []

    if len(pivots) < 6:
        return patterns

    validator = PatternValidatorPipeline(df)
    total_candles = len(df)
    latest_close = float(df["Close"].iloc[-1])

    for i in range(len(pivots) - 5):
        p = pivots[i:i + 6]

        if [x["type"] for x in p] != ["L", "H", "L", "H", "L", "H"]:
            continue

        l0, h1, l1, h2, l2, h3 = [x["val"] for x in p]

        if h1 <= l0 or l1 <= l0:
            continue

        if h2 <= h1 or h2 <= h3:
            continue

        neckline_min = min(l1, l2)
        head_height = h2 - neckline_min

        if head_height <= 0:
            continue

        if abs(h1 - h3) > (head_height * 0.35):
            continue

        max_shoulder = max(h1, h3)

        if (h2 - max_shoulder) < (head_height * 0.25):
            continue

        if abs(l1 - l2) > (head_height * 0.25):
            continue

        passed, end_idx, end_val = validator.run(p, "Bearish")

        if not passed:
            continue

        end_pos = df.index.get_loc(end_idx)

        l1_idx, l2_idx = p[2]["idx"], p[4]["idx"]
        neckline_avg = (l1 + l2) / 2.0

        actual_head_length = h2 - neckline_avg

        entry = neckline_avg
        sl = h2
        shoulder_sl = max(h1, h3)
        tp = entry - actual_head_length

        # قائمة العقد المسماة بحسب المخطط المطلوب L0 -> Breakout
        node_labels = ["L0", "LS (H1)", "N1 (L1)", "Head (H2)", "N2 (L2)", "RS (H3)", "Breakout"]
        nodes = [
            {"idx": p[0]["idx"], "val": l0, "label": "L0"},
            {"idx": p[1]["idx"], "val": h1, "label": "LS (H1)"},
            {"idx": p[2]["idx"], "val": l1, "label": "N1 (L1)"},
            {"idx": p[3]["idx"], "val": h2, "label": "Head (H2)"},
            {"idx": p[4]["idx"], "val": l2, "label": "N2 (L2)"},
            {"idx": p[5]["idx"], "val": h3, "label": "RS (H3)"},
            {"idx": end_idx, "val": float(end_val), "label": "Breakout"}
        ]

        nodes_tuples = [(x["idx"], x["val"]) for x in nodes]

        neckline_nodes = [(l1_idx, l1), (l2_idx, l2)]
        target_nodes = [
            (end_idx, float(round(entry, 5))),
            (end_idx, float(round(tp, 5)))
        ]

        pattern_dict = {
            "name": "Head and Shoulders",
            "pattern": "Head and Shoulders",
            "bias": "Bearish",
            "match": 100.0,
            "nodes": nodes_tuples,
            "nodes_detailed": nodes,
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
            "Shoulder SL": float(round(shoulder_sl, 5)),
            "recency_candle_count": total_candles - end_pos
        }

        trade_result, exit_idx, exit_price, extra_stats = simulate_backtest_outcome(pattern_dict, df)
        pattern_dict["trade_result"] = trade_result
        pattern_dict["Head Result"] = extra_stats["head_result"]
        pattern_dict["Shoulder Result"] = extra_stats["shoulder_result"]
        pattern_dict["Candles to Exit (Cabdale)"] = extra_stats["candles_to_exit"]
        pattern_dict["Candles to TP Move"] = extra_stats["candles_to_tp_move"]

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

        is_valid_entry = (progress_ratio <= CONFIG["VALID_ENTRY_PROGRESS_MAX"]) and not hit_sl_live
        is_near_target = (CONFIG["NEAR_TARGET_PROGRESS_MIN"] <= progress_ratio < 1.0) and not hit_sl_live

        pattern_dict["progress_ratio"] = float(round(progress_ratio * 100, 2))
        pattern_dict["is_valid_entry"] = is_valid_entry
        pattern_dict["is_near_target"] = is_near_target

        patterns.append(pattern_dict)

    return patterns


def detect_all_inverse_head_shoulders(pivots, df):
    """اكتشاف نموذج الرأس والكتفين المعكوس مع تسمية النقاط H0, L1(LS), H1(N1), L2(Head), H2(N2), L3(RS), Breakout"""
    patterns = []

    if len(pivots) < 6:
        return patterns

    validator = PatternValidatorPipeline(df)
    total_candles = len(df)
    latest_close = float(df["Close"].iloc[-1])

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

        if abs(l1 - l3) > (head_depth * 0.35):
            continue

        min_shoulder = min(l1, l3)

        if (min_shoulder - l2) < (head_depth * 0.25):
            continue

        if abs(h1 - h2) > (head_depth * 0.25):
            continue

        passed, end_idx, end_val = validator.run(p, "Bullish")

        if not passed:
            continue

        end_pos = df.index.get_loc(end_idx)

        h1_idx, h2_idx = p[2]["idx"], p[4]["idx"]
        neckline_avg = (h1 + h2) / 2.0

        entry = neckline_avg
        sl = l2
        shoulder_sl = min(l1, l3)
        actual_head_length = neckline_avg - l2
        tp = entry + actual_head_length

        nodes = [
            {"idx": p[0]["idx"], "val": h0, "label": "H0"},
            {"idx": p[1]["idx"], "val": l1, "label": "LS (L1)"},
            {"idx": p[2]["idx"], "val": h1, "label": "N1 (H1)"},
            {"idx": p[3]["idx"], "val": l2, "label": "Head (L2)"},
            {"idx": p[4]["idx"], "val": h2, "label": "N2 (H2)"},
            {"idx": p[5]["idx"], "val": l3, "label": "RS (L3)"},
            {"idx": end_idx, "val": float(end_val), "label": "Breakout"}
        ]

        nodes_tuples = [(x["idx"], x["val"]) for x in nodes]

        neckline_nodes = [(h1_idx, h1), (h2_idx, h2)]
        target_nodes = [
            (end_idx, float(round(entry, 5))),
            (end_idx, float(round(tp, 5)))
        ]

        pattern_dict = {
            "name": "Inverse Head and Shoulders",
            "pattern": "Inverse Head and Shoulders",
            "bias": "Bullish",
            "match": 100.0,
            "nodes": nodes_tuples,
            "nodes_detailed": nodes,
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
            "Shoulder SL": float(round(shoulder_sl, 5)),
            "recency_candle_count": total_candles - end_pos
        }

        trade_result, exit_idx, exit_price, extra_stats = simulate_backtest_outcome(pattern_dict, df)
        pattern_dict["trade_result"] = trade_result
        pattern_dict["Head Result"] = extra_stats["head_result"]
        pattern_dict["Shoulder Result"] = extra_stats["shoulder_result"]
        pattern_dict["Candles to Exit (Cabdale)"] = extra_stats["candles_to_exit"]
        pattern_dict["Candles to TP Move"] = extra_stats["candles_to_tp_move"]

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

        is_valid_entry = (progress_ratio <= CONFIG["VALID_ENTRY_PROGRESS_MAX"]) and not hit_sl_live
        is_near_target = (CONFIG["NEAR_TARGET_PROGRESS_MIN"] <= progress_ratio < 1.0) and not hit_sl_live

        pattern_dict["progress_ratio"] = float(round(progress_ratio * 100, 2))
        pattern_dict["is_valid_entry"] = is_valid_entry
        pattern_dict["is_near_target"] = is_near_target

        patterns.append(pattern_dict)

    return patterns


def detect_all_head_shoulders(pivots, df):
    """دمج النماذج وترتيبها زمنياً"""
    normal_patterns = detect_all_head_shoulders_base(pivots, df)
    inverse_patterns = detect_all_inverse_head_shoulders(pivots, df)

    all_patterns = normal_patterns + inverse_patterns
    all_patterns.sort(key=lambda x: x.get("end_pos", -1))
    return all_patterns


def create_pattern_chart(analysis_result):
    """رسم الشارت التفاعلي وإسقاط النمط وتسميات النقاط L0/H0 بدقة فوق الشمعات"""
    if not analysis_result or "df" not in analysis_result or analysis_result["df"].empty:
        return None

    df = analysis_result["df"]
    all_patterns = analysis_result.get("all_patterns", [])

    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        subplot_titles=('Price Chart & Head & Shoulders Patterns', 'RSI & Volume'),
        row_width=[0.25, 0.75]
    )

    # 1. الشموع اليابانية
    fig.add_trace(
        go.Candlestick(
            x=df.index,
            open=df['Open'],
            high=df['High'],
            low=df['Low'],
            close=df['Close'],
            name='Candles'
        ),
        row=1, col=1
    )

    # 2. المتوسطات المتحركة
    if "EMA50" in df.columns:
        fig.add_trace(
            go.Scatter(x=df.index, y=df["EMA50"], mode='lines', name='EMA 50', line=dict(color='rgba(255,165,0,0.8)', width=1.2)),
            row=1, col=1
        )
    if "EMA200" in df.columns:
        fig.add_trace(
            go.Scatter(x=df.index, y=df["EMA200"], mode='lines', name='EMA 200', line=dict(color='rgba(0,122,255,0.8)', width=1.5)),
            row=1, col=1
        )

    # 3. RSI
    if "RSI" in df.columns:
        fig.add_trace(
            go.Scatter(x=df.index, y=df["RSI"], mode='lines', name='RSI', line=dict(color='purple', width=1.5)),
            row=2, col=1
        )
        fig.add_hline(y=70, line_dash="dash", line_color="red", row=2, col=1)
        fig.add_hline(y=30, line_dash="dash", line_color="green", row=2, col=1)

    # 4. رسم النمط وتسميات النقاط
    for idx, pat in enumerate(all_patterns):
        nodes_detailed = pat.get("nodes_detailed", [])
        bias = pat.get("bias", "Bearish")
        is_latest = (idx == len(all_patterns) - 1)

        color = "#EF5350" if bias == "Bearish" else "#26A69A"
        line_width = 3 if is_latest else 1.5
        opacity = 1.0 if is_latest else 0.45

        if nodes_detailed:
            x_coords = [n["idx"] for n in nodes_detailed]
            y_coords = [n["val"] for n in nodes_detailed]

            # خط الاتصال بين نقاط النمط
            fig.add_trace(
                go.Scatter(
                    x=x_coords,
                    y=y_coords,
                    mode='lines+markers',
                    name=f"{pat['pattern']} ({bias})",
                    line=dict(color=color, width=line_width),
                    opacity=opacity,
                    marker=dict(size=7, color=color, symbol="diamond")
                ),
                row=1, col=1
            )

            # إضافة التسميات المعيرة بدقة فوق/تحت كل نقطة
            if is_latest:
                for n_info in nodes_detailed:
                    lbl = n_info.get("label", "")
                    nx, ny = n_info["idx"], n_info["val"]
                    
                    is_top = (bias == "Bearish" and ("H" in lbl or "LS" in lbl or "RS" in lbl or "Head" in lbl)) or \
                             (bias == "Bullish" and ("H" in lbl or "N1" in lbl or "N2" in lbl))
                    
                    fig.add_annotation(
                        x=nx, y=ny,
                        text=f"<b>{lbl}</b>",
                        showarrow=True,
                        arrowhead=2,
                        ax=0,
                        ay=-24 if is_top else 24,
                        row=1, col=1
                    )

            # خط الرقبة Neckline
            neckline_nodes = pat.get("neckline_nodes", [])
            if len(neckline_nodes) >= 2:
                nx = [neckline_nodes[0][0], neckline_nodes[1][0]]
                ny = [neckline_nodes[0][1], neckline_nodes[1][1]]
                fig.add_trace(
                    go.Scatter(
                        x=nx, y=ny,
                        mode='lines',
                        name='Neckline',
                        line=dict(color='yellow' if is_latest else 'gray', width=2, dash='dash'),
                        opacity=opacity
                    ),
                    row=1, col=1
                )

            # المستويات المالية (Entry, SL, TP)
            if is_latest:
                entry = pat.get("entry")
                sl = pat.get("sl")
                tp = pat.get("tp")
                end_idx = pat.get("neckline_end_idx")

                if entry and sl and tp and end_idx in df.index:
                    last_x = df.index[-1]

                    fig.add_trace(
                        go.Scatter(x=[end_idx, last_x], y=[entry, entry], mode='lines+text', name='Entry',
                                   text=["", f"Entry: {entry}"], textposition="top right",
                                   line=dict(color='cyan', width=1.5, dash='dot')),
                        row=1, col=1
                    )
                    fig.add_trace(
                        go.Scatter(x=[end_idx, last_x], y=[sl, sl], mode='lines+text', name='SL',
                                   text=["", f"SL: {sl}"], textposition="top right",
                                   line=dict(color='red', width=1.5, dash='dot')),
                        row=1, col=1
                    )
                    fig.add_trace(
                        go.Scatter(x=[end_idx, last_x], y=[tp, tp], mode='lines+text', name='TP',
                                   text=["", f"TP: {tp}"], textposition="top right",
                                   line=dict(color='green', width=1.5, dash='dot')),
                        row=1, col=1
                    )

    fig.update_layout(
        xaxis_rangeslider_visible=False,
        template="plotly_dark",
        height=780,
        margin=dict(l=20, r=20, t=40, b=20)
    )

    return fig


def backtest_strategy(df, interval=None, config=CONFIG, **kwargs):
    """تشغيل باكتيست شامل للبيانات التاريخية"""
    if df is None or df.empty or len(df) < 30:
        return []

    df = df.copy()
    required = ["Open", "High", "Low", "Close"]

    for col in required:
        if col not in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=required)

    df_active = calculate_indicators(df)
    df_active = calculate_zigzag(df_active)

    pivots = get_chronological_pivots(df_active)
    all_patterns = detect_all_head_shoulders(pivots, df_active)

    trades = []
    for pat in all_patterns:
        trade_record = {
            "Pattern": pat["pattern"],
            "Bias": pat["bias"],
            "Entry": pat["entry"],
            "SL": pat["sl"],
            "Shoulder SL": pat.get("shoulder_sl", pat["sl"]),
            "TP": pat["tp"],
            "Head Result": pat.get("Head Result", "OPEN"),
            "Shoulder Result": pat.get("Shoulder Result", "OPEN"),
            "Candles to Exit (Cabdale)": pat.get("Candles to Exit (Cabdale)", 0),
            "Candles to TP Move": pat.get("Candles to TP Move", 0),
            "Hit Shoulder SL": pat.get("Shoulder Result") == "LOSS",
            "Hit Head SL": pat.get("Head Result") == "LOSS",
            "trade_result": pat.get("trade_result", "OPEN"),
            "Progress Ratio (%)": pat.get("progress_ratio", 0.0),
            "Valid Entry": pat.get("is_valid_entry", False),
            "Near Target": pat.get("is_near_target", False)
        }
        trades.append(trade_record)

    return trades


def run_full_analysis(df):
    """دالة التحليل الرئيسي المعتمدة للواجهة البرمجية"""
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
        "fig": None,
        "chart": None
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

    df_active = df.tail(200).copy()
    df_active = calculate_indicators(df_active)
    df_active = calculate_zigzag(df_active)

    pivots = get_chronological_pivots(df_active)
    all_patterns = detect_all_head_shoulders(pivots, df_active)

    if not all_patterns:
        default_response["df"] = df_active
        default_response["fig"] = create_pattern_chart({"df": df_active, "all_patterns": []})
        default_response["chart"] = default_response["fig"]
        return default_response

    recent_patterns = [p for p in all_patterns if p.get("recency_candle_count", 999) <= CONFIG["MAX_RECENCY_CANDLES"]]
    selected_pattern = recent_patterns[-1] if recent_patterns else all_patterns[-1]

    if selected_pattern["pattern"] == "Inverse Head and Shoulders":
        signal = "STRONG BUY"
    elif selected_pattern["pattern"] == "Head and Shoulders":
        signal = "STRONG SELL"
    else:
        signal = "WAITING"

    near_target_patterns = [p for p in all_patterns if p.get("is_near_target", False)]

    analysis_res = {
        "df": df_active,
        "signal": signal,
        "pattern": selected_pattern["pattern"],
        "bias": selected_pattern["bias"],
        "entry": selected_pattern["entry"],
        "entry_trigger": selected_pattern["entry_trigger"],
        "sl": selected_pattern["sl"],
        "shoulder_sl": selected_pattern.get("shoulder_sl", selected_pattern["sl"]),
        "tp": selected_pattern["tp"],
        "nodes": selected_pattern["nodes"],
        "match": selected_pattern["match"],
        "neckline_start_idx": selected_pattern["neckline_start_idx"],
        "neckline_nodes": selected_pattern.get("neckline_nodes", []),
        "target_nodes": selected_pattern.get("target_nodes", []),
        "all_patterns": all_patterns,
        "near_target_patterns": near_target_patterns,
        "trade_result": selected_pattern.get("trade_result", "OPEN")
    }

    fig = create_pattern_chart(analysis_res)
    analysis_res["fig"] = fig
    analysis_res["chart"] = fig

    return analysis_res


if __name__ == "__main__":
    print("ENGINE.PY loaded with Volume Confirmation & Labeling Scheme (v4.7).")
