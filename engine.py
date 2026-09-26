# -*- coding: utf-8 -*-
import pandas as pd
import numpy as np

# ==========================================================
# ENGINE.PY - DYNAMIC SWING SCANNER & TRUE BACKTEST LAB (v4.7)
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
            movement = abs(p["val"] - last["val"]) / max(
                abs(last["val"]), 1e-9
            )

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
        i_l0, i_h1, i_l1, i_h2, i_l2, i_h3 = [
            x["pos"] for x in p
        ]

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
        return True, None, None

    def breakout_filter(self, p, data):
        idx_h3 = p[5]["idx"]
        l1_val, l2_val = p[2]["val"], p[4]["val"]
        idx_l1, idx_l2 = p[2]["pos"], p[4]["pos"]
        
        if idx_l1 == idx_l2:
            return False, None, None
            
        slope = (l2_val - l1_val) / (idx_l2 - idx_l1)

        post_h3_df = data.loc[idx_h3:]
        
        if len(post_h3_df) <= 1:
            return False, None, None

        for current_idx, row in post_h3_df.iloc[1:].iterrows():
            current_pos = data.index.get_loc(current_idx)
            current_neckline = l2_val + slope * (current_pos - idx_l2)
            close_price = row["Close"]

            if close_price < current_neckline:
                rsi_val = row["RSI"]
                ema50 = row["EMA50"]
                ema200 = row["EMA200"]

                if (30 <= rsi_val <= 75) and (ema50 > ema200):
                    return True, current_idx, close_price
                else:
                    return False, None, None

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


def _detect_all_head_shoulders_base(pivots, df, max_candles_ago=None):
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

        passed, end_idx, end_val = validator.run(p)

        if not passed:
            continue

        end_pos = df.index.get_loc(end_idx)

        # عدم تقييد الأنماط عند الاختبار الرجعي
        if max_candles_ago is not None and (total_candles - end_pos) > max_candles_ago:
            continue

        l1_idx, l2_idx = p[2]["idx"], p[4]["idx"]
        slope = (l2 - l1) / (p[4]["pos"] - p[2]["pos"])
        breakout_neckline_price = l2 + slope * (end_pos - p[4]["pos"])

        actual_head_length = h2 - breakout_neckline_price

        entry = float(end_val)
        sl = h2
        tp = entry - actual_head_length

        nodes = [(x["idx"], x["val"]) for x in p]
        nodes.append((end_idx, float(end_val)))

        neckline_nodes = [(l1_idx, l1), (l2_idx, l2)]

        target_nodes = [
            (end_idx, float(round(entry, 5))),
            (end_idx, float(round(tp, 5)))
        ]

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
            "neckline_nodes": neckline_nodes,
            "target_nodes": target_nodes,
            "end_pos": p[5]["pos"]
        })

    return patterns


def detect_all_inverse_head_shoulders(pivots, df, max_candles_ago=None):
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

        if head_depth <= 0:
            continue

        if abs(l1 - l3) > (head_depth * 0.35):
            continue

        min_shoulder = min(l1, l3)

        if (min_shoulder - l2) < (head_depth * 0.25):
            continue

        if abs(h1 - h2) > (head_depth * 0.25):
            continue

        positions = [x["pos"] for x in p]

        if any((positions[j] - positions[j-1]) < MIN_WAVE_CANDLES for j in range(1, 6)):
            continue

        idx_l3 = p[5]["idx"]

        if idx_l3 not in df.index:
            continue

        post_l3_df = df.loc[idx_l3:]

        if len(post_l3_df) <= 1:
            continue

        h1_idx, h2_idx = p[2]["idx"], p[4]["idx"]
        pos_h1, pos_h2 = p[2]["pos"], p[4]["pos"]
        
        if pos_h1 == pos_h2:
            continue

        slope = (h2 - h1) / (pos_h2 - pos_h1)

        breakout_confirmed = False
        end_idx = None
        end_val = None
        breakout_neckline_price = None

        for current_idx, row in post_l3_df.iloc[1:].iterrows():
            current_pos = df.index.get_loc(current_idx)
            current_neckline = h2 + slope * (current_pos - pos_h2)
            close_price = row["Close"]

            if close_price > current_neckline:
                rsi_val = row["RSI"]
                ema50 = row["EMA50"]
                ema200 = row["EMA200"]

                if (30 <= rsi_val <= 75) and (ema50 < ema200):
                    breakout_confirmed = True
                    end_idx = current_idx
                    end_val = close_price
                    breakout_neckline_price = current_neckline
                break

        if not breakout_confirmed:
            continue

        end_pos = df.index.get_loc(end_idx)

        if max_candles_ago is not None and (total_candles - end_pos) > max_candles_ago:
            continue

        entry = float(end_val)
        sl = l2
        actual_head_length = breakout_neckline_price - l2
        tp = entry + actual_head_length

        nodes = [(x["idx"], x["val"]) for x in p]
        nodes.append((end_idx, end_val))

        neckline_nodes = [(h1_idx, h1), (h2_idx, h2)]

        target_nodes = [
            (end_idx, float(round(entry, 5))),
            (end_idx, float(round(tp, 5)))
        ]

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
            "neckline_nodes": neckline_nodes,
            "target_nodes": target_nodes,
            "end_pos": p[5]["pos"]
        })

    return patterns


