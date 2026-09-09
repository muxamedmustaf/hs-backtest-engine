import pandas as pd
import numpy as np

# ==========================================================
# ENGINE.PY - DYNAMIC SWING SCANNER (Full Logic & Backtest)
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

    for i in range(depth, n - backstep):
        high_window = highs[i - depth:i + backstep + 1]
        low_window = lows[i - depth:i + backstep + 1]

        current_high = highs[i]
        current_low = lows[i]

        is_high = (current_high == np.max(high_window) and np.sum(high_window == current_high) == 1)
        is_low = (current_low == np.min(low_window) and np.sum(low_window == current_low) == 1)

        if is_high and not is_low:
            df.iloc[i, df.columns.get_loc("Pivot_H")] = current_high
        elif is_low and not is_high:
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
    def __init__(self, df):
        self.df = df
        self.filters = [
            self.time_filter,
            self.trend_filter,
            self.invalidation_filter,
            self.indicator_confirmation_filter,
            self.breakout_filter
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
            past_min = pre_l0_df["Low"].iloc[-10:].min()
            if past_min > p[0]["val"]:
                return False, None, None
        return True, None, None

    def invalidation_filter(self, p, data):
        h2 = p[3]["val"]
        idx_h2 = p[3]["idx"]
        post_head_df = data.loc[idx_h2:]
        if not post_head_df.empty:
            if post_head_df["High"].max() > h2:
                return False, None, None
        return True, None, None

    def indicator_confirmation_filter(self, p, data):
        idx_h3 = p[5]["idx"]
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
        end_idx = breakout_candles.index[0]
        end_val = breakout_candles["Close"].iloc[0]
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

def detect_all_head_shoulders(pivots, df):
    patterns = []
    if len(pivots) < 6:
        return patterns
    validator = PatternValidatorPipeline(df)
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
        if abs(h1 - h3) > (head_height * 0.35):
            continue
        max_shoulder = max(h1, h3)
        if (h2 - max_shoulder) < (head_height * 0.25):
            continue
        if abs(l1 - l2) > (head_height * 0.25):
            continue

        passed, end_idx, end_val = validator.run(p)
        if not passed:
            continue

        l1_idx, l2_idx = p[2]["idx"], p[4]["idx"]
        neckline_avg = (l1 + l2) / 2.0
        entry = neckline_avg
        sl = h2
        tp = entry - (h2 - neckline_avg)

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

        idx_l3 = p[5]["idx"]
        if idx_l3 not in df.index:
            continue
        rsi_val = df.loc[idx_l3, "RSI"]
        if not (25 <= rsi_val <= 70):
            continue
        ema50 = df.loc[idx_l3, "EMA50"]
        ema200 = df.loc[idx_l3, "EMA200"]
        if pd.isna(ema50) or pd.isna(ema200):
            continue

        h1, h2 = p[2]["val"], p[4]["val"]
        neckline_avg = (h1 + h2) / 2.0
        post_l3_df = df.loc[idx_l3:]
        breakout_candles = post_l3_df[post_l3_df["Close"] > neckline_avg]
        if breakout_candles.empty:
            continue
        end_idx = breakout_candles.index[0]
        end_val = float(breakout_candles["Close"].iloc[0])

        entry = neckline_avg
        sl = l2
        tp = entry + (neckline_avg - l2)

        nodes = [(x["idx"], x["val"]) for x in p]
        nodes.append((end_idx, end_val))

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
            "neckline_start_idx": p[2]["idx"],
            "neckline_end_idx": end_idx,
            "end_pos": p[5]["pos"]
        })
    return patterns

def _detect_both_head_shoulders(pivots, df):
    normal_patterns = detect_all_head_shoulders(pivots, df)
    inverse_patterns = detect_all_inverse_head_shoulders(pivots, df)
    all_patterns = normal_patterns + inverse_patterns
    all_patterns.sort(key=lambda x: x.get("end_pos", -1))
    return all_patterns

detect_all_head_shoulders = _detect_both_head_shoulders

