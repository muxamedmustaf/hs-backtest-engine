def detect_all_head_shoulders_base(pivots, df):
    patterns = []
    if len(pivots) < 6:
        return patterns

    validator = PatternValidatorPipeline(df)
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

        # SHURUUDA ADAG: Farqiga dhererka garabada max 25%
        height_diff_ratio = abs(right_shoulder_height - left_shoulder_height) / max(left_shoulder_height, 1e-9)
        if height_diff_ratio > 0.25:
            continue

        if abs(l2 - l0) / max(left_shoulder_height, 1e-9) > 0.25:
            continue
        if abs(l2 - l1) / max(left_shoulder_height, 1e-9) > 0.25:
            continue
        if abs(h3 - h1) / max(left_shoulder_height, 1e-9) > 0.25:
            continue

        neckline_min = min(l1, l2)
        head_height = h2 - neckline_min
        if head_height <= 0:
            continue

        # SHURUUDA ADAG: Garabada heerooda (h1 vs h3) max 15%
        if abs(h1 - h3) > (head_height * 0.15):
            continue

        # SHURUUDA ADAG: Madaxu waa inuu ugu yarayn 30% ka sarreeyaa garabka ugu sareeya
        max_shoulder = max(h1, h3)
        if (h2 - max_shoulder) < (head_height * 0.30):
            continue

        # SHURUUDA ADAG: Qalooca luqanta max 15%
        if abs(l1 - l2) > (head_height * 0.15):
            continue

        passed, end_idx, end_val = validator.run(p)
        if not passed:
            continue

        l1_idx, l2_idx = p[2]["idx"], p[4]["idx"]
        neckline_avg = (l1 + l2) / 2.0
        actual_head_length = h2 - neckline_avg

        entry = neckline_avg
        sl = h2
        shoulder_sl = max(h1, h3)
        tp = entry - actual_head_length

        total_tp_dist = abs(entry - tp)
        moved_dist = max(0.0, entry - latest_close) if latest_close < entry else 0.0
        progress_ratio = moved_dist / total_tp_dist if total_tp_dist > 0 else 0.0

        post_breakout_df = df.loc[end_idx:]
        hit_sl_live = (post_breakout_df["High"] >= sl).any()

        is_valid_entry = (progress_ratio <= (1.0 / 3.0)) and not hit_sl_live
        is_near_target = (0.70 <= progress_ratio < 1.0) and not hit_sl_live

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
            "Shoulder SL": float(round(shoulder_sl, 5)),
            "progress_ratio": float(round(progress_ratio * 100, 2)),
            "is_valid_entry": is_valid_entry,
            "is_near_target": is_near_target,
            "status": "ACTIVE_ENTRY" if is_valid_entry else ("NEAR_TARGET" if is_near_target else "IN_PROGRESS")
        }

        trade_result, exit_idx, exit_price, extra_stats = simulate_backtest_outcome(pattern_dict, df)
        pattern_dict["trade_result"] = trade_result
        pattern_dict["Head Result"] = extra_stats["head_result"]
        pattern_dict["Shoulder Result"] = extra_stats["shoulder_result"]
        pattern_dict["Candles to Exit (Cabdale)"] = extra_stats["candles_to_exit"]
        pattern_dict["Candles to TP Move"] = extra_stats["candles_to_tp_move"]
        pattern_dict["exit_idx"] = exit_idx
        pattern_dict["exit_price"] = exit_price

        patterns.append(pattern_dict)

    return patterns


