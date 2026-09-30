# -*- coding: utf-8 -*-
"""
ENGINE.PY - Head & Shoulders Pattern Detector
Unified Live + Backtest Engine
"""
import pandas as pd
import numpy as np

# ==============================================================================
# [1] الإعدادات المركزية
# ==============================================================================
CONFIG = {
    "ZIGZAG_DEPTH": 12,
    "ZIGZAG_BACKSTEP": 6,
    "MIN_WAVE_CANDLES": 3,
    "SHOULDER_DIFF_MAX_RATIO": 0.35,
    "HEAD_PROPORTION_MIN_RATIO": 0.25,
    "NECKLINE_DIFF_MAX_RATIO": 0.25,
    "LIVE_MAX_BREAKOUT_CANDLES": 30,
    "RSI_MIN_BEARISH": 30.0,
    "RSI_MAX_BEARISH": 75.0,
    "RSI_MIN_BULLISH": 25.0,
    "RSI_MAX_BULLISH": 70.0,
    "EMA_FAST_SPAN": 50,
    "EMA_SLOW_SPAN": 200,
}

# ==============================================================================
# [2] حساب المؤشرات الفنية
# ==============================================================================
def calculate_indicators(df):
    """حساب EMA50, EMA200, RSI, ATR, Dynamic_Swing"""
    df = df.copy()
    df["EMA50"] = df["Close"].ewm(span=50, adjust=False).mean()
    df["EMA200"] = df["Close"].ewm(span=200, adjust=False).mean()

    # RSI (Wilder's smoothing)
    delta = df["Close"].diff()
    gain = delta.where(delta > 0, 0.0).ewm(alpha=1/14, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0.0)).ewm(alpha=1/14, adjust=False).mean()
    loss_safe = loss.replace(0, 1e-9)
    rs = gain / loss_safe
    df["RSI"] = 100 - (100 / (1 + rs))
    df["RSI"] = df["RSI"].fillna(50.0)

    # ATR
    high_low = df["High"] - df["Low"]
    high_close = np.abs(df["High"] - df["Close"].shift())
    low_close = np.abs(df["Low"] - df["Close"].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = ranges.max(axis=1)
    df["ATR"] = true_range.rolling(14).mean()

    df["Dynamic_Swing"] = (df["ATR"] / df["Close"]) * 0.5
    df["Dynamic_Swing"] = df["Dynamic_Swing"].fillna(0.001)

    return df


# ==============================================================================
# [3] ZigZag
# ==============================================================================
def calculate_zigzag(df, depth=12, backstep=6):
    """تحديد قمم وقيعان ZigZag"""
    df = df.copy()
    df["Pivot_H"] = np.nan
    df["Pivot_L"] = np.nan

    highs = df["High"].astype(float).values
    lows = df["Low"].astype(float).values
    n = len(df)

    if n < depth + backstep + 1:
        return df

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


# ==============================================================================
# [4] تنقية النقاط الزمنية
# ==============================================================================
def get_chronological_pivots(df):
    """تنقية وترتيب نقاط ZigZag زمنياً"""
    raw = []

    for pos, (idx, row) in enumerate(df.iterrows()):
        if not pd.isna(row["Pivot_H"]):
            raw.append({
                "idx": idx, "pos": pos,
                "val": float(row["Pivot_H"]),
                "type": "H",
                "dynamic_swing": float(row.get("Dynamic_Swing", 0.001))
            })
        elif not pd.isna(row["Pivot_L"]):
            raw.append({
                "idx": idx, "pos": pos,
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
# [5] محاكاة نتيجة الصفقة
# ==============================================================================
def simulate_trade_outcome(pattern, df):
    """محاكاة نتيجة الصفقة بعد الكسر - الوقف والهدف حسب طول الرأس"""
    bias = pattern["bias"]
    entry = float(pattern["entry"])
    sl = float(pattern["sl"])
    tp = float(pattern["tp"])
    end_idx = pattern["neckline_end_idx"]

    stats = {
        "Result": "OPEN",
        "Head Result": "OPEN",
        "progress_ratio": 0.0,
        "candles_to_exit": 0,
        "exit_idx": None,
        "exit_price": None,
        "Entry Date": None,
        "Exit Date": None,
        "Max Reach %": 0.0,
        "SL Safety %": 0.0,
    }

    if end_idx not in df.index:
        return stats

    post_df = df.loc[end_idx:]
    if len(post_df) <= 1:
        return stats

    # تاريخ الدخول
    stats["Entry Date"] = str(end_idx)

    total_tp_dist = abs(tp - entry)
    total_sl_dist = abs(sl - entry)
    max_favorable = 0.0   # أقصى وصول للهدف
    max_adverse = 0.0     # أقصى ابتعاد عن SL

    for candle_count, (idx, row) in enumerate(post_df.iloc[1:].iterrows(), start=1):
        high = float(row["High"])
        low = float(row["Low"])

        # تتبع Max Reach و SL Safety
        if bias == "Bearish":
            favorable = max(0.0, entry - low)   # انخفاض = ربح
            adverse = max(0.0, high - entry)    # ارتفاع = خطر
        else:
            favorable = max(0.0, high - entry)  # ارتفاع = ربح
            adverse = max(0.0, entry - low)     # انخفاض = خطر

        if total_tp_dist > 0:
            max_favorable = max(max_favorable, favorable / total_tp_dist * 100)
        if total_sl_dist > 0:
            max_adverse = max(max_adverse, adverse / total_sl_dist * 100)

        if bias == "Bearish":
            hit_sl = high >= sl
            hit_tp = low <= tp
        else:
            hit_sl = low <= sl
            hit_tp = high >= tp

        # أولوية SL (تحفظي)
        if hit_sl and hit_tp:
            stats["Result"] = "LOSS"
            stats["Head Result"] = "LOSS"
            stats["exit_idx"] = idx
            stats["exit_price"] = sl
            stats["candles_to_exit"] = candle_count
            stats["Exit Date"] = str(idx)
            break
        elif hit_sl:
            stats["Result"] = "LOSS"
            stats["Head Result"] = "LOSS"
            stats["exit_idx"] = idx
            stats["exit_price"] = sl
            stats["candles_to_exit"] = candle_count
            stats["Exit Date"] = str(idx)
            break
        elif hit_tp:
            stats["Result"] = "WIN"
            stats["Head Result"] = "WIN"
            stats["exit_idx"] = idx
            stats["exit_price"] = tp
            stats["candles_to_exit"] = candle_count
            stats["Exit Date"] = str(idx)
            break
    else:
        # لم يضرب أي منهما
        stats["candles_to_exit"] = max(0, len(post_df) - 1)
        stats["Exit Date"] = str(df.index[-1])

    stats["Max Reach %"] = round(max_favorable, 1)
    stats["SL Safety %"] = round(100 - max_adverse, 1) if max_adverse <= 100 else 0.0

    # progress_ratio
    if stats["Result"] == "WIN":
        stats["progress_ratio"] = 100.0
    elif stats["Result"] == "LOSS":
        stats["progress_ratio"] = 0.0
    else:
        latest_close = float(df["Close"].iloc[-1])
        if bias == "Bearish":
            moved = max(0.0, entry - latest_close) if latest_close < entry else 0.0
        else:
            moved = max(0.0, latest_close - entry) if latest_close > entry else 0.0
        if total_tp_dist > 0:
            stats["progress_ratio"] = round(moved / total_tp_dist * 100, 2)

    return stats


# ==============================================================================
# [6] فلاتر النمط
# ==============================================================================
class PatternValidatorPipeline:
    """فلاتر التحقق من صحة النمط"""

    def __init__(self, df):
        self.df = df

    def time_filter(self, p):
        positions = [x["pos"] for x in p]
        for j in range(len(positions) - 1):
            if positions[j + 1] - positions[j] < CONFIG["MIN_WAVE_CANDLES"]:
                return False
        return True

    def invalidation_filter(self, p):
        """الرأس يجب أن يكون أعلى قمة في النمط (لا توجد قمة أعلى منه)"""
        h2 = p[3]["val"]
        idx_h2 = p[3]["idx"]

        post_head = self.df.loc[idx_h2:]
        if not post_head.empty and post_head["High"].max() > h2:
            return False
        return True

    def indicator_filter(self, p):
        """RSI في نطاق معقول عند الكتف الأيمن"""
        idx_h3 = p[5]["idx"]
        if idx_h3 not in self.df.index:
            return False
        rsi_val = float(self.df.loc[idx_h3, "RSI"])
        return CONFIG["RSI_MIN_BEARISH"] <= rsi_val <= CONFIG["RSI_MAX_BEARISH"]

    def breakout_filter(self, p):
        """البحث عن كسر خط العنق"""
        idx_h3 = p[5]["idx"]
        l1, l2 = p[2]["val"], p[4]["val"]
        neckline = (l1 + l2) / 2.0

        post_h3 = self.df.loc[idx_h3:]
        breakout = post_h3[post_h3["Close"] < neckline]

        if breakout.empty:
            return None
        return breakout.index[0], float(breakout["Close"].iloc[0])

    def run(self, p):
        if not self.time_filter(p):
            return False, None, None
        if not self.invalidation_filter(p):
            return False, None, None
        if not self.indicator_filter(p):
            return False, None, None

        result = self.breakout_filter(p)
        if result is None:
            return False, None, None

        return True, result[0], result[1]


# ==============================================================================
# [7] كشف النمط الهابط (H&S)
# ==============================================================================
def detect_head_shoulders_bearish(pivots, df, is_backtest=False):
    """كشف نمط الرأس والكتفين الهابط"""
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

        # شروط أساسية
        if h1 <= l0 or l1 <= l0 or h2 <= h1 or h2 <= h3:
            continue

        neckline_min = min(l1, l2)
        head_height = h2 - neckline_min
        if head_height <= 0:
            continue

        # تناسق الكتفين
        if abs(h1 - h3) > head_height * CONFIG["SHOULDER_DIFF_MAX_RATIO"]:
            continue

        # بروز الرأس
        max_shoulder = max(h1, h3)
        if (h2 - max_shoulder) < head_height * CONFIG["HEAD_PROPORTION_MIN_RATIO"]:
            continue

        # استواء خط العنق
        if abs(l1 - l2) > head_height * CONFIG["NECKLINE_DIFF_MAX_RATIO"]:
            continue

        # الفلاتر
        passed, end_idx, end_val = validator.run(p)
        if not passed:
            continue

        if end_idx not in df.index:
            continue

        end_pos = df.index.get_loc(end_idx)

        # في الوضع الحي: نقبل فقط الكسر الحديث
        if not is_backtest:
            if (total_candles - end_pos) > CONFIG["LIVE_MAX_BREAKOUT_CANDLES"]:
                continue

        # الحسابات
        l1_idx, l2_idx = p[2]["idx"], p[4]["idx"]
        neckline_avg = (l1 + l2) / 2.0
        actual_head_length = h2 - neckline_avg

        entry = neckline_avg
        sl = h2                                    # SL عند قمة الرأس
        tp = entry - actual_head_length            # TP بمسافة طول الرأس

        nodes = [(x["idx"], x["val"]) for x in p]
        nodes.append((end_idx, float(end_val)))

        neckline_nodes = [(l1_idx, l1), (l2_idx, l2)]
        target_nodes = [
            (end_idx, float(round(entry, 5))),
            (end_idx, float(round(tp, 5)))
        ]

        pattern = {
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
            "end_pos": p[5]["pos"],
            "SL": float(round(sl, 5)),
            "TP": float(round(tp, 5)),
            "Entry": float(round(entry, 5)),
            "Pattern": "Head and Shoulders",
            "pattern": "Head and Shoulders",
            "Entry Conditions": "Breakout + RSI + Head Structure",
        }

        # محاكاة النتيجة
        sim = simulate_trade_outcome(pattern, df)
        pattern.update(sim)

        patterns.append(pattern)

    return patterns


# ==============================================================================
# [8] كشف النمط الصاعد (Inverse H&S)
# ==============================================================================
def detect_head_shoulders_bullish(pivots, df, is_backtest=False):
    """كشف نمط الرأس والكتفين المعكوس (صاعد)"""
    patterns = []
    if len(pivots) < 6:
        return patterns

    total_candles = len(df)

    for i in range(len(pivots) - 5):
        p = pivots[i:i + 6]

        if [x["type"] for x in p] != ["H", "L", "H", "L", "H", "L"]:
            continue

        h0, l1, h1, l2, h2, l3 = [x["val"] for x in p]

        # شروط أساسية
        if l2 >= l1 or l2 >= l3 or l1 >= h1 or l3 >= h2:
            continue

        neckline_max = max(h1, h2)
        head_depth = neckline_max - l2
        if head_depth <= 0:
            continue

        # تناسق الكتفين
        if abs(l1 - l3) > head_depth * CONFIG["SHOULDER_DIFF_MAX_RATIO"]:
            continue

        # بروز الرأس
        min_shoulder = min(l1, l3)
        if (min_shoulder - l2) < head_depth * CONFIG["HEAD_PROPORTION_MIN_RATIO"]:
            continue

        # استواء خط العنق
        if abs(h1 - h2) > head_depth * CONFIG["NECKLINE_DIFF_MAX_RATIO"]:
            continue

        # فحص زمني
        positions = [x["pos"] for x in p]
        if any(positions[j+1] - positions[j] < CONFIG["MIN_WAVE_CANDLES"]
               for j in range(len(positions) - 1)):
            continue

        # invalidation: الرأس يجب أن يكون أدنى قاع
        idx_l2 = p[3]["idx"]
        post_head = df.loc[idx_l2:]
        if not post_head.empty and post_head["Low"].min() < l2:
            continue

        # RSI
        idx_l3 = p[5]["idx"]
        if idx_l3 not in df.index:
            continue
        rsi_val = float(df.loc[idx_l3, "RSI"])
        if not (CONFIG["RSI_MIN_BULLISH"] <= rsi_val <= CONFIG["RSI_MAX_BULLISH"]):
            continue

        # كسر خط العنق لأعلى
        h1_idx, h2_idx = p[2]["idx"], p[4]["idx"]
        neckline_avg = (h1 + h2) / 2.0

        post_l3 = df.loc[idx_l3:]
        breakout = post_l3[post_l3["Close"] > neckline_avg]
        if breakout.empty:
            continue

        end_idx = breakout.index[0]
        end_val = float(breakout["Close"].iloc[0])
        end_pos = df.index.get_loc(end_idx)

        if not is_backtest:
            if (total_candles - end_pos) > CONFIG["LIVE_MAX_BREAKOUT_CANDLES"]:
                continue

        # الحسابات - الوقف والهدف حسب طول الرأس
        actual_head_length = neckline_avg - l2
        entry = neckline_avg
        sl = l2                                    # SL عند قاع الرأس
        tp = entry + actual_head_length            # TP بمسافة طول الرأس

        nodes = [(x["idx"], x["val"]) for x in p]
        nodes.append((end_idx, end_val))

        neckline_nodes = [(h1_idx, h1), (h2_idx, h2)]
        target_nodes = [
            (end_idx, float(round(entry, 5))),
            (end_idx, float(round(tp, 5)))
        ]

        pattern = {
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
            "end_pos": p[5]["pos"],
            "SL": float(round(sl, 5)),
            "TP": float(round(tp, 5)),
            "Entry": float(round(entry, 5)),
            "Pattern": "Inverse Head and Shoulders",
            "pattern": "Inverse Head and Shoulders",
            "Entry Conditions": "Breakout + RSI + Inverse Head Structure",
        }

        sim = simulate_trade_outcome(pattern, df)
        pattern.update(sim)

        patterns.append(pattern)

    return patterns


# ==============================================================================
# [9] دالة الكشف الموحدة
# ==============================================================================
def detect_all_head_shoulders(pivots, df, is_backtest=False):
    """كشف كلا الاتجاهين وترتيبهم زمنياً"""
    bearish = detect_head_shoulders_bearish(pivots, df, is_backtest)
    bullish = detect_head_shoulders_bullish(pivots, df, is_backtest)

    all_patterns = bearish + bullish
    all_patterns.sort(key=lambda x: x.get("end_pos", -1))
    return all_patterns


# ==============================================================================
# [10] التحليل الحي (Live Analysis)
# ==============================================================================
def run_full_analysis(df, interval="1h", symbol=None):
    """التحليل الحي - متوافق مع backtest.py"""
    default_empty = {
        "df": df,
        "symbol": symbol or "N/A",
        "signal": "WAITING",
        "pattern": "NO PATTERN DETECTED",
        "bias": "Neutral",
        "entry": None, "sl": None, "tp": None,
        "nodes": [], "pattern_nodes": [],
        "all_patterns": [],
        "error": None,
    }

    if df is None or df.empty:
        return default_empty

    df = df.copy()

    # تأكد من الأعمدة
    required = ["Open", "High", "Low", "Close"]
    for col in required:
        if col not in df.columns:
            default_empty["error"] = f"Missing column: {col}"
            return default_empty
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=required)

    if len(df) < 30:
        default_empty["error"] = f"Insufficient data: {len(df)} candles"
        return default_empty

    # نافذة التحليل الحي - آخر 500 شمعة
    df_active = df.tail(500).copy()
    df_active = calculate_indicators(df_active)
    df_active = calculate_zigzag(df_active, CONFIG["ZIGZAG_DEPTH"], CONFIG["ZIGZAG_BACKSTEP"])

    pivots = get_chronological_pivots(df_active)
    all_patterns = detect_all_head_shoulders(pivots, df_active, is_backtest=False)

    if not all_patterns:
        default_empty["df"] = df_active
        return default_empty

    latest = all_patterns[-1]
    signal = "STRONG BUY" if latest["bias"] == "Bullish" else "STRONG SELL"

    return {
        "df": df_active,
        "symbol": symbol or "N/A",
        "signal": signal,
        "pattern": latest["pattern"],
        "bias": latest["bias"],
        "entry": latest["entry"],
        "entry_trigger": latest["entry_trigger"],
        "sl": latest["sl"],
        "tp": latest["tp"],
        "nodes": latest["nodes"],
        "pattern_nodes": latest["nodes"],
        "neckline_nodes": latest.get("neckline_nodes", []),
        "target_nodes": latest.get("target_nodes", []),
        "all_patterns": all_patterns,
        "match": latest.get("match", 100.0),
        "Result": latest.get("Result", "OPEN"),
        "Entry Date": latest.get("Entry Date"),
        "Exit Date": latest.get("Exit Date"),
        "error": None,
    }


# ==============================================================================
# [11] الباكتيست الرجعي (Backtest)
# ==============================================================================
def backtest_strategy(df, interval="1h", symbol=None):
    """الباكتيست الرجعي - متوافق مع backtest.py"""
    if df is None or df.empty or len(df) < 30:
        return []

    df = df.copy()

    required = ["Open", "High", "Low", "Close"]
    for col in required:
        if col not in df.columns:
            return []
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=required)

    if len(df) < 30:
        return []

    # الباكتيست: نستخدم كل البيانات
    df = calculate_indicators(df)
    df = calculate_zigzag(df, CONFIG["ZIGZAG_DEPTH"], CONFIG["ZIGZAG_BACKSTEP"])

    pivots = get_chronological_pivots(df)
    all_patterns = detect_all_head_shoulders(pivots, df, is_backtest=True)

    # تحويل إلى قائمة صفقات متوافقة مع الواجهة
    trades = []
    for p in all_patterns:
        trade = {
            "Symbol": symbol or "N/A",
            "Pattern": p["pattern"],
            "pattern": p["pattern"],
            "Bias": p["bias"],
            "Result": p.get("Result", "OPEN"),
            "Head Result": p.get("Head Result", "OPEN"),
            "Entry": p["entry"],
            "SL": p["sl"],
            "TP": p["tp"],
            "Entry Date": p.get("Entry Date"),
            "Exit Date": p.get("Exit Date"),
            "time": p.get("Entry Date"),
            "close_time": p.get("Exit Date"),
            "Max Reach %": p.get("Max Reach %", 0.0),
            "SL Safety %": p.get("SL Safety %", 0.0),
            "Entry Conditions": p.get("Entry Conditions", ""),
            "nodes": p["nodes"],
            "candles_to_exit": p.get("candles_to_exit", 0),
            "progress_ratio": p.get("progress_ratio", 0.0),
            "neckline_end_idx": p["neckline_end_idx"],
        }
        trades.append(trade)

    return trades


# ==============================================================================
# [12] منفذ الاختبار المباشر
# ==============================================================================
if __name__ == "__main__":
    print("ENGINE.PY - Head & Shoulders Detector")
    print("Functions: run_full_analysis(), backtest_strategy()")
