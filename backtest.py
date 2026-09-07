import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import importlib
import engine

try:
    from ffff import get_symbols_from_sheet
except ImportError:
    st.error("⚠️ The file ffff.py was not found alongside backtest script")

st.set_page_config(page_title="Smart Historical Backtest", layout="wide")
engine = importlib.reload(engine)

st.title("🧠 Smart Historical H&S Backtester")
st.caption("محرك اختبار رجعي ذكي يتجاوز قيود النطاق الزمني باستخدام النافذة المنزلقة.")

SHEET_ID = "1TXvF6RhSgfJ631UpnWB38Ww1OMvZVx7VonDB_y1pO3s"
DEFAULT_SHEET_NAME = "GOLD"
DEFAULT_COL_NAME = "TOKENS"

st.sidebar.header("⚙️ إعدادات الاختبار الذكي")
symbol_input = st.sidebar.text_input("Symbol", "BTC-USD").strip()
period = st.sidebar.selectbox("الفترة", ["1y", "2y", "5y"], index=1)
run = st.sidebar.button("🚀 بدء الاختبار الرجعي الذكي", use_container_width=True)

if run:
    with st.spinner("جاري جلب البيانات وتطبيق النافذة المنزلقة على التاريخ..."):
        df = yf.download(symbol_input, period=period, interval="1d", progress=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
            
        trades = []
        # تطبيق النافذة المنزلقة عبر التاريخ الممتد
        start_idx = 100
        step = 1 # يمكن جعلها 5 لتسريع المعالجة
        
        for i in range(start_idx, len(df), step):
            df_slice = df.iloc[:i].copy()
            
            # تشغيل تحليلات الإنجين على النافذة المقتطعة
            df_ind = engine.calculate_indicators(df_slice)
            df_ind = engine.calculate_zigzag(df_ind)
            pivots = engine.get_chronological_pivots(df_ind)
            patterns = engine.detect_all_head_shoulders(pivots, df_ind)
            
            if patterns:
                latest_pat = patterns[-1]
                end_idx = latest_pat.get("neckline_end_idx")
                
                # التأكد من عدم تكرار نفس النمط في نفس الموضع
                if any(t.get("End_Idx") == end_idx for t in trades):
                    continue
                
                entry = latest_pat.get("entry")
                sl = latest_pat.get("sl")
                tp = latest_pat.get("tp")
                bias = latest_pat.get("bias")
                
                # محاكاة المستقبل بعد اكتمال النمط
                future_df = df.loc[end_idx:].iloc[1:]
                outcome = "OPEN"
                exit_price = entry
                
                for f_idx, row in future_df.iterrows():
                    h, l = row["High"], row["Low"]
                    if bias == "Bearish":
                        if h >= sl:
                            outcome = "LOSS"; exit_price = sl; break
                        elif l <= tp:
                            outcome = "WIN"; exit_price = tp; break
                    elif bias == "Bullish":
                        if l <= sl:
                            outcome = "LOSS"; exit_price = sl; break
                        elif h >= tp:
                            outcome = "WIN"; exit_price = tp; break
                
                trades.append({
                    "Date": end_idx,
                    "Pattern": latest_pat.get("pattern"),
                    "Bias": bias,
                    "Entry": entry,
                    "SL": sl,
                    "TP": tp,
                    "Outcome": outcome,
                    "End_Idx": end_idx
                })
        
        if trades:
            tdf = pd.DataFrame(trades)
            wins = len(tdf[tdf["Outcome"] == "WIN"])
            losses = len(tdf[tdf["Outcome"] == "LOSS"])
            total = len(tdf)
            wr = (wins / total) * 100 if total > 0 else 0
            
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("إجمالي الصفقات التاريخية", total)
            c2.metric("الرابحة", wins)
            c3.metric("الخاسرة", losses)
            c4.metric("نسبة النجاح الكلية", f"{wr:.2f}%")
            
            st.dataframe(tdf.drop(columns=["End_Idx"]), use_container_width=True)
        else:
            st.warning("لم يتم العثور على أنماط تاريخية مطابقة لشروط النافذة المنزلقة.")
            
