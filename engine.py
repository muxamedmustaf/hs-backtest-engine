import pandas as pd
from engine import (
    calculate_indicators,
    calculate_zigzag,
    get_chronological_pivots,
    detect_all_head_shoulders
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

    # تطبيق نفس عمليات المحرك الحقيقي من engine.txt بالترتيب
    df_active = calculate_indicators(df_clean)
    df_active = calculate_zigzag(df_active)
    pivots = get_chronological_pivots(df_active)
    
    # استخراج كافة النماذج التاريخية التي اجتازت كافة شروط وفلاتر engine.txt
    patterns = detect_all_head_shoulders(pivots, df_active)

    for pat in patterns:
        bias = pat["bias"]
        entry = pat["entry"]
        tp = pat["tp"]
        sl = pat["sl"]
        end_idx = pat["neckline_end_idx"]
        
        if end_idx not in df_active.index:
            continue
            
        end_pos = df_active.index.get_loc(end_idx)
        
        result = "OPEN"
        exit_time = None
        
        # محاكاة حركة السعر بدقة بعد شمعة الاختراق باستخدام High و Low
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
            "Pattern": pat["pattern"],
            "Type": bias,
            "Entry Time": end_idx,
            "Entry": entry,
            "TP": tp,
            "Shoulder SL": sl,
            "Result": result,
            "Exit Time": exit_time
        })

    return trades
    
