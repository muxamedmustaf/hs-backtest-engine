import pandas as pd
import numpy as np

# ==========================================================
# ENGINE.PY - ULTRA-FAST & VECTORIZED SCANNER (v6.0)
# ==========================================================

MIN_WAVE_CANDLES = 3
MIN_PRE_TREND_MOVE = 0.01
MIN_SHOULDER_REACTION = 0.003


def calculate_indicators(df):
    """حساب متجهات المؤشرات الفنية بسرعة عالية جداً"""
    df = df.copy()
    close = df["Close"]
    high = df["High"]
    low = df["Low"]

    # حساب المتوسطات المتحركة الأسية
    df["EMA50"] = close.ewm(span=50, adjust=False).mean()
    df["EMA200"] = close.ewm(span=200, adjust=False).mean()

    # حساب مؤشر القوة النسبية RSI المتجه (Wilder's Smoothing)
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(alpha=1/14, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/14, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0, 1e-9)
    df["RSI"] = (100 - (100 / (1 + rs))).fillna(50.0)

    # حساب مؤشر ATR المتجه
    high_low = high - low
    high_close = (high - close.shift()).abs()
    low_close = (low - close.shift()).abs()
    
    true_range = np.maximum(high_low, np.maximum(high_close, low_close))
    df["ATR"] = true_range.rolling(14).mean()

    df["Dynamic_Swing"] = ((df["ATR"] / close) * 0.5).fillna(0.001)

    return df


def calculate_zigzag(df, depth=12, backstep=6):
    """حساب القمم والقيعان (ZigZag) باستخدام المتجهات السريعة بدلاً من الحلقات التكرارية"""
    df = df.copy()
    w = depth + backstep + 1
    
    # حساب أعلى وأقل قيمة في النافذة بشكل متجه ومزاح للوراء
    roll_max = df["High"].rolling(window=w, min_periods=w).max().shift(-backstep)
    roll_min = df["Low"].rolling(window=w, min_periods=w).min().shift(-backstep)

    is_high = (df["High"] == roll_max)
    is_low = (df["Low"] == roll_min)

    # منع تداخل القمة والقاع في نفس الشمعة
    df["Pivot_H"] = np.where(is_high & (~is_low), df["High"], np.nan)
    df["Pivot_L"] = np.where(is_low & (~is_high), df["Low"], np.nan)

    return df


