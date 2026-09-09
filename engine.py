import pandas as pd
import numpy as np

# ==========================================================
# ENGINE.PY - OPTIMIZED HIGH-SPEED BACKTESTER (v5.0)
# ==========================================================

MIN_WAVE_CANDLES = 3


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

    if n < (depth + backstep):
        return df

    for i in range(depth, n - backstep):
        high_window = highs[i - depth:i + backstep + 1]
        low_window = lows[i - depth:i + backstep + 1]

        current_high = highs[i]
        current_low = lows[i]

        if current_high == np.max(high_window) and np.sum(high_window == current_high) == 1:
            df.iloc[i, df.columns.get_loc("Pivot_H")] = current_high
        elif current_low == np.min(low_window) and np.sum(low_window == current_low) == 1:
            df.iloc[i, df.columns.get_loc("Pivot_L")] = current_low

    return df


def get_chronological_pivots(df):
    raw = []
    for pos, (idx, row) in enumerate(df.iterrows()):
        if not pd.isna(row["Pivot_H"]):
            raw.append({"idx": idx, "pos": pos, "val": float(row["Pivot_H"]), "type": "H", "dynamic_swing": float(row.get("Dynamic_Swing", 0.001))})
        elif not pd.isna(row["Pivot_L"]):
            raw.append({"idx": idx, "pos": pos, "val": float(row["Pivot_L"]), "type": "L", "dynamic_swing": float(row.get("Dynamic_Swing", 0.001))})

    if not raw:
        return []

    clean = []
    for p in raw:
        if not clean:
            clean.append(p)
            continue
        last = clean[-1]
        if last["type"] != p["type"]:
            movement = abs(p["val"] - last["val"]) / max(abs(last["val"]), 1e-9)
            if movement >= p["dynamic_swing"]:
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

    return clean


class PatternValidatorPipeline:
    def __init__(self, df):
        self.df = df
        self.filters = [
            self.time_filter, self.trend_filter, self.invalidation_filter,
            self.indicator_confirmation_filter, self.breakout_filter
        ]

    def time_filter(self, p, data):
        i_l0, i_h1, i_l1, i_h2, i_l2, i_h3 = [x["pos"] for x in p]
        if (i_h1 - i_l0 < MIN_WAVE_CANDLES) or \
           (i_l1 - i_h1 < MIN_WAVE_CANDLES) or \
           (i_h2 - i_l1 < MIN_WAVE_CANDLES) or \
           (i_l2 - i_h2 < MIN_WAVE_CANDLES) or \
           (i_h3 - i_l2 < MIN_WAVE_CANDLES):
            return False, None, None
        return True, None, None

    def trend_filter(self, p, data):
        idx_l0 = p[0]["idx"]
        pre_l0_df = data.loc[:idx_l0]
        if len(pre_l0_df) > 10:
            if pre_l0_df["Low"].iloc[-10:].min() > p[0]["val"]:
                return False, None, None
        return True, None, None

    def invalidation_filter(self, p, data):
        h2 = p[3]["val"]
        idx_h2 = p[3]["idx"]
        post_head_df = data.loc[idx_h2:]
        if not post_head_df.empty and post_head_df["High"].max() > h2:
            return False, None, None
        return True, None, None

    def indicator_confirmation_filter(self, p, data):
        idx_h3 = p[5]["idx"]
        if idx_h3 not in data.index:
            return False, None, None
        rsi_val = data.loc[idx_h3, "RSI"]
        if not (30 <= rsi_val <= 75):
            return False, None, None
        ema50 = data.loc[idx_h3, "EMA50"]
        ema200 = data.loc[idx_h3, "EMA200"]
        if pd.isna(ema50) or pd.isna(ema200):
            return False, None, None
        return True, None, None

    def breakout_filter(self, p, data):
        idx_h3 = p[5]["idx"]
        l1, l2 = p[2]["val"], p[4]["val"]
        neckline_avg = (l1 + l2) / 2.0
        post_h3_df = data.loc[idx_h3:]
        breakout_candles = post_h3_df[post_h3_df["Close"] < neckline_avg]
        if breakout_candles.empty:
            return False, None, None
        return True, breakout_candles.index[0], breakout_candles["Close"].iloc[0]

    def run(self, p):
        end_idx, end_val = None, None
        for f in self.filters:
            passed, e_idx, e_val = f(p, self.df)
            if not passed:
                return False, None, None
            if e_idx is not None:
                end_idx, end_val = e_idx, e_val
        return True, end_idx, end_val


def detect_normal_head_shoulders(pivots, df):
    patterns = []
    if len(pivots) < 6:
        return patterns
    validator = PatternValidatorPipeline(df)
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
        if head_height <= 0 or abs(h1 - h3) > (head_height * 0.35):
            continue
        if (h2 - max(h1, h3)) < (head_height * 0.25) or abs(l1 - l2) > (head_height * 0.25):
            continue

        passed, end_idx, end_val = validator.run(p)
        if not passed or (total_candles - df.index.get_loc(end_idx)) > 10:
            continue

        neckline_avg = (l1 + l2) / 2.0
        entry = neckline_avg
        sl = h2
        tp = entry - (h2 - neckline_avg)
        nodes = [(x["idx"], x["val"]) for x in p] + [(end_idx, float(end_val))]

        patterns.append({
            "pattern": "Head and Shoulders", "bias": "Bearish",
            "nodes": nodes, "entry": float(round(entry, 5)),
            "sl": float(round(sl, 5)), "tp": float(round(tp, 5)),
            "end_pos": p[5]["pos"]
        })
    return patterns


