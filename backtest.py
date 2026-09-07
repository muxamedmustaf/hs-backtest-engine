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
    st.error("⚠️ The file ffff.py was not found alongside backtest script")

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
)

SHEET_ID = "1TXvF6RhSgfJ631UpnWB38Ww1OMvZVx7VonDB_y1pO3s"
DEFAULT_SHEET_NAME = "GOLD"
DEFAULT_COL_NAME = "TOKENS"

st.sidebar.header("⚙️ إعدادات الاختبار")

scan_mode = st.sidebar.radio(
    "طريقة اختيار الأصول:",
    ["Single Asset", "Google Sheet (Scan List)"],
    index=0
)

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
        st.sidebar.success(f"تم تحميل {len(symbols_to_test)} أصل من Google Sheet بنجاح!")[span_0](start_span)[span_0](end_span)

period = st.sidebar.selectbox(
    "الفترة التاريخية",
    ["1mo", "3mo", "6mo", "1y", "2y", "5y"],
    index=2
)

timeframes = st.sidebar.multiselect(
    "Timeframes",
    ["5m", "15m", "30m", "1h", "2h", "4h", "1d"],
    default=["1d"]
)

MAX_HOLDING_CANDLES = st.sidebar.number_input(
    "الحد الأقصى لشموع الصفقة (0 = حتى نهاية البيانات)",
    min_value=0,
    value=0,
    step=10
)

run = st.sidebar.button(
    "🚀 تشغيل الاختبار الكامل",
    use_container_width=True
)

if run:
    if not symbols_to_test:
        st.error("⚠️ لا توجد أصول متاحة للاختبار. يرجى التحقق من بيانات الشيت أو المدخلات.")
    else:
        st.info(f"🚀 جاري بدء الاختبار وتحليل {len(symbols_to_test)} أصل عبر engine.py...")
        
        for symbol in symbols_to_test:
            with st.expander(f"📊 نتائج الفحص للرمز: {symbol}", expanded=True):
                for tf in timeframes:
                    st.write(f"⏱️ فحص الفاصل الزمني ({tf})...")
                    try:
                        df = yf.download(symbol, period=period, interval=tf, progress=False)
                        if df.empty:
                            st.warning(f"⚠️ تعذر العثور على بيانات تاريخية للرمز {symbol} على الفاصل {tf}")
                            continue
                        
                        # تنظيف الأعمدة المتعددة لو وجدت في yfinance
                        if isinstance(df.columns, pd.MultiIndex):
                            df.columns = df.columns.get_level_values(0)

                        # استدعاء دالة التحليل الأساسية من engine.py[span_1](start_span)[span_1](end_span)
                        analysis_result = engine.run_full_analysis(df)
                        
                        signal = analysis_result.get("signal", "WAITING")
                        pattern = analysis_result.get("pattern", "NO PATTERN DETECTED")
                        bias = analysis_result.get("bias", "Neutral")
                        
                        col1, col2, col3, col4 = st.columns(4)
                        col1.metric("الإشارة (Signal)", signal)
                        col2.metric("النمط (Pattern)", pattern)
                        col3.metric("التحيز (Bias)", bias)
                        col4.metric("عدد الأنماط المكتشفة", len(analysis_result.get("all_patterns", [])))
                        
                        if signal != "WAITING":
                            st.success(f"🎯 نقطة الدخول (Entry): {analysis_result.get('entry')}")
                            st.info(f"🛑 وقف الخسارة (SL): {analysis_result.get('sl')} | 🎯 الهدف (TP): {analysis_result.get('tp')}")
                        else:
                            st.write("💤 لا توجد إشارة قوية مطابقة للشروط الحالية.")
                            
                    except Exception as e:
                        st.error(f"حدث خطأ أثناء معالجة الرمز {symbol} على الفاصل {tf}: {str(e)}")
                        
