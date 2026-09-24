# -*- coding: utf-8 -*-
import pandas as pd
import numpy as np

def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """حساب المؤشرات الفنية الأساسية (RSI و EMAs)"""
    df = df.copy()
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / (loss + 1e-10)
    df['RSI'] = 100 - (100 / (1 + rs))
    
    df['EMA_20'] = df['Close'].ewm(span=20, adjust=False).mean()
    df['EMA_50'] = df['Close'].ewm(span=50, adjust=False).mean()
    df['EMA_200'] = df['Close'].ewm(span=200, adjust=False).mean()
    return df

def prepare_timeframe_data(df: pd.DataFrame, target_interval: str) -> pd.DataFrame:
    """تحويل وتجميع بيانات الشموع (OHLCV Resampling) لدعم كافة الأطر الزمانية العالمية"""
    if df.empty:
        return df
        
    resample_map = {
        "1m": "1min", "2m": "2min", "3m": "3min", "4m": "4min", "5m": "5min",
        "10m": "10min", "15m": "15min", "30m": "30min", "45m": "45min",
        "1h": "1h", "2h": "2h", "3h": "3h", "4h": "4h", "6h": "6h", "8h": "8h", "12h": "12h",
        "1d": "1D", "2d": "2D", "3d": "3D", "1wk": "1W", "1mo": "1ME", "3mo": "3ME", "1y": "1YE"
    }
    
    rule = resample_map.get(target_interval)
    if not rule or target_interval in ["1m", "5m", "15m", "30m", "1h", "1d", "1wk", "1mo"]:
        return df
        
    try:
        resampled_df = df.resample(rule).agg({
            'Open': 'first',
            'High': 'max',
            'Low': 'min',
            'Close': 'last',
            'Volume': 'sum' if 'Volume' in df.columns else 'first'
        }).dropna()
        return resampled_df
    except Exception:
        return df

def find_pivots(df: pd.DataFrame, window: int = 3):
    """استخراج القمم والقيعان المحلية"""
    pivots_high, pivots_low = [], []
    highs, lows, dates = df['High'].values, df['Low'].values, df.index
    
    for i in range(window, len(df) - window):
        if all(highs[i] > highs[i - j] for j in range(1, window + 1)) and \
           all(highs[i] > highs[i + j] for j in range(1, window + 1)):
            pivots_high.append((dates[i], highs[i], i))
            
        if all(lows[i] < lows[i - j] for j in range(1, window + 1)) and \
           all(lows[i] < lows[i + j] for j in range(1, window + 1)):
            pivots_low.append((dates[i], lows[i], i))
            
    return pivots_high, pivots_low

def detect_head_and_shoulders(df: pd.DataFrame, pivots_high, pivots_low, 
                              shoulder_tolerance: float = 0.15, 
                              head_prominence: float = 0.01):
    """خوارزمية التعرف الهيكلي المتقدمة المطبقة بكافة شروط البروز والتماثل"""
    patterns = []
    
    # 1. الرأس والكتفين الهبوطي (Head & Shoulders)
    for i in range(len(pivots_high) - 2):
        l_shoulder, head, r_shoulder = pivots_high[i], pivots_high[i+1], pivots_high[i+2]
        
        # شرط البروز
        if head[1] > l_shoulder[1] * (1 + head_prominence) and head[1] > r_shoulder[1] * (1 + head_prominence):
            # شرط التماثل
            shoulder_diff = abs(l_shoulder[1] - r_shoulder[1]) / max(l_shoulder[1], r_shoulder[1])
            if shoulder_diff <= shoulder_tolerance:
                lows_between_1 = [p for p in pivots_low if l_shoulder[2] < p[2] < head[2]]
                lows_between_2 = [p for p in pivots_low if head[2] < p[2] < r_shoulder[2]]
                
                if lows_between_1 and lows_between_2:
                    n1 = min(lows_between_1, key=lambda x: x[1])
                    n2 = min(lows_between_2, key=lambda x: x[1])
                    
                    nodes = [(l_shoulder[0], l_shoulder[1]), (n1[0], n1[1]), (head[0], head[1]), (n2[0], n2[1]), (r_shoulder[0], r_shoulder[1])]
                    neckline_nodes = [(n1[0], n1[1]), (n2[0], n2[1])]
                    
                    entry = round(float(n2[1]), 5)
                    sl = round(float(r_shoulder[1]), 5)
                    pattern_height = head[1] - ((n1[1] + n2[1]) / 2)
                    tp_head = round(float(entry - pattern_height), 5)
                    tp_shoulder = round(float(entry - (r_shoulder[1] - n2[1])), 5)
                    
                    patterns.append({
                        "type": "Head and Shoulders",
                        "signal": "STRONG SELL",
                        "end_idx": r_shoulder[2],
                        "nodes": nodes,
                        "neckline_nodes": neckline_nodes,
                        "entry": entry,
                        "sl": sl,
                        "tp_head": tp_head,
                        "tp_shoulder": tp_shoulder
                    })

    # 2. الرأس والكتفين الصعودي المعكوس (Inverse Head & Shoulders)
    for i in range(len(pivots_low) - 2):
        l_shoulder, head, r_shoulder = pivots_low[i], pivots_low[i+1], pivots_low[i+2]
        
        # شرط البروز للمنعكس
        if head[1] < l_shoulder[1] * (1 - head_prominence) and head[1] < r_shoulder[1] * (1 - head_prominence):
            # شرط التماثل
            shoulder_diff = abs(l_shoulder[1] - r_shoulder[1]) / max(l_shoulder[1], r_shoulder[1])
            if shoulder_diff <= shoulder_tolerance:
                highs_between_1 = [p for p in pivots_high if l_shoulder[2] < p[2] < head[2]]
                highs_between_2 = [p for p in pivots_high if head[2] < p[2] < r_shoulder[2]]
                
                if highs_between_1 and highs_between_2:
                    n1 = max(highs_between_1, key=lambda x: x[1])
                    n2 = max(highs_between_2, key=lambda x: x[1])
                    
                    nodes = [(l_shoulder[0], l_shoulder[1]), (n1[0], n1[1]), (head[0], head[1]), (n2[0], n2[1]), (r_shoulder[0], r_shoulder[1])]
                    neckline_nodes = [(n1[0], n1[1]), (n2[0], n2[1])]
                    
                    entry = round(float(n2[1]), 5)
                    sl = round(float(r_shoulder[1]), 5)
                    pattern_height = ((n1[1] + n2[1]) / 2) - head[1]
                    tp_head = round(float(entry + pattern_height), 5)
                    tp_shoulder = round(float(entry + (n2[1] - r_shoulder[1])), 5)
                    
                    patterns.append({
                        "type": "Inverse Head and Shoulders",
                        "signal": "STRONG BUY",
                        "end_idx": r_shoulder[2],
                        "nodes": nodes,
                        "neckline_nodes": neckline_nodes,
                        "entry": entry,
                        "sl": sl,
                        "tp_head": tp_head,
                        "tp_shoulder": tp_shoulder
                    })

    return patterns

