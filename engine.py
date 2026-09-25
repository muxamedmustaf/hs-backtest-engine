# -*- coding: utf-8 -*-
import pandas as pd
import numpy as np

def calculate_indicators(df):
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))
    df['EMA50'] = df['Close'].ewm(span=50, adjust=False).mean()
    df['EMA200'] = df['Close'].ewm(span=200, adjust=False).mean()
    return df

def get_pivot_points(df, order=5):
    df['Peak'] = df['High'][(df['High'] == df['High'].rolling(window=2*order+1, center=True).max())]
    df['Trough'] = df['Low'][(df['Low'] == df['Low'].rolling(window=2*order+1, center=True).min())]
    
    nodes = []
    for time_idx, val in df['Peak'].dropna().items():
        nodes.append({'time': time_idx, 'price': val, 'type': 'peak', 'idx': df.index.get_loc(time_idx)})
    for time_idx, val in df['Trough'].dropna().items():
        nodes.append({'time': time_idx, 'price': val, 'type': 'trough', 'idx': df.index.get_loc(time_idx)})
        
    nodes = sorted(nodes, key=lambda x: x['idx'])
    
    clean_nodes = []
    for node in nodes:
        if not clean_nodes:
            clean_nodes.append(node)
        else:
            if clean_nodes[-1]['type'] != node['type']:
                clean_nodes.append(node)
            else:
                if node['type'] == 'peak' and node['price'] > clean_nodes[-1]['price']:
                    clean_nodes[-1] = node
                elif node['type'] == 'trough' and node['price'] < clean_nodes[-1]['price']:
                    clean_nodes[-1] = node
                    
    df.drop(columns=['Peak', 'Trough'], inplace=True)
    return clean_nodes

def detect_confirmed_patterns(df, nodes):
    patterns = []
    if len(nodes) < 5: return patterns
        
    for i in range(len(nodes) - 4):
        window = nodes[i:i+5]
        types = [n['type'] for n in window]
        
        if types == ['trough', 'peak', 'trough', 'peak', 'trough']:
            ls, p1, head, p2, rs = window
            if head['price'] < ls['price'] and head['price'] < rs['price']:
                idx1, y1 = p1['idx'], p1['price']
                idx2, y2 = p2['idx'], p2['price']
                
                if idx1 != idx2:
                    slope = (y2 - y1) / (idx2 - idx1)
                    
                    for j in range(rs['idx'] + 1, len(df)):
                        neckline_price = y2 + slope * (j - idx2)
                        close_price = df['Close'].iloc[j]
                        
                        if close_price > neckline_price:
                            rsi_val = df['RSI'].iloc[j]
                            ema50 = df['EMA50'].iloc[j]
                            ema200 = df['EMA200'].iloc[j]
                            
                            if (30 <= rsi_val <= 75) and (ema50 < ema200):
                                entry = close_price
                                sl = head['price']
                                tp = entry + (neckline_price - head['price'])
                                patterns.append({
                                    'pattern': 'Inverse Head & Shoulders', 'signal': 'STRONG BUY',
                                    'nodes': [(n['time'], n['price']) for n in window],
                                    'neckline_nodes': [(p1['time'], p1['price']), (p2['time'], p2['price'])],
                                    'target_nodes': [(df.index[j], entry), (df.index[j], tp)],
                                    'entry': entry, 'sl': sl, 'tp': tp, 'end_idx': j
                                })
                            break

        elif types == ['peak', 'trough', 'peak', 'trough', 'peak']:
            ls, t1, head, t2, rs = window
            if head['price'] > ls['price'] and head['price'] > rs['price']:
                idx1, y1 = t1['idx'], t1['price']
                idx2, y2 = t2['idx'], t2['price']
                
                if idx1 != idx2:
                    slope = (y2 - y1) / (idx2 - idx1)
                    
                    for j in range(rs['idx'] + 1, len(df)):
                        neckline_price = y2 + slope * (j - idx2)
                        close_price = df['Close'].iloc[j]
                        
                        if close_price < neckline_price:
                            rsi_val = df['RSI'].iloc[j]
                            ema50 = df['EMA50'].iloc[j]
                            ema200 = df['EMA200'].iloc[j]
                            
                            if (30 <= rsi_val <= 75) and (ema50 > ema200):
                                entry = close_price
                                sl = head['price']
                                tp = entry - (head['price'] - neckline_price)
                                patterns.append({
                                    'pattern': 'Head & Shoulders', 'signal': 'STRONG SELL',
                                    'nodes': [(n['time'], n['price']) for n in window],
                                    'neckline_nodes': [(t1['time'], t1['price']), (t2['time'], t2['price'])],
                                    'target_nodes': [(df.index[j], entry), (df.index[j], tp)],
                                    'entry': entry, 'sl': sl, 'tp': tp, 'end_idx': j
                                })
                            break

    return patterns

def backtest_strategy(df):
    df = calculate_indicators(df)
    nodes = get_pivot_points(df, order=5)
    patterns = detect_confirmed_patterns(df, nodes)
    
    trades = []
    if not patterns: return trades
        
    for p in patterns:
        end_idx = p['end_idx']
        signal = p['signal']
        entry_price = p['entry']
        sl = p['sl']
        tp = p['tp']
        
        if end_idx + 1 >= len(df): continue
            
        forward_df = df.iloc[end_idx+1:]
        head_res, shoulder_res = "PENDING", "PENDING"
        dist = abs(entry_price - tp)
        shoulder_tp = entry_price + (dist/2) if signal == 'STRONG BUY' else entry_price - (dist/2)
        
        for _, row in forward_df.iterrows():
            high, low = row['High'], row['Low']
            
            if signal == 'STRONG BUY':
                if low <= sl:
                    head_res = "LOSS" if head_res == "PENDING" else head_res
                    shoulder_res = "LOSS" if shoulder_res == "PENDING" else shoulder_res
                    break
                if high >= shoulder_tp and shoulder_res == "PENDING":
                    shoulder_res = "WIN"
                if high >= tp:
                    head_res = "WIN"
                    if shoulder_res == "PENDING": shoulder_res = "WIN"
                    break
            else:
                if high >= sl:
                    head_res = "LOSS" if head_res == "PENDING" else head_res
                    shoulder_res = "LOSS" if shoulder_res == "PENDING" else shoulder_res
                    break
                if low <= shoulder_tp and shoulder_res == "PENDING":
                    shoulder_res = "WIN"
                if low <= tp:
                    head_res = "WIN"
                    if shoulder_res == "PENDING": shoulder_res = "WIN"
                    break
                    
        trades.append({
            "Entry Time": df.index[end_idx],
            "Type": "BUY" if signal == 'STRONG BUY' else "SELL",
            "Entry Price": round(entry_price, 5), "SL": round(sl, 5), "TP": round(tp, 5),
            "Head Result": head_res, "Shoulder Result": shoulder_res,
            "nodes": p['nodes'], "neckline_nodes": p['neckline_nodes'], "target_nodes": p['target_nodes']
        })
        
    return trades
                   