def run_full_analysis(df):
    if df is None or df.empty or len(df) < 30:
        return {
            "df": df, "signal": "WAITING", "pattern": "NO PATTERN DETECTED",
            "bias": "Neutral", "entry": None, "sl": None, "tp": None,
            "nodes": [], "neckline_nodes": [], "target_nodes": [], "all_patterns": []
        }
    df = df.copy()
    for col in ["Open", "High", "Low", "Close"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["Open", "High", "Low", "Close"])

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

    latest = all_patterns[-1]
    signal = "STRONG BUY" if latest["bias"] == "Bullish" else "STRONG SELL"

    return {
        "df": df, "signal": signal, "pattern": latest["pattern"],
        "bias": latest["bias"], "entry": latest["entry"], "sl": latest["sl"],
        "tp": latest["tp"], "nodes": latest["nodes"], "match": latest["match"],
        "neckline_start_idx": latest["neckline_start_idx"], "all_patterns": all_patterns
    }

def backtest_strategy(df):
    trades = []
    if df is None or len(df) < 50:
        return trades

    df_clean = df.copy()
    for col in ["Open", "High", "Low", "Close"]:
        df_clean[col] = pd.to_numeric(df_clean[col], errors="coerce")
    df_clean = df_clean.dropna(subset=["Open", "High", "Low", "Close"])

    df_active = calculate_indicators(df_clean)
    df_active = calculate_zigzag(df_active)
    pivots = get_chronological_pivots(df_active)

    if len(pivots) < 6:
        return trades

    validator = PatternValidatorPipeline(df_active)

    for i in range(len(pivots) - 5):
        p = pivots[i:i + 6]
        is_bullish = ([x["type"] for x in p] == ["H", "L", "H", "L", "H", "L"])
        is_bearish = ([x["type"] for x in p] == ["L", "H", "L", "H", "L", "H"])
        
        if not is_bullish and not is_bearish:
            continue

        passed, end_idx, end_val = validator.run(p)
        if not passed or end_idx not in df_active.index:
            continue

        end_pos = df_active.index.get_loc(end_idx)

        if is_bullish:
            h1, h2 = p[2]["val"], p[4]["val"]
            l2 = p[3]["val"]
            neckline_avg = (h1 + h2) / 2.0
            entry = neckline_avg
            sl = l2
            tp = entry + (neckline_avg - l2)
            bias = "Bullish"
            pattern_name = "Inverse Head and Shoulders"
        else:
            l1, l2 = p[2]["val"], p[4]["val"]
            h2 = p[3]["val"]
            neckline_avg = (l1 + l2) / 2.0
            entry = neckline_avg
            sl = h2
            tp = entry - (h2 - neckline_avg)
            bias = "Bearish"
            pattern_name = "Head and Shoulders"

        result = "OPEN"
        exit_time = None
        
        # تتبع الصفقة حتى آخر شمعة متاحة في البيانات التاريخية (مهما طال الزمن)
        for j in range(end_pos + 1, len(df_active)):
            h = df_active['High'].iloc[j]
            l = df_active['Low'].iloc[j]
            t_idx = df_active.index[j]

            if bias == "Bearish":
                hit_tp = l <= tp
                hit_sl = h >= sl
                if hit_tp and hit_sl:
                    result = "LOSS"
                    exit_time = t_idx
                    break
                elif hit_tp:
                    result = "WIN"
                    exit_time = t_idx
                    break
                elif hit_sl:
                    result = "LOSS"
                    exit_time = t_idx
                    break
            elif bias == "Bullish":
                hit_tp = h >= tp
                hit_sl = l <= sl
                if hit_tp and hit_sl:
                    result = "LOSS"
                    exit_time = t_idx
                    break
                elif hit_tp:
                    result = "WIN"
                    exit_time = t_idx
                    break
                elif hit_sl:
                    result = "LOSS"
                    exit_time = t_idx
                    break

        trades.append({
            "Pattern": pattern_name,
            "Type": bias,
            "Entry Time": end_idx,
            "Entry": float(round(entry, 5)),
            "TP": float(round(tp, 5)),
            "Shoulder SL": float(round(sl, 5)),
            "Result": result,
            "Exit Time": exit_time
        })

    return trades
        