def detect_all_inverse_head_shoulders(pivots, df):
    patterns = []
    if len(pivots) < 6:
        return patterns

    latest_close = float(df["Close"].iloc[-1])

    for i in range(len(pivots) - 5):
        p = pivots[i:i + 6]
        if [x["type"] for x in p] != ["H", "L", "H", "L", "H", "L"]:
            continue

        h0, l1, h1, l2, h2, l3 = [x["val"] for x in p]

        if l2 >= l1 or l2 >= l3:
            continue

        if l1 >= min(h0, h1):
            continue

        left_shoulder_depth = max(h0, h1) - l1
        right_shoulder_depth = max(h1, h2) - l3

        if left_shoulder_depth <= 0 or right_shoulder_depth <= 0:
            continue

        # SHURUUDA ADAG: Farqiga dhererka garabada max 25%
        depth_diff_ratio = abs(right_shoulder_depth - left_shoulder_depth) / max(left_shoulder_depth, 1e-9)
        if depth_diff_ratio > 0.25:
            continue

        if abs(h2 - h0) / max(left_shoulder_depth, 1e-9) > 0.25:
            continue
        if abs(h2 - h1) / max(left_shoulder_depth, 1e-9) > 0.25:
            continue
        if abs(l3 - l1) / max(left_shoulder_depth, 1e-9) > 0.25:
            continue

        neckline_max = max(h1, h2)
        head_depth = neckline_max - l2
        if head_depth <= 0:
            continue

        # SHURUUDA ADAG: Max 15% farqiga l1 vs l3
        if abs(l1 - l3) > (head_depth * 0.15):
            continue

        # SHURUUDA ADAG: Madaxu waa inuu ugu yarayn 30% ka hooseeyaa garabka ugu hooseeya
        min_shoulder = min(l1, l3)
        if (min_shoulder - l2) < (head_depth * 0.30):
            continue

        # SHURUUDA ADAG: Qalooca luqanta max 15%
        if abs(h1 - h2) > (head_depth * 0.15):
            continue

        positions = [x["pos"] for x in p]
        if any((positions[j+1] - positions[j]) < MIN_WAVE_CANDLES for j in range(5)):
            continue

        idx_h0 = p[0]["idx"]
        pre_left_df = df.loc[:idx_h0]
        if len(pre_left_df) > 10:
            past_max = float(pre_left_df["High"].iloc[-10:].max())
            if past_max < p[0]["val"]:
                continue

        idx_l2 = p[3]["idx"]
        post_head_df = df.loc[idx_l2:]
        if not post_head_df.empty:
            if float(post_head_df["Low"].min()) < l2:
                continue

        idx_l3 = p[5]["idx"]
        if idx_l3 not in df.index:
            continue

        # ----------------------------------------------------
        # RSI SIDIISII HORE LOO CELIYAY (25 - 70)
        # ----------------------------------------------------
        rsi_val = float(df.loc[idx_l3, "RSI"])
        if not (25 <= rsi_val <= 70):
            continue

        ema50 = df.loc[idx_l3, "EMA50"]
        ema200 = df.loc[idx_l3, "EMA200"]
        if pd.isna(ema50) or pd.isna(ema200):
            continue

        h1_idx, h2_idx = p[2]["idx"], p[4]["idx"]
        neckline_avg = (h1 + h2) / 2.0

        post_l3_df = df.loc[idx_l3:]
        breakout_candles = post_l3_df[post_l3_df["Close"] > neckline_avg]

        if breakout_candles.empty:
            continue

        end_idx = breakout_candles.index[0]
        end_val = float(breakout_candles["Close"].iloc[0])

        entry = neckline_avg
        sl = l2
        shoulder_sl = min(l1, l3)
        actual_head_length = neckline_avg - l2
        tp = entry + actual_head_length

        total_tp_dist = abs(tp - entry)
        moved_dist = max(0.0, latest_close - entry) if latest_close > entry else 0.0
        progress_ratio = moved_dist / total_tp_dist if total_tp_dist > 0 else 0.0

        post_breakout_df = df.loc[end_idx:]
        hit_sl_live = (post_breakout_df["Low"] <= sl).any()

        is_valid_entry = (progress_ratio <= (1.0 / 3.0)) and not hit_sl_live
        is_near_target = (0.70 <= progress_ratio < 1.0) and not hit_sl_live

        nodes = [(x["idx"], x["val"]) for x in p]
        nodes.append((end_idx, end_val))

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
            "Shoulder SL": float(round(shoulder_sl, 5)),
            "progress_ratio": float(round(progress_ratio * 100, 2)),
            "is_valid_entry": is_valid_entry,
            "is_near_target": is_near_target,
            "status": "ACTIVE_ENTRY" if is_valid_entry else ("NEAR_TARGET" if is_near_target else "IN_PROGRESS")
        }

        trade_result, exit_idx, exit_price, extra_stats = simulate_backtest_outcome(pattern_dict, df)
        pattern_dict["trade_result"] = trade_result
        pattern_dict["Head Result"] = extra_stats["head_result"]
        pattern_dict["Shoulder Result"] = extra_stats["shoulder_result"]
        pattern_dict["Candles to Exit (Cabdale)"] = extra_stats["candles_to_exit"]
        pattern_dict["Candles to TP Move"] = extra_stats["candles_to_tp_move"]
        pattern_dict["exit_idx"] = exit_idx
        pattern_dict["exit_price"] = exit_price

        patterns.append(pattern_dict)

    return patterns