def detect_all_inverse_head_shoulders(pivots, df):
    patterns = []
    if len(pivots) < 6:
        return patterns
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
        if head_depth <= 0 or abs(l1 - l3) > (head_depth * 0.35):
            continue
        if (min(l1, l3) - l2) < (head_depth * 0.25) or abs(h1 - h2) > (head_depth * 0.25):
            continue

        positions = [x["pos"] for x in p]
        if any((positions[j+1] - positions[j]) < MIN_WAVE_CANDLES for j in range(5)):
            continue

        idx_l3 = p[5]["idx"]
        if idx_l3 not in df.index:
            continue

        rsi_val = df.loc[idx_l3, "RSI"]
        if not (25 <= rsi_val <= 70):
            continue

        neckline_avg = (h1 + h2) / 2.0
        post_l3_df = df.loc[idx_l3:]
        breakout_candles = post_l3_df[post_l3_df["Close"] > neckline_avg]
        if breakout_candles.empty:
            continue

        end_idx = breakout_candles.index[0]
        end_val = float(breakout_candles["Close"].iloc[0])
        if (total_candles - df.index.get_loc(end_idx)) > 10:
            continue

        entry = neckline_avg
        sl = l2
        tp = entry + (neckline_avg - l2)
        nodes = [(x["idx"], x["val"]) for x in p] + [(end_idx, end_val)]

        patterns.append({
            "pattern": "Inverse Head and Shoulders", "bias": "Bullish",
            "nodes": nodes, "entry": float(round(entry, 5)),
            "sl": float(round(sl, 5)), "tp": float(round(tp, 5)),
            "end_pos": p[5]["pos"]
        })
    return patterns


def detect_all_head_shoulders(pivots, df):
    return detect_normal_head_shoulders(pivots, df) + detect_all_inverse_head_shoulders(pivots, df)


def run_full_analysis(df):
    if df is None or df.empty or len(df) < 30:
        return {"signal": "WAITING", "pattern": "NO PATTERN DETECTED", "bias": "Neutral", "nodes": []}
    
    df = df.copy()
    for col in ["Open", "High", "Low", "Close"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["Open", "High", "Low", "Close"])

    df_active = calculate_indicators(df.tail(200))
    df_active = calculate_zigzag(df_active)
    pivots = get_chronological_pivots(df_active)
    all_patterns = detect_all_head_shoulders(pivots, df_active)

    if not all_patterns:
        return {"signal": "WAITING", "pattern": "NO PATTERN", "bias": "Neutral", "nodes": []}

    latest = all_patterns[-1]
    signal = "STRONG BUY" if latest["bias"] == "Bullish" else "STRONG SELL"
    return {
        "df": df, "signal": signal, "pattern": latest["pattern"], "bias": latest["bias"],
        "entry": latest["entry"], "sl": latest["sl"], "tp": latest["tp"], "nodes": latest["nodes"],
        "all_patterns": all_patterns
    }


def simulate_trade(df_clean, start_idx, bias, entry, tp, sl):
    for j in range(start_idx, min(len(df_clean), start_idx + 40)):
        bar = df_clean.iloc[j]
        h_p, l_p = bar["High"], bar["Low"]
        if bias == "Bullish":
            if l_p <= sl: return "LOSS"
            elif h_p >= tp: return "WIN"
        else:
            if h_p >= sl: return "LOSS"
            elif l_p <= tp: return "WIN"
    return "OPEN"


def backtest_strategy(df):
    trades = []
    if df is None or len(df) < 150:
        return trades

    df_clean = df.copy()
    for col in ["Open", "High", "Low", "Close"]:
        df_clean[col] = pd.to_numeric(df_clean[col], errors="coerce")
    df_clean = df_clean.dropna(subset=["Open", "High", "Low", "Close"])

    # تحسين السرعة القصوى بحساب المؤشرات كاملة مرة واحدة مسبقاً
    df_clean = calculate_indicators(df_clean)

    step = 10  # زيادة خطوة المسح لتسريع التنفيذ الضعف
    start_bar = 100

    for i in range(start_bar, len(df_clean) - 10, step):
        sub_df = df_clean.iloc[:i].copy()
        sub_df = calculate_zigzag(sub_df)
        pivots = get_chronological_pivots(sub_df)
        patterns = detect_all_head_shoulders(pivots, sub_df)

        if patterns:
            latest = patterns[-1]
            signal_time = sub_df.index[-1]
            pat_name = latest["pattern"]

            if any(t["Entry Time"] == signal_time and t["Pattern"] == pat_name for t in trades):
                continue

            bias, entry, tp = latest["bias"], latest["entry"], latest["tp"]
            nodes = latest["nodes"]

            if len(nodes) >= 6:
                val1, val3, val5 = nodes[1][1], nodes[3][1], nodes[5][1]
                if bias == "Bearish":
                    sl_head, sl_shoulder = val3, max(val1, val5)
                else:
                    sl_head, sl_shoulder = val3, min(val1, val5)
            else:
                continue

            res_head = simulate_trade(df_clean, i, bias, entry, tp, sl_head)
            res_shoulder = simulate_trade(df_clean, i, bias, entry, tp, sl_shoulder)

            better_sl = "متطابقان" if res_head == res_shoulder else ("وقف الرأس" if res_head == "WIN" and res_shoulder == "LOSS" else "وقف الكتف")

            trades.append({
                "Entry Time": signal_time, "Pattern": pat_name, "Type": bias,
                "Entry": entry, "TP": tp, "Head SL": sl_head, "Head Result": res_head,
                "Shoulder SL": sl_shoulder, "Shoulder Result": res_shoulder, "Better SL": better_sl
            })

    return trades
        
