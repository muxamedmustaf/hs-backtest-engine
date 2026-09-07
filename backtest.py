import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import importlib
import engine
from datetime import datetime

# Ku darso import-ka ffff.py si loo soo akhriyo Google Sheets
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

# Hidden Spreadsheet Constants (sida ku jirta mobile analysis appkaaga)
SHEET_ID = "1TXvF6RhSgfJ631UpnWB38Ww1OMvZVx7VonDB_y1pO3s"
DEFAULT_SHEET_NAME = "GOLD"
DEFAULT_COL_NAME = "TOKENS"

st.sidebar.header("⚙️ إعدادات الاختبار")

# Doorka habka loo soo qaadanayo astaamaha (Scan Method / Selection)
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
        st.sidebar.success(f"تم تحميل {len(symbols_to_test)} أصل من Google Sheet بنجاح!")

period = st.sidebar.selectbox(
    "الفترة التاريخية",
    ["1mo", "3mo", "6mo", "1y", "2y", "5y"],
    index=2
)

timeframes = st.sidebar.multiselect(
    "Timeframes",
    ["5m", "15m", "30m", "1h", "2h", "4h", "1d"],
    default=["5m", "15m", "30m", "1h", "2h", "4h", "1d"]
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

# [Qaybaha kale ee koodka sida normalize_ohlcv, resample_4h, download_timeframe, iwm. waxay ahaanayaan sidoodii hore...]