def detect_all_head_shoulders(pivots, df, max_candles_ago=None):
    normal_patterns = _detect_all_head_shoulders_base(pivots, df, max_candles_ago=max_candles_ago)
    inverse_patterns = detect_all_inverse_head_shoulders(pivots, df, max_candles_ago=max_candles_ago)

    all_patterns = normal_patterns + inverse_patterns
    all_patterns.sort(key=lambda x: x.get("end_pos", -1))
    return all_patterns


def run_full_analysis(df, interval="1d"):
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
            raise ValueError(f"Missing required column: {col}")
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=required)

    if len(df) < 30:
        return {
            "df": df, "signal": "WAITING", "pattern": "NO PATTERN DETECTED",
            "bias": "Neutral", "entry": None, "sl": None, "tp": None,
            "nodes": [], "neckline_nodes": [], "target_nodes": [], "all_patterns": []
        }

    # للماسح الحي: نأخذ أحدث 300 شمعة
    df_active = df.tail(300).copy()
    df_active = calculate_indicators(df_active)
    df_active = calculate_zigzag(df_active)

    pivots = get_chronological_pivots(df_active)
    all_patterns = detect_all_head_shoulders(pivots, df_active, max_candles_ago=150)

    if not all_patterns:
        return {
            "df": df_active, "signal": "WAITING", "pattern": "NO PATTERN DETECTED",
            "bias": "Neutral", "entry": None, "sl": None, "tp": None,
            "nodes": [], "neckline_nodes": [], "target_nodes": [], "all_patterns": []
        }

    latest_pattern = all_patterns[-1]
    signal = "STRONG BUY" if latest_pattern["bias"] == "Bullish" else "STRONG SELL"

    return {
        "df": df_active,
        "signal": signal,
        "pattern": latest_pattern["pattern"],
        "bias": latest_pattern["bias"],
        "entry": latest_pattern["entry"],
        "entry_trigger": latest_pattern["entry_trigger"],
        "sl": latest_pattern["sl"],
        "tp": latest_pattern["tp"],
        "nodes": latest_pattern["nodes"],
        "match": latest_pattern["match"],
        "neckline_start_idx": latest_pattern["neckline_start_idx"],
        "neckline_nodes": latest_pattern.get("neckline_nodes", []),
        "target_nodes": latest_pattern.get("target_nodes", []),
        "all_patterns": all_patterns
    }


# دالة الاختبار الرجعي الشاملة والتاريخية الحقيقية (True Backtest)
def backtest_strategy(df, interval="1d"):
    if df is None or len(df) < 50:
        return []

    # معالجة كامل السلسلة الزمنية التاريخية
    df_calc = calculate_indicators(df)
    df_calc = calculate_zigzag(df_calc)
    pivots = get_chronological_pivots(df_calc)
    
    # جلب كافة الأنماط التاريخية بدون تقييد زمني
    patterns = detect_all_head_shoulders(pivots, df_calc, max_candles_ago=None)

    trades = []
    for pat in patterns:
        entry = pat["entry"]
        sl = pat["sl"]
        tp = pat["tp"]
        bias = pat["bias"]
        end_idx = pat["neckline_end_idx"]

        try:
            sub_df = df_calc.loc[end_idx:]
            if len(sub_df) <= 1:
                continue
            
            head_result = "PENDING"
            exit_date = None
            exit_price = None

            # محاكاة حركة السعر شمعة بشمعة بعد الاختراق
            for current_idx, row in sub_df.iloc[1:].iterrows():
                high_p = row["High"]
                low_p = row["Low"]

                if bias == "Bearish": # صفقة بيع (Head and Shoulders)
                    if high_p >= sl:
                        head_result = "LOSS"
                        exit_date = current_idx
                        exit_price = sl
                        break
                    elif low_p <= tp:
                        head_result = "WIN"
                        exit_date = current_idx
                        exit_price = tp
                        break
                else: # صفقة شراء (Inverse Head and Shoulders)
                    if low_p <= sl:
                        head_result = "LOSS"
                        exit_date = current_idx
                        exit_price = sl
                        break
                    elif high_p >= tp:
                        head_result = "WIN"
                        exit_date = current_idx
                        exit_price = tp
                        break

            if head_result == "PENDING":
                head_result = "OPEN"
                exit_date = sub_df.index[-1]
                exit_price = sub_df["Close"].iloc[-1]

            entry_cond = f"{pat['pattern']} ({'كسر هبوطي' if bias == 'Bearish' else 'اختراق صعودي'}) + تأكيد EMA/RSI"

            trades.append({
                "Pattern": pat["pattern"],
                "Bias": bias,
                "Entry Date": str(end_idx),
                "Exit Date": str(exit_date),
                "Entry Price": entry,
                "Exit Price": float(round(exit_price, 5)) if exit_price else entry,
                "Stop Loss": sl,
                "Take Profit": tp,
                "Result": head_result,
                "Head Result": head_result,
                "Shoulder Result": head_result,
                "Entry Conditions": entry_cond,
                "nodes": pat["nodes"],
                "neckline_nodes": pat["neckline_nodes"]
            })
        except Exception:
            continue

    return trades


if __name__ == "__main__":
    print("ENGINE.PY loaded with True Backtest Lab & Live Scanner (v4.7).")
        
