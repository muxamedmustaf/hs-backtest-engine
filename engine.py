import pandas as pd
from engine import (
    calculate_indicators,
    calculate_zigzag,
    get_chronological_pivots,
    PatternValidatorPipeline
)

def backtest_strategy(df):
    trades = []
    if df is None or len(df) < 50:
        return trades

    df_clean = df.copy()
    required = ["Open", "High", "Low", "Close"]
    for col in required:
        df_clean[col] = pd.to_numeric(df_clean[col], errors="coerce")
    df_clean = df_clean.dropna(subset=required)

    # تطبيق المؤشرات والزิกزاج بنفس منطق المحرك الأصلي
    df_active = calculate_indicators(df_clean)
    df_active = calculate_zigzag(df_active)
    pivots = get_chronological_pivots(df_active)

    if len(pivots) < 6:
        return trades

    validator = PatternValidatorPipeline(df_active)

    # فحص جميع النماذج التاريخية باستخدام خطوط التحقق الأصلية دون قيد الـ 10 شمعات
    for i in range(len(pivots) - 5):
        p = pivots[i:i + 6]
        
        is_bullish = ([x["type"] for x in p] == ["H", "L", "H", "L", "H", "L"])
        is_bearish = ([x["type"] for x in p] == ["L", "H", "L", "H", "L", "H"])
        
        if not is_bullish and not is_bearish:
            continue

        # تشغيل نفس الـ Pipeline الأصلي (فحص الـ RSI، الـ EMA، وأبعاد الكتفين والرأس)
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

        # تتبع الصفقة شمعة بشمعة حتى نهاية التاريخ المتاح (حتى لو استغرق ضرب الهدف شهوراً أو سنة)
        result = "OPEN"
        exit_time = None
        
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
    
