import pandas as pd
import numpy as np

# ==========================================================
# ENGINE.PY - STRICT SHOULDER SYMMETRY & DYNAMIC SCANNER
# ==========================================================

MIN_WAVE_CANDLES = 3
MAX_WAVE_CANDLES = 40       # منع التباعد الزمني المفرط بين نقاط النموذج

MIN_PRE_TREND_MOVE = 0.015  # شرط حركة اتجاهية سابقة لا تقل عن 1.5%
MIN_SHOULDER_REACTION = 0.003

# تعديل التباين المقبول بين قمتي/قاعي الكتفين وعمقهما ليصبح 10% كحد أقصى
MAX_SHOULDER_LEVEL_DIFF = 0.10  # 10% تباين أقصى بين القمم/القيعان
MAX_SHOULDER_DEPTH_DIFF = 0.10  # 10% تباين أقصى في العمق والارتفاع


def calculate_indicators(df):
    df = df.copy()
    df["EMA50"] = df["Close"].ewm(span=50, adjust=False).mean()
    df["EMA200"] = df["Close"].ewm(span=200, adjust=False).mean()

    delta = df["Close"].diff()
    gain = delta.where(delta > 0, 0.0).rolling(14).mean()
    loss = -delta.where(delta < 0, 0.0).rolling(14).mean()

    loss_safe = loss.replace(0, 1e-9)
    rs = gain / loss_safe

    df["RSI"] = 100 - (100 / (1 + rs))
    df["RSI"] = df["RSI"].fillna(50.0)

    high_low = df["High"] - df["Low"]
    high_close = np.abs(df["High"] - df["Close"].shift())
    low_close = np.abs(df["Low"] - df["Close"].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = ranges.max(axis=1)
    df["ATR"] = true_range.rolling(14).mean()

    df["Dynamic_Swing"] = (df["ATR"] / df["Close"]) * 0.5
    df["Dynamic_Swing"] = df["Dynamic_Swing"].fillna(0.001)

    return df


def calculate_zigzag(df, depth=12, backstep=6):
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

    def __init__(self, df, pattern_type="Head and Shoulders"):
        self.df = df
        self.pattern_type = pattern_type
        self.filters = [
            self.time_filter,
            self.trend_filter,
            self.invalidation_filter,
            self.indicator_confirmation_filter,
            self.breakout_filter
        ]

    def time_filter(self, p, data):
        """
        التحقق من توازن الزمن وعدم التباعد المفرط بين الشموع لمنع التشويه
        """
        i_l0, i_h1, i_l1, i_h2, i_l2, i_h3 = [x["pos"] for x in p]
        
        diffs = [
            i_h1 - i_l0,
            i_l1 - i_h1,
            i_h2 - i_l1,
            i_l2 - i_h2,
            i_h3 - i_l2
        ]

        for d in diffs:
            if d < MIN_WAVE_CANDLES or d > MAX_WAVE_CANDLES:
                return False, None, None

        return True, None, None

    def trend_filter(self, p, data):
        idx_start = p[0]["idx"]
        pos_start = data.index.get_loc(idx_start)

        lookback = 20
        if pos_start < lookback:
            return False, None, None

        pre_pattern_df = data.iloc[pos_start - lookback : pos_start]
        
        ema50_pre = pre_pattern_df["EMA50"].dropna()
        ema200_pre = pre_pattern_df["EMA200"].dropna()

        if ema50_pre.empty or ema200_pre.empty:
            return False, None, None

        last_ema50 = ema50_pre.iloc[-1]
        last_ema200 = ema200_pre.iloc[-1]

        if self.pattern_type == "Head and Shoulders":
            start_price = pre_pattern_df["Low"].min()
            h1_price = p[1]["val"]
            upward_move = (h1_price - start_price) / max(abs(start_price), 1e-9)

            if upward_move < MIN_PRE_TREND_MOVE or last_ema50 < last_ema200:
                return False, None, None

        else:
            start_price = pre_pattern_df["High"].max()
            l1_price = p[1]["val"]
            downward_move = (start_price - l1_price) / max(abs(start_price), 1e-9)

            if downward_move < MIN_PRE_TREND_MOVE or last_ema50 > last_ema200:
                return False, None, None

        return True, None, None

    def invalidation_filter(self, p, data):
        h2 = p[3]["val"]
        idx_h2 = p[3]["idx"]
        idx_h3 = p[5]["idx"]

        post_head_df = data.loc[idx_h2:idx_h3]
        if len(post_head_df) > 1:
            if self.pattern_type == "Head and Shoulders":
                if post_head_df["High"].iloc[1:].max() > h2:
                    return False, None, None
            else:
                if post_head_df["Low"].iloc[1:].min() < h2:
                    return False, None, None
        return True, None, None

    def indicator_confirmation_filter(self, p, data):
        idx_h3 = p[5]["idx"]
        rsi_val = data.loc[idx_h3, "RSI"]
        ema50 = data.loc[idx_h3, "EMA50"]
        ema200 = data.loc[idx_h3, "EMA200"]
        close_val = data.loc[idx_h3, "Close"]

        if pd.isna(ema50) or pd.isna(ema200) or pd.isna(rsi_val):
            return False, None, None

        if self.pattern_type == "Head and Shoulders":
            if close_val > max(ema50, ema200) or rsi_val > 65:
                return False, None, None
        else:
            if close_val < min(ema50, ema200) or rsi_val < 35:
                return False, None, None

        return True, None, None

    def breakout_filter(self, p, data):
        idx_h3 = p[5]["idx"]
        pos_h3 = data.index.get_loc(idx_h3)
        search_window = data.iloc[pos_h3 : pos_h3 + 40]

        if self.pattern_type == "Head and Shoulders":
            l1, l2 = p[2]["val"], p[4]["val"]
            h2 = p[3]["val"]
            neckline_avg = (l1 + l2) / 2.0

            for idx, row in search_window.iterrows():
                close = float(row["Close"])
                rsi = float(row.get("RSI", 50))
                
                if float(row["High"]) > h2:
                    return False, None, None
                
                if close < neckline_avg and rsi < 50:
                    return True, idx, close
        else:
            h1, h2_neck = p[2]["val"], p[4]["val"]
            l2_head = p[3]["val"]
            neckline_avg = (h1 + h2_neck) / 2.0

            for idx, row in search_window.iterrows():
                close = float(row["Close"])
                rsi = float(row.get("RSI", 50))
                
                if float(row["Low"]) < l2_head:
                    return False, None, None
                
                if close > neckline_avg and rsi > 50:
                    return True, idx, close

        return False, None, None

    def run(self, p):
        end_idx, end_val = None, None
        for f in self.filters:
            passed, e_idx, e_val = f(p, self.df)
            if not passed:
                return False, None, None
            if e_idx is not None:
                end_idx, end_val = e_idx, e_val
        return True, end_idx, end_val


def detect_all_head_shoulders(pivots, df):
    patterns = []
    if len(pivots) < 6:
        return patterns

    validator = PatternValidatorPipeline(df, pattern_type="Head and Shoulders")

    for i in range(len(pivots) - 5):
        p = pivots[i:i + 6]
        if [x["type"] for x in p] != ["L", "H", "L", "H", "L", "H"]:
            continue

        l0, h1, l1, h2, l2, h3 = [x["val"] for x in p]

        if h1 <= l0 or l1 <= l0 or h2 <= h1 or h2 <= h3:
            continue

        left_reaction_up = (h1 - l0) / max(abs(l0), 1e-9)
        left_reaction_down = (h1 - l1) / max(abs(h1), 1e-9)
        right_reaction_up = (h3 - l2) / max(abs(l2), 1e-9)
        if left_reaction_up < MIN_SHOULDER_REACTION or left_reaction_down < MIN_SHOULDER_REACTION or right_reaction_up < MIN_SHOULDER_REACTION:
            continue

        # شرط تماثل قمة الكتف الأيمن بقمة الكتف الأيسر (10% تباين كحد أقصى)
        shoulder_level_diff = abs(h1 - h3) / max(abs(h1), 1e-9)
        if shoulder_level_diff > MAX_SHOULDER_LEVEL_DIFF:
            continue

        # شرط تماثل عمق الكتفين (10% تباين كحد أقصى)
        left_depth = h1 - l1
        right_depth = h3 - l2
        if left_depth <= 0 or right_depth <= 0:
            continue

        if abs(left_depth - right_depth) / max(left_depth, right_depth) > MAX_SHOULDER_DEPTH_DIFF:
            continue

        passed, end_idx, end_val = validator.run(p)
        if not passed:
            continue

        l1_idx = p[2]["idx"]
        neckline_avg = (l1 + l2) / 2.0
        actual_head_length = h2 - neckline_avg

        entry = neckline_avg
        sl = h2
        tp = entry - actual_head_length

        nodes = [(x["idx"], x["val"]) for x in p]
        nodes.append((end_idx, float(end_val)))

        patterns.append({
            "name": "Head and Shoulders",
            "pattern": "Head and Shoulders",
            "bias": "Bearish",
            "match": 100.0,
            "nodes": nodes,
            "entry": float(round(entry, 5)),
            "entry_trigger": float(round(entry, 5)),
            "sl": float(round(sl, 5)),
            "tp": float(round(tp, 5)),
            "neckline_start_idx": l1_idx,
            "neckline_end_idx": end_idx,
            "end_pos": p[5]["pos"]
        })

    return patterns


def detect_all_inverse_head_shoulders(pivots, df):
    patterns = []
    if len(pivots) < 6:
        return patterns

    validator = PatternValidatorPipeline(df, pattern_type="Inverse Head and Shoulders")

    for i in range(len(pivots) - 5):
        p = pivots[i:i + 6]
        if [x["type"] for x in p] != ["H", "L", "H", "L", "H", "L"]:
            continue

        h0, l1, h1, l2, h2, l3 = [x["val"] for x in p]

        if l2 >= l1 or l2 >= l3:
            continue

        # شرط تماثل قاع الكتف الأيمن بقاع الكتف الأيسر (10% تباين كحد أقصى)
        shoulder_level_diff = abs(l1 - l3) / max(abs(l1), 1e-9)
        if shoulder_level_diff > MAX_SHOULDER_LEVEL_DIFF:
            continue

        # شرط تماثل عمق الكتفين (10% تباين كحد أقصى)
        left_depth = h1 - l1
        right_depth = h2 - l3
        if left_depth <= 0 or right_depth <= 0:
            continue

        if abs(left_depth - right_depth) / max(left_depth, right_depth) > MAX_SHOULDER_DEPTH_DIFF:
            continue

        passed, end_idx, end_val = validator.run(p)
        if not passed:
            continue

        h1_idx = p[2]["idx"]
        neckline_avg = (h1 + h2) / 2.0
        actual_head_length = neckline_avg - l2

        entry = neckline_avg
        sl = l2
        tp = entry + actual_head_length

        nodes = [(x["idx"], x["val"]) for x in p]
        nodes.append((end_idx, float(end_val)))

        patterns.append({
            "name": "Inverse Head and Shoulders",
            "pattern": "Inverse Head and Shoulders",
            "bias": "Bullish",
            "match": 100.0,
            "nodes": nodes,
            "entry": float(round(entry, 5)),
            "entry_trigger": float(round(entry, 5)),
            "sl": float(round(sl, 5)),
            "tp": float(round(tp, 5)),
            "neckline_start_idx": h1_idx,
            "neckline_end_idx": end_idx,
            "end_pos": p[5]["pos"]
        })

    return patterns


_original_detect_all_head_shoulders = detect_all_head_shoulders

def _detect_both_head_shoulders(pivots, df):
    normal_patterns = _original_detect_all_head_shoulders(pivots, df)
    inverse_patterns = detect_all_inverse_head_shoulders(pivots, df)
    all_patterns = normal_patterns + inverse_patterns
    all_patterns.sort(key=lambda x: x.get("end_pos", -1))
    return all_patterns

detect_all_head_shoulders = _detect_both_head_shoulders


def run_full_analysis(df):
    if df is None or df.empty:
        return {
            "df": df, "signal": "WAITING", "pattern": "NO PATTERN DETECTED",
            "bias": "Neutral", "entry": None, "sl": None, "tp": None,
            "nodes": [], "neckline_nodes": [], "target_nodes": [], "all_patterns": []
        }

    df = df.copy()
    required = ["Open", "High", "Low", "Close"]
    for col in required:
        if col not in df.columns:
            return {
                "df": df, "signal": "ERROR", "pattern": f"Missing column: {col}",
                "bias": "Neutral", "entry": None, "sl": None, "tp": None,
                "nodes": [], "neckline_nodes": [], "target_nodes": [], "all_patterns": []
            }
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=required)

    if len(df) < 30:
        return {
            "df": df, "signal": "WAITING", "pattern": "NO PATTERN DETECTED",
            "bias": "Neutral", "entry": None, "sl": None, "tp": None,
            "nodes": [], "neckline_nodes": [], "target_nodes": [], "all_patterns": []
        }

    df_active = df.tail(200).copy()
    df_active = calculate_indicators(df_active)
    df_active = calculate_zigzag(df_active)

    pivots = get_chronological_pivots(df_active)
    all_patterns = detect_all_head_shoulders(pivots, df_active)

    if not all_patterns:
        return {
            "df": df, "signal": "WAITING", "pattern": "NO PATTERN DETECTED",
            "bias": "Neutral", "entry": None, "sl": None, "tp": None,
            "nodes": [], "neckline_nodes": [], "target_nodes": [], "all_patterns": []
        }

    latest_pattern = all_patterns[-1]

    return {
        "df": df,
        "signal": "STRONG SELL" if latest_pattern["bias"] == "Bearish" else "STRONG BUY",
        "pattern": latest_pattern["pattern"],
        "bias": latest_pattern["bias"],
        "entry": latest_pattern["entry"],
        "entry_trigger": latest_pattern["entry_trigger"],
        "sl": latest_pattern["sl"],
        "tp": latest_pattern["tp"],
        "nodes": latest_pattern["nodes"],
        "match": latest_pattern["match"],
        "neckline_start_idx": latest_pattern["neckline_start_idx"],
        "all_patterns": all_patterns
    }


