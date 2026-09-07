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

st.set_page_config(
    page_title="H&S Ultimate Backtester Pro",
    page_icon="📊",
    layout="wide"
)

# تخصيص التصميم والواجهة لتطابق النمط الحديث في الصورة
st.markdown("""
    <style>
    .stApp {
        background-color: #0e1117;
    }
    div.stExpander {
        background-color: #161b22;
        border-radius: 16px;
        border: 1px solid #30363d;
        padding: 10px;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
    }
    .stButton>button {
        border-radius: 12px;
        background-color: #2563eb;
        color: white;
        font-weight: bold;
        border: none;
        padding: 0.5rem 1rem;
    }
    .stButton>button:hover {
        background-color: #1d4ed8;
    }
    </style>
""", unsafe_allow_html=True)

engine = importlib.reload(engine)

st.title("📊 H&S Ultimate Backtester Pro")
st.caption("اختبار رجعي شامل يدعم Google Sheets، الفواصل المتعددة، ومقارنة وقف الخسارة بتصميم عصري.")

SHEET_ID = "1TXvF6RhSgfJ631UpnWB38Ww1OMvZVx7VonDB_y1pO3s"
DEFAULT_SHEET_NAME = "GOLD"
DEFAULT_COL_NAME = "TOKENS"

st.sidebar.header("⚙️ إعدادات الشاشة والتشغيل")

scan_mode = st.sidebar.radio(
    "طريقة اختيار الأصول:",
    ["Single Asset", "Google Sheet (Scan List)"],
    index=0
)

symbols_to_test = []

if scan_mode == "Single Asset":
    symbol_input = st.sidebar.text_input("Symbol", "BTC-USD").strip()
    symbols_to_test = [symbol_input] if symbol_input else []
else:
    fetched_symbols, err = get_symbols_from_sheet(SHEET_ID, DEFAULT_SHEET_NAME, DEFAULT_COL_NAME)
    if err:
        st.sidebar.error(err)
        symbols_to_test = []
    else:
        symbols_to_test = fetched_symbols
        st.sidebar.success(f"تم تحميل {len(symbols_to_test)} أصل من Google Sheet بنجاح!")

all_timeframes = ["1m", "5m", "15m", "30m", "1h", "4h", "1d", "1wk", "1mo", "3mo", "6mo", "1y", "2y", "5y"]
selected_tfs = st.sidebar.multiselect("اختر الفواصل الزمنية للمقارنة", all_timeframes, default=["1h", "4h", "1d"])

sl_strategy = st.sidebar.radio("استراتيجية وقف الخسارة:", ["الكل (مقارنة الرأس والكتف)", "وقف الرأس فقط (Head SL)", "وقف الكتف فقط (Shoulder SL)"])

run = st.sidebar.button("🚀 تشغيل الاختبار الشامل", use_container_width=True)

def get_safe_period_for_tf(tf):
    if tf in ["1m"]: return "7d"
    elif tf in ["5m", "15m", "30m"]: return "60d"
    elif tf in ["1h", "2h", "4h"]: return "730d"
    else: return "2y"

