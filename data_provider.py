# -*- coding: utf-8 -*-
"""
DATA PROVIDER — Yahoo Finance ama Twelve Data
Timezone Adjustment: UTC -> GMT+2 (IC Markets)
"""
import pandas as pd
import streamlit as st
from datetime import datetime, timedelta
import time  # <--- Waa muhiim inuu halkan ku jiro

# ==============================================================================
# 🚪 DOORASHADA PROVIDER
# ==============================================================================
PROVIDER = "twelve_data"  # <--- "yahoo" ama "twelve_data"

# ==============================================================================
# 🔑 API KEY — Twelve Data
# ==============================================================================
TWELVE_DATA_API_KEY = "951d7884292c4734aee5e4fc82878dc3" 

# ==============================================================================
# ⏱️ TIMEZONE CONFIG
# ==============================================================================
TARGET_TIMEZONE = "GMT+2"

TIMEZONE_OFFSET_HOURS = {
    "UTC": 0,
    "GMT+1": 1,
    "GMT+2": 2,
    "GMT+3": 3,
    "GMT+4": 4,
    "GMT-1": -1,
    "GMT-2": -2,
    "GMT-3": -3,
    "GMT-4": -4,
    "GMT-5": -5,
}

def adjust_timezone(df, target_tz=None):
    """U beddel saacadda DataFrame-ka — isku mid dhigista MT5."""
    if df is None or df.empty:
        return df

    if target_tz is None:
        target_tz = TARGET_TIMEZONE

    offset = TIMEZONE_OFFSET_HOURS.get(target_tz, 0)

    if offset == 0:
        return df

    df = df.copy()
    df.index = df.index + pd.Timedelta(hours=offset)

    return df

# ==============================================================================
# 🛠️ HELPERS — Timeframe + Symbol Conversion
# ==============================================================================
def _timeframe_yahoo(tf):
    return {
        "1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m",
        "1h": "1h", "4h": "4h", "1d": "1d",
    }.get(tf, "1h")

def _timeframe_twelve(tf):
    return {
        "1m": "1min", "5m": "5min", "15m": "15min", "30m": "30min",
        "1h": "1h", "4h": "4h", "1d": "1day",
    }.get(tf, "1h")

def _symbol_twelve(symbol):
    """Yahoo -> Twelve Data format."""
    s = str(symbol).upper().strip()
    if "-USD" in s:
        return s.replace("-USD", "/USD")
    if s in ["BTC-USD", "ETH-USD"]:
        return s.replace("-USD", "/USD")
    if s in ["GC=F", "XAUUSD", "XAUUSD=X", "GOLD"]:
        return "XAU/USD"
    if s in ["SI=F", "XAGUSD", "XAGUSD=X", "SILVER"]:
        return "XAG/USD"
    if s.endswith("=X"):
        s = s.replace("=X", "")
        if len(s) == 6:
            return f"{s[:3]}/{s[3:]}"
        return s
    if len(s) == 6 and s.isalpha():
        return f"{s[:3]}/{s[3:]}"
    return s

# ==============================================================================
# 🤖 YAHOO FINANCE
# ==============================================================================
def _fetch_yahoo(symbol, interval="1h", period="3mo",
                 start_date=None, end_date=None):
    """Yahoo Finance."""
    try:
        import yfinance as yf
    except ImportError:
        raise ImportError("Ku shub: pip install yfinance")

    tf = _timeframe_yahoo(interval)

    if start_date and end_date:
        df = yf.download(symbol, start=start_date, end=end_date,
                         interval=tf, progress=False, auto_adjust=False)
    else:
        df = yf.download(symbol, period=period,
                         interval=tf, progress=False, auto_adjust=False)

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    if df is None or df.empty:
        return None

    df.rename(columns={
        "open": "Open", "high": "High", "low": "Low",
        "close": "Close", "volume": "Volume",
    }, inplace=True)

    return df

# ==============================================================================
# 🟡 TWELVE DATA
# ==============================================================================
def _fetch_twelve(symbol, interval="1h", period="3mo",
                  start_date=None, end_date=None):
    """Twelve Data API."""
    try:
        from twelvedata import TDClient
    except ImportError:
        raise ImportError("Ku shub: pip install twelvedata")

    td = TDClient(apikey=TWELVE_DATA_API_KEY)
    
    tf = _timeframe_twelve(interval)
    sym = _symbol_twelve(symbol)

    ts = td.time_series(
        symbol=sym,
        interval=tf,
        outputsize=5000,
        timezone="UTC"
    )

    df = ts.as_pandas()

    if df is None or df.empty:
        return None

    # Twelve Data wuxuu soo celiyaa xogta kor ilaa hoos, marka waa in la rogaa
    df = df.iloc[::-1]

    df.rename(columns={
        "open": "Open", "high": "High", "low": "Low",
        "close": "Close", "volume": "Volume",
    }, inplace=True)

    # XALKII DIHBAATADA RATE LIMIT
    time.sleep(8)  # Sug 8 ilbiriqsi ka hor inta aadan lammaanaha xigta soo qaadin

    return df

# ==============================================================================
# 🚀 MAIN WRAPPER FUNCTION (Kani waa kii backtest.py raadinayay)
# ==============================================================================
def fetch_data(symbol, interval="1h", period="3mo",
               start_date=None, end_date=None, 
               cache_hours=None, **kwargs):  # <--- Ku dar cache_hours iyo **kwargs halkan
    """Function-ka ugu weyn ee xogta soo qaada."""
    
    if PROVIDER == "twelve_data":
        df = _fetch_twelve(symbol, interval, period, start_date, end_date)
    else:
        df = _fetch_yahoo(symbol, interval, period, start_date, end_date)
    
    # Halkan ayaa timezone-ka loo beddelaa GMT+2
    if df is not None:
        df = adjust_timezone(df)
    
    return df

def get_provider_info():
    """Soo celi macluumaadka ku saabsan provider-ka hadda shaqaynaya."""
    return {
        "provider": PROVIDER,
        "api_key_used": TWELVE_DATA_API_KEY if PROVIDER == "twelve_data" else "N/A",
        "timezone": TARGET_TIMEZONE
    }