def backtest_strategy(df):
    if df is None or df.empty or len(df) < 30:
        return []

    df_calc = df.copy()
    required = ["Open", "High", "Low", "Close"]
    for col in required:
        if col not in df_calc.columns:
            return []
        df_calc[col] = pd.to_numeric(df_calc[col], errors="coerce")
    df_calc = df_calc.dropna(subset=required)

    df_calc = calculate_indicators(df_calc)
    df_calc = calculate_zigzag(df_calc)
    pivots = get_chronological_pivots(df_calc)

    all_patterns = detect_all_head_shoulders(pivots, df_calc)
    if not all_patterns:
        return []

    trades = []
    for pat in all_patterns:
        breakout_idx = pat["nodes"][-1][0]
        entry_price = pat["entry"]
        sl_price = pat["sl"]
        head_tp = pat["tp"]

        if pat["bias"] == "Bearish":
            shoulder_tp = entry_price - (abs(entry_price - head_tp) * 0.5)
        else:
            shoulder_tp = entry_price + (abs(head_tp - entry_price) * 0.5)

        trade_df = df_calc.loc[breakout_idx:]
        head_res, shoulder_res = "LOSS", "LOSS"

        for _, candle in trade_df.iterrows():
            high, low = candle["High"], candle["Low"]

            if pat["bias"] == "Bearish":
                if high >= sl_price:
                    break
                if low <= shoulder_tp and shoulder_res == "LOSS":
                    shoulder_res = "WIN"
                if low <= head_tp:
                    head_res = "WIN"
                    if shoulder_res == "LOSS":
                        shoulder_res = "WIN"
                    break
            else:
                if low <= sl_price:
                    break
                if high >= shoulder_tp and shoulder_res == "LOSS":
                    shoulder_res = "WIN"
                if high >= head_tp:
                    head_res = "WIN"
                    if shoulder_res == "LOSS":
                        shoulder_res = "WIN"
                    break

        trades.append({
            "Pattern": pat["pattern"],
            "Type": pat["bias"],
            "Breakout Date": breakout_idx,
            "Entry Price": round(entry_price, 5),
            "SL": round(sl_price, 5),
            "Head Target": round(head_tp, 5),
            "Shoulder Target": round(shoulder_tp, 5),
            "Head Result": head_res,
            "Shoulder Result": shoulder_res,
            "nodes": pat["nodes"]
        })

    return trades