def run_full_analysis(df: pd.DataFrame, interval: str = "1d", window: int = 3, shoulder_tolerance: float = 0.15, head_prominence: float = 0.01) -> dict:
    """تغذية الواجهة بالتحليل المباشر"""
    if df.empty or len(df) < 20:
        return {
            "signal": "NEUTRAL", "pattern": "None", "entry": 0.0, "sl": 0.0, "tp": 0.0,
            "nodes": [], "neckline_nodes": [], "df": df
        }
        
    df_prep = prepare_timeframe_data(df, interval)
    df_calc = calculate_indicators(df_prep)
    pivots_high, pivots_low = find_pivots(df_calc, window=window)
    patterns = detect_head_and_shoulders(df_calc, pivots_high, pivots_low, shoulder_tolerance=shoulder_tolerance, head_prominence=head_prominence)
    
    if patterns:
        latest = patterns[-1]
        return {
            "signal": latest["signal"],
            "pattern": latest["type"],
            "entry": latest["entry"],
            "sl": latest["sl"],
            "tp": latest["tp_head"],
            "nodes": latest["nodes"],
            "neckline_nodes": latest["neckline_nodes"],
            "df": df_calc
        }
        
    return {
        "signal": "NEUTRAL",
        "pattern": "No Pattern Detected",
        "entry": round(float(df_calc['Close'].iloc[-1]), 5),
        "sl": 0.0, "tp": 0.0, "nodes": [], "neckline_nodes": [], "df": df_calc
    }

def backtest_strategy(df: pd.DataFrame, interval: str = "1d", window: int = 3, shoulder_tolerance: float = 0.15, head_prominence: float = 0.01) -> list:
    """محاكاة الاختبار الرجعي بالأهداف المزدوجة وتقييم الأداء"""
    if df.empty or len(df) < 30:
        return []
        
    df_prep = prepare_timeframe_data(df, interval)
    df_calc = calculate_indicators(df_prep)
    pivots_high, pivots_low = find_pivots(df_calc, window=window)
    patterns = detect_head_and_shoulders(df_calc, pivots_high, pivots_low, shoulder_tolerance=shoulder_tolerance, head_prominence=head_prominence)
    
    trades = []
    for pat in patterns:
        start_idx = pat["end_idx"]
        signal = pat["signal"]
        entry = pat["entry"]
        sl = pat["sl"]
        tp_head = pat["tp_head"]
        tp_shoulder = pat["tp_shoulder"]
        
        future_df = df_calc.iloc[start_idx:]
        head_result = "LOSS"
        shoulder_result = "LOSS"
        
        for _, row in future_df.iterrows():
            high, low = row['High'], row['Low']
            
            if signal == "STRONG SELL":
                if low <= tp_head and head_result != "WIN":
                    head_result = "WIN"
                if low <= tp_shoulder and shoulder_result != "WIN":
                    shoulder_result = "WIN"
                if high >= sl:
                    break
                    
            elif signal == "STRONG BUY":
                if high >= tp_head and head_result != "WIN":
                    head_result = "WIN"
                if high >= tp_shoulder and shoulder_result != "WIN":
                    shoulder_result = "WIN"
                if low <= sl:
                    break
                    
        trade_date = pat["nodes"][-1][0] if pat["nodes"] else df_calc.index[start_idx]
        
        trades.append({
            "Date": str(trade_date),
            "Pattern": pat["type"],
            "Signal": signal,
            "Entry": entry,
            "SL": sl,
            "TP": tp_head,
            "Head Result": head_result,
            "Shoulder Result": shoulder_result,
            "nodes": pat["nodes"],
            "neckline_nodes": pat["neckline_nodes"]
        })
        
    return trades
        
