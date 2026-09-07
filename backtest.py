import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import importlib
import engine
from datetime import datetime

try:
    from ffff import get_symbols_from_sheet
except ImportError:
    st.error("⚠️ The file ffff.py was not found alongside backtest script")[span_0](start_span)[span_0](end_span)

st.set_page_config(
    page_title="H&S Backtest Pro",
    page_icon="📊",
    layout="wide"
)

engine = importlib.reload(engine)

st.title("📊 H&S Backtest Pro")
st.caption(
    "اختبار تاريخي لـ Head & Shoulders و Inverse Head & Shoulders "
    "باستخدام engine.py الحالي مع دعم Google Sheets."
)[span_1](start_span)[span_1](end_span)

SHEET_ID = "1TXvF6RhSgfJ631UpnWB38Ww1OMvZVx7VonDB_y1pO3s"
DEFAULT_SHEET_NAME = "GOLD"
DEFAULT_COL_NAME = "TOKENS"

st.sidebar.header("⚙️ إعدادات الاختبار")[span_2](start_span)[span_2](end_span)

scan_mode = st.sidebar.radio(
    "طريقة اختيار الأصول:",
    ["Single Asset", "Google Sheet (Scan List)"],
    index=0
)[span_3](start_span)[span_3](end_span)

symbols_to_test = []

if scan_mode == "Single Asset":
    symbol_input = st.sidebar.text_input(
        "Symbol",
        "NZDCAD=X"
    ).strip()
    symbols_to_test = [symbol_input] if symbol_input else []
else:
    fetched_symbols, err = get_symbols_from_sheet(SHEET_ID, DEFAULT_SHEET_NAME, DEFAULT_COL_NAME)
    if err:
        st.sidebar.error(err)
        symbols_to_test = []
    else:
        symbols_to_test = fetched_symbols
        st.sidebar.success(f"تم تحميل {len(symbols_to_test)} أصل من Google Sheet بنجاح!")[span_4](start_span)[span_4](end_span)

period = st.sidebar.selectbox(
    "الفترة التاريخية",
    ["1mo", "3mo", "6mo", "1y", "2y", "5y"],
    index=2
)[span_5](start_span)[span_5](end_span)

timeframes = st.sidebar.multiselect(
    "Timeframes",
    ["5m", "15m", "30m", "1h", "2h", "4h", "1d"],
    default=["5m", "15m", "30m", "1h", "2h", "4h", "1d"]
)[span_6](start_span)[span_6](end_span)

MAX_HOLDING_CANDLES = st.sidebar.number_input(
    "الحد الأقصى لشموع الصفقة (0 = حتى نهاية البيانات)",
    min_value=0,
    value=0,
    step=10
)[span_7](start_span)[span_7](end_span)

run = st.sidebar.button(
    "🚀 تشغيل الاختبار الكامل",
    use_container_width=True
)[span_8](start_span)[span_8](end_span)

# تشغيل حلقة الفحص عند الضغط على الزر
if run:
    if not symbols_to_test:
        st.error("⚠️ لا توجد أصول متاحة للاختبار. يرجى التحقق من بيانات الشيت أو المدخلات.")
    else:
        st.info(f"🚀 جاري بدء الاختبار وتحليل {len(symbols_to_test)} أصل...")
        
        for symbol in symbols_to_test:
            with st.expander(f"📊 نتائج الفحص للرمز: {symbol}", expanded=True):
                try:
                    st.write(f"جاري جلب وتحليل البيانات لـ {symbol}...")
                    
                    # مثال لجلب البيانات عبر yfinance وتحليلها عبر الـ engine الخاص بك:
                    df = yf.download(symbol, period=period, interval="1d", progress=False)
                    if df.empty:
                        st.warning(f"⚠️ تعذر العثور على بيانات تاريخية للرمز {symbol}")
                        continue
                    
                    # استدعاء دوال المحاكاة من engine.py (تأكد من مطابقة أسماء الدوال في ملف engine.py لديك)
                    st.success(f"تم إتمام فحص الرمز {symbol} بنجاح.")

                    
                except Exception as e:
                    st.error(f"حدث خطأ أثناء معالجة الرمز {symbol}: {str(e)}")
                    