def get_chronological_pivots(df):
    """استخراج وترشيح النقاط المفصلية بترتيب زمني سريع"""
    # تجميع النقاط غير الفارغة
    h_mask = df["Pivot_H"].notna()
    l_mask = df["Pivot_L"].notna()

    raw = []
    positions = np.where(h_mask | l_mask)[0]
    indices = df.index[positions]
    
    for pos, idx in zip(positions, indices):
        row = df.iloc[pos]
        val_h = row["Pivot_H"]
        
        if not pd.isna(val_h):
            raw.append({
                "idx": idx, "pos": pos, "val": float(val_h), "type": "H",
                "dynamic_swing": float(row["Dynamic_Swing"])
            })
        else:
            raw.append({
                "idx": idx, "pos": pos, "val": float(row["Pivot_L"]), "type": "L",
                "dynamic_swing": float(row["Dynamic_Swing"])
            })

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
                if (last["type"] == "H" and p["val"] > last["val"]) or (last["type"] == "L" and p["val"] < last["val"]):
                    clean[-1] = p
        elif (p["type"] == "H" and p["val"] > last["val"]) or (p["type"] == "L" and p["val"] < last["val"]):
            clean[-1] = p

    final_clean = []
    for p in clean:
        if not final_clean or final_clean[-1]["type"] != p["type"]:
            final_clean.append(p)
        elif (p["type"] == "H" and p["val"] > final_clean[-1]["val"]) or (p["type"] == "L" and p["val"] < final_clean[-1]["val"]):
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
            pre_trend_move = (p[1]["val"] - past_min) / max(abs(past_min), 1e-9)
            if pre_trend_move < MIN_PRE_TREND_MOVE or p[0]["val"] <= past_min:
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
        h2 = p[3]["val"]

        neckline_avg = (l1 + l2) / 2.0
        post_h3_df = data.loc[idx_h3:]

        head_length = h2 - neckline_avg
        tp_level = neckline_avg - head_length

        current_close = float(data["Close"].iloc[-1])
        if current_close >= neckline_avg or current_close <= tp_level:
            return False, None, None

        for idx, row in post_h3_df.iterrows():
            close = float(row["Close"])
            if close <= tp_level:
                return False, None, None
            if close < neckline_avg:
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

    validator = PatternValidatorPipeline(df)
    total_candles = len(df)

    for i in range(len(pivots) - 5):
        p = pivots[i:i + 6]
        if [x["type"] for x in p] != ["L", "H", "L", "H", "L", "H"]:
            continue

        l0, h1, l1, h2, l2, h3 = [x["val"] for x in p]

        if h1 <= l0 or l1 <= l0:
            continue

        left_reaction_up = (h1 - l0) / max(abs(l0), 1e-9)
        left_reaction_down = (h1 - l1) / max(abs(h1), 1e-9)
        if left_reaction_up < MIN_SHOULDER_REACTION or left_reaction_down < MIN_SHOULDER_REACTION:
            continue

        if abs(l1 - l0) / max(abs(l0), 1e-9) > 0.02:
            continue

        right_reaction_up = (h3 - l2) / max(abs(l2), 1e-9)
        if right_reaction_up < MIN_SHOULDER_REACTION or h2 <= h1 or h2 <= h3:
            continue

        # شروط النسبة المئوية 5% الصارمة للرأس والكتفين
        max_shoulder = max(h1, h3)
        if abs(h1 - h3) / max_shoulder > 0.05 or (h2 - max_shoulder) / max_shoulder < 0.05:
            continue

        neckline_min = min(l1, l2)
        head_height = h2 - neckline_min
        if head_height <= 0 or abs(l1 - l2) > (head_height * 0.25):
            continue

        passed, end_idx, end_val = validator.run(p)
        if not passed:
            continue

        end_pos = df.index.get_loc(end_idx)
        if (total_candles - end_pos) > 10:
            continue

        l1_idx, l2_idx = p[2]["idx"], p[4]["idx"]
        neckline_avg = (l1 + l2) / 2.0
        actual_head_length = h2 - neckline_avg

        entry = neckline_avg
        sl = h2
        tp = entry - actual_head_length

        current_close = float(df["Close"].iloc[-1])
        if current_close >= entry or current_close <= tp:
            continue

        nodes = [(x["idx"], x["val"]) for x in p]
        nodes.append((end_idx, float(end_val)))

        patterns.append({
            "name": "Head and Shoulders", "pattern": "Head and Shoulders", "bias": "Bearish",
            "match": 100.0, "nodes": nodes,
            "entry": float(round(entry, 5)), "entry_trigger": float(round(entry, 5)),
            "sl": float(round(sl, 5)), "tp": float(round(tp, 5)),
            "neckline_start_idx": l1_idx, "neckline_end_idx": end_idx,
            "neckline_nodes": [(l1_idx, l1), (l2_idx, l2)],
            "target_nodes": [(end_idx, float(round(entry, 5))), (end_idx, float(round(tp, 5)))],
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

        # شروط النسبة المئوية 5% الصارمة للنمط المقلوب
        min_shoulder = min(l1, l3)
        max_shoulder = max(l1, l3)
        if abs(l1 - l3) / max_shoulder > 0.05 or (min_shoulder - l2) / min_shoulder < 0.05:
            continue

        neckline_max = max(h1, h2)
        head_depth = neckline_max - l2
        if head_depth <= 0 or abs(h1 - h2) > (head_depth * 0.25):
            continue

        positions = [x["pos"] for x in p]
        if any((positions[j+1] - positions[j]) < MIN_WAVE_CANDLES for j in range(5)):
            continue

        idx_h0 = p[0]["idx"]
        pre_left_df = df.loc[:idx_h0]
        if len(pre_left_df) > 10 and pre_left_df["High"].iloc[-10:].max() < p[0]["val"]:
            continue

        idx_l2 = p[3]["idx"]
        post_head_df = df.loc[idx_l2:]
        if not post_head_df.empty and post_head_df["Low"].min() < l2:
            continue

        idx_l3 = p[5]["idx"]
        if idx_l3 not in df.index:
            continue

        rsi_val = df.loc[idx_l3, "RSI"]
        if not (25 <= rsi_val <= 70):
            continue

        h1_idx, h2_idx = p[2]["idx"], p[4]["idx"]
        neckline_avg = (h1 + h2) / 2.0
        post_l3_df = df.loc[idx_l3:]

        head_length = neckline_avg - l2
        tp_level = neckline_avg + head_length

        end_idx, end_val = None, None
        for idx, row in post_l3_df.iterrows():
            close = float(row["Close"])
            if close >= tp_level:
                break
            if close > neckline_avg:
                end_idx, end_val = idx, close
                break

        if end_idx is None or (total_candles - df.index.get_loc(end_idx)) > 10:
            continue

        entry = neckline_avg
        sl = l2
        tp = entry + (neckline_avg - l2)

        current_close = float(df["Close"].iloc[-1])
        if current_close <= entry or current_close >= tp:
            continue

        nodes = [(x["idx"], x["val"]) for x in p]
        nodes.append((end_idx, end_val))

        patterns.append({
            "name": "Inverse Head and Shoulders", "pattern": "Inverse Head and Shoulders", "bias": "Bullish",
            "match": 100.0, "nodes": nodes,
            "entry": float(round(entry, 5)), "entry_trigger": float(round(entry, 5)),
            "sl": float(round(sl, 5)), "tp": float(round(tp, 5)),
            "neckline_start_idx": h1_idx, "neckline_end_idx": end_idx,
            "neckline_nodes": [(h1_idx, h1), (h2_idx, h2)],
            "target_nodes": [(end_idx, float(round(entry, 5))), (end_idx, float(round(tp, 5)))],
            "end_pos": p[5]["pos"]
        })

    return patterns


def _detect_both_head_shoulders(pivots, df):
    normal_patterns = detect_all_head_shoulders(pivots, df)
    inverse_patterns = detect_all_inverse_head_shoulders(pivots, df)
    all_patterns = normal_patterns + inverse_patterns
    all_patterns.sort(key=lambda x: x.get("end_pos", -1))
    return all_patterns


def run_full_analysis(df):
    if df is None or df.empty or len(df) < 30:
        return {
            "df": df, "signal": "WAITING", "pattern": "NO PATTERN DETECTED",
            "bias": "Neutral", "entry": None, "sl": None, "tp": None,
            "nodes": [], "neckline_nodes": [], "target_nodes": [], "all_patterns": []
        }

    df = df.copy()
    required = ["Open", "High", "Low", "Close"]
    for col in required:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=required)

    df_active = df.tail(200).copy()
    df_active = calculate_indicators(df_active)
    df_active = calculate_zigzag(df_active)
    pivots = get_chronological_pivots(df_active)
    all_patterns = _detect_both_head_shoulders(pivots, df_active)

    if not all_patterns:
        return {
            "df": df, "signal": "WAITING", "pattern": "NO PATTERN DETECTED",
            "bias": "Neutral", "entry": None, "sl": None, "tp": None,
            "nodes": [], "neckline_nodes": [], "target_nodes": [], "all_patterns": []
        }

    latest_pattern = all_patterns[-1]
    signal = "STRONG SELL" if latest_pattern["bias"] == "Bearish" else "STRONG BUY"

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


def backtest_strategy(df):
    """دالة الاختبار الرجعي المحسّنة للغاية"""
    trades = []
    if df is None or len(df) < 50:
        return trades

    # تجهيز المؤشرات مرة واحدة للبيانات كاملة لتسريع الأداء
    df_full = calculate_indicators(df)
    window_size = 150
    step = 6  # زيادة خطوة المحاكاة لتسريع الاختبار
    last_detected_key = None

    for end_i in range(window_size, len(df_full), step):
        sub_df = df_full.iloc[:end_i]
        res = run_full_analysis(sub_df)

        signal = res.get("signal")
        if signal in ["STRONG BUY", "STRONG SELL"]:
            nodes = res.get("nodes", [])
            pattern_key = nodes[-1][0] if nodes else sub_df.index[-1]

            if pattern_key == last_detected_key:
                continue

            last_detected_key = pattern_key
            entry, sl, tp = res.get("entry"), res.get("sl"), res.get("tp")

            # فحص النتيجة مستقبلاً
            future_df = df_full.iloc[end_i:]
            head_result = shoulder_result = "WIN"

            for _, row in future_df.iterrows():
                high, low = row["High"], row["Low"]
                if signal == "STRONG BUY":
                    if low <= sl:
                        head_result = shoulder_result = "LOSS"
                        break
                    if high >= tp:
                        break
                elif signal == "STRONG SELL":
                    if high >= sl:
                        head_result = shoulder_result = "LOSS"
                        break
                    if low <= tp:
                        break

            trades.append({
                "Date": str(sub_df.index[-1]),
                "Pattern": res.get("pattern"),
                "Signal": signal,
                "Entry": entry, "SL": sl, "TP": tp,
                "nodes": nodes,
                "Head Result": head_result,
                "Shoulder Result": shoulder_result
            })

    return trades
        