if run:
    if not symbols_to_test:
        st.error("⚠️ لا توجد أصول متاحة للاختبار. يرجى التحقق من المدخلات أو الشيت.")
    else:
        st.info(f"🚀 جاري بدء الاختبار الرجعي لـ {len(symbols_to_test)} أصل عبر engine.py...")
        
        for symbol in symbols_to_test:
            with st.expander(f"📊 نتائج الفحص للرمز: {symbol}", expanded=(len(symbols_to_test) == 1)):
                tf_results = []
                for tf in selected_tfs:
                    period = get_safe_period_for_tf(tf)
                    fetch_tf = "1d" if tf in ["1y", "2y", "3y", "5y", "6mo"] else tf
                    fetch_period = tf if tf in ["1y", "2y", "3y", "5y", "6mo"] else period
                    
                    df = yf.download(symbol, period=fetch_period, interval=fetch_tf, progress=False)
                    if isinstance(df.columns, pd.MultiIndex):
                        df.columns = df.columns.get_level_values(0)
                        
                    if df.empty or len(df) < 50:
                        continue
                        
                    for sl_type in ["Head SL", "Shoulder SL"]:
                        if sl_strategy != "الكل (مقارنة الرأس والكتف)" and sl_type not in sl_strategy:
                            continue
                        
                        trades = []
                        start_idx = min(100, len(df) // 2)
                        for i in range(start_idx, len(df), max(1, len(df) // 40)):
                            df_slice = df.iloc[:i].copy()
                            
                            df_ind = engine.calculate_indicators(df_slice)
                            df_ind = engine.calculate_zigzag(df_ind)
                            pivots = engine.get_chronological_pivots(df_ind)
                            patterns = engine.detect_all_head_shoulders(pivots, df_ind)
                            
                            if patterns:
                                pat = patterns[-1]
                                end_idx = pat.get("neckline_end_idx")
                                if any(t.get("End_Idx") == end_idx and t.get("SL_Type") == sl_type for t in trades):
                                    continue
                                    
                                bias = pat.get("bias")
                                entry = pat.get("entry")
                                tp = pat.get("tp")
                                
                                if sl_type == "Head SL":
                                    sl = pat.get("sl")
                                else:
                                    nodes = pat.get("nodes", [])
                                    if bias == "Bearish" and len(nodes) >= 4:
                                        sl = max(nodes[1][1], nodes[3][1])
                                    elif bias == "Bullish" and len(nodes) >= 4:
                                        sl = min(nodes[1][1], nodes[3][1])
                                    else:
                                        sl = pat.get("sl")
                                
                                future_df = df.loc[end_idx:].iloc[1:]
                                outcome = "OPEN"
                                for f_idx, row in future_df.iterrows():
                                    h, l = row["High"], row["Low"]
                                    if bias == "Bearish":
                                        if h >= sl: outcome = "LOSS"; break
                                        elif l <= tp: outcome = "WIN"; break
                                    elif bias == "Bullish":
                                        if l <= sl: outcome = "LOSS"; break
                                        elif h >= tp: outcome = "WIN"; break
                                        
                                trades.append({
                                    "Symbol": symbol,
                                    "TF": tf,
                                    "SL_Type": sl_type,
                                    "Outcome": outcome,
                                    "End_Idx": end_idx
                                })
                        
                        if trades:
                            tdf = pd.DataFrame(trades)
                            wins = len(tdf[tdf["Outcome"] == "WIN"])
                            losses = len(tdf[tdf["Outcome"] == "LOSS"])
                            total = wins + losses
                            wr = (wins / total) * 100 if total > 0 else 0
                            tf_results.append({
                                "Symbol": symbol,
                                "Timeframe": tf,
                                "SL Method": sl_type,
                                "Total Trades": total,
                                "Wins": wins,
                                "Losses": losses,
                                "Win Rate (%)": round(wr, 2)
                            })
                
                if tf_results:
                    res_df = pd.DataFrame(tf_results).sort_values(by="Win Rate (%)", ascending=False)
                    best_row = res_df.iloc[0]
                    
                    st.dataframe(res_df, use_container_width=True)
                    
                    st.markdown(f"**📋 التقرير الشامل والتوصية الاستراتيجية للرمز: {symbol}**")
                    report_lines = [
                        f"1. **أفضل فاصل زمني:** الفاصل ({best_row['Timeframe']}) حقق أعلى معدل نجاح بـ {best_row['Win Rate (%)']}% باستخدام ({best_row['SL Method']}).",
                        f"2. **مقارنة الوقف:** تبين تفوق استراتيجية ({best_row['SL Method']}) في ضبط المخاطر لهذا الأصل.",
                        f"3. **كفاءة الصفقات:** إجمالي الصفقات الخاضعة للاختبار يعكس موثوقية الأنماط المكتشفة.",
                        f"4. **حالة السوق:** التباين بين الفواصل يؤكد ضرورة الالتزام بالفاصل الأمثل.",
                        f"5. **التوصية:** يوصى بالتداول على **{best_row['Timeframe']}** مع اعتماد وقف خسارة بنظام **{best_row['SL Method']}**."
                    ]
                    for line in report_lines:
                        st.markdown(line)
                else:
                    st.warning(f"لم تُسجل صفقات كافية على الرمز {symbol} بالفواصل المحددة.")
                    
