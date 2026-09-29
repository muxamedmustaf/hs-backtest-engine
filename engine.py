import pandas as pd
import numpy as np

# الإعدادات الافتراضية
CONFIG = {
    "SHOULDER_DIFF_MAX_RATIO": 0.25,
    "HEAD_MIN_PROPORTION": 0.15,
    "NECKLINE_DIFF_MAX_RATIO": 0.20,
    "MAX_BREAKOUT_RECENCY": 50,
    "MAX_BREAKOUT_WAIT_CANDLES": 20,  # الحد الأقصى للشموع بين آخر نقطة والكسر
    "VALID_ENTRY_PROGRESS_MAX": 0.30,
    "NEAR_TARGET_PROGRESS_MIN": 0.70
}


def detect_all_head_shoulders_base(pivots, df, config=CONFIG, is_backtest=False):
    """
    اكتشاف نمط الرأس والكتفين العادي (الهابط)
    - الشروط: H1 > L0, H1 > L1 | H3 > L2, H3 > L1 | H2 > H1, H2 > H3
    - ألا يتجاوز الكسر 20 شمعة من H3
    """
    patterns = []
    if len(pivots) < 6:
        return patterns

    validator = PatternValidatorPipeline(df, config)
    total_candles = len(df)
    latest_close = float(df["Close"].iloc[-1])
    max_wait_candles = config.get("MAX_BREAKOUT_WAIT_CANDLES", 20)

    for i in range(len(pivots) - 5):
        p = pivots[i:i + 6]
        if [x["type"] for x in p] != ["L", "H", "L", "H", "L", "H"]:
            continue

        l0, h1, l1, h2, l2, h3 = [x["val"] for x in p]

        # 1. ضبط علاقات القمم والقيعان (H1/H3 مع L0/L1/L2)
        if h1 <= l0 or h1 <= l1:
            continue
        if h3 <= l2 or h3 <= l1:
            continue
        if h2 <= h1 or h2 <= h3:
            continue

        neckline_min = min(l1, l2)
        head_height = h2 - neckline_min
        if head_height <= 0:
            continue

        # 2. الفحوصات الهندسية لنسب الكتفين والرأس
        if abs(h1 - h3) > (head_height * config["SHOULDER_DIFF_MAX_RATIO"]):
            continue

        max_shoulder = max(h1, h3)
        if (h2 - max_shoulder) < (head_height * config["HEAD_MIN_PROPORTION"]):
            continue

        if abs(l1 - l2) > (head_height * config["NECKLINE_DIFF_MAX_RATIO"]):
            continue

        # 3. التحقق من وقوع الكسر
        passed, end_idx, end_val = validator.run(p, "Bearish")
        if not passed:
            continue

        end_pos = df.index.get_loc(end_idx)
        last_pivot_pos = p[5]["pos"]  # موقع H3

        # 4. شرط الكسر خلال 20 شمعة كحد أقصى من H3
        if (end_pos - last_pivot_pos) > max_wait_candles:
            continue

        if not is_backtest and config.get("MAX_BREAKOUT_RECENCY") is not None:
            if (total_candles - end_pos) > config["MAX_BREAKOUT_RECENCY"]:
                continue

        # حسابات مستويات التداول والأهداف
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
            "end_pos": p[5]["pos"],
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


def detect_all_inverse_head_shoulders(pivots, df, config=CONFIG, is_backtest=False):
    """
    اكتشاف نمط الرأس والكتفين المعكوس (الصاعد)
    - الشروط: L1 < H0, L1 < H1 | L3 < H2, L3 < H1 | L2 < L1, L2 < L3
    - ألا يتجاوز الكسر 20 شمعة من L3
    """
    patterns = []
    if len(pivots) < 6:
        return patterns

    validator = PatternValidatorPipeline(df, config)
    total_candles = len(df)
    latest_close = float(df["Close"].iloc[-1])
    max_wait_candles = config.get("MAX_BREAKOUT_WAIT_CANDLES", 20)

    for i in range(len(pivots) - 5):
        p = pivots[i:i + 6]
        if [x["type"] for x in p] != ["H", "L", "H", "L", "H", "L"]:
            continue

        h0, l1, h1, l2, h2, l3 = [x["val"] for x in p]

        # 1. ضبط علاقات القيعان والقمم (L1/L3 مع H0/H1/H2)
        if l1 >= h0 or l1 >= h1:
            continue
        if l3 >= h2 or l3 >= h1:
            continue
        if l2 >= l1 or l2 >= l3:
            continue

        neckline_max = max(h1, h2)
        head_depth = neckline_max - l2
        if head_depth <= 0:
            continue

        # 2. الفحوصات الهندسية لنسب الكتفين والرأس
        if abs(l1 - l3) > (head_depth * config["SHOULDER_DIFF_MAX_RATIO"]):
            continue

        min_shoulder = min(l1, l3)
        if (min_shoulder - l2) < (head_depth * config["HEAD_MIN_PROPORTION"]):
            continue

        if abs(h1 - h2) > (head_depth * config["NECKLINE_DIFF_MAX_RATIO"]):
            continue

        # 3. التحقق من وقوع الكسر
        passed, end_idx, end_val = validator.run(p, "Bullish")
        if not passed:
            continue

        end_pos = df.index.get_loc(end_idx)
        last_pivot_pos = p[5]["pos"]  # موقع L3

        # 4. شرط الكسر خلال 20 شمعة كحد أقصى من L3
        if (end_pos - last_pivot_pos) > max_wait_candles:
            continue

        if not is_backtest and config.get("MAX_BREAKOUT_RECENCY") is not None:
            if (total_candles - end_pos) > config["MAX_BREAKOUT_RECENCY"]:
                continue

        # حسابات مستويات التداول والأهداف
        h1_idx, h2_idx = p[2]["idx"], p[4]["idx"]
        neckline_avg = (h1 + h2) / 2.0
        actual_head_length = neckline_avg - l2

        entry = neckline_avg
        sl = l2
        shoulder_sl = min(l1, l3)
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

        trade_result, exit_idx, exit_price, extra_stats = simulate_backtest_outcome(pattern_dict, df)
        pattern_dict["trade_result"] = trade_result
        pattern_dict["Head Result"] = extra_stats["head_result"]
        pattern_dict["Shoulder Result"] = extra_stats["shoulder_result"]
        pattern_dict["Candles to Exit (Cabdale)"] = extra_stats["candles_to_exit"]
        pattern_dict["Candles to TP Move"] = extra_stats["candles_to_tp_move"]
        pattern_dict["exit_idx"] = exit_idx
        pattern_dict["exit_price"] = exit_price

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
