# -*- coding: utf-8 -*-
import pandas as pd
import streamlit as st
from datetime import datetime, timedelta
import time

PROVIDER = "twelve_data"
TWELVE_DATA_API_KEY = "951d7884292c4734aee5e4fc82878dc3" 
TARGET_TIMEZONE = "GMT+2"

TIMEZONE_OFFSET_HOURS = {
    "UTC": 0, "GMT+1": 1, "GMT+2": 2, "GMT+3": 3, "GMT+4": 4,
    "GMT-1": -1, "GMT-2": -2, "GMT-3": -3, "GMT-4": -4, "GMT-5": -5,
}

def adjust_timezone(df, target_tz=None):
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

def _fetch_yahoo(symbol, interval="1h", period="3mo", start_date=None, end_date=None):
    try:
        import yfinance as yf
    except ImportError:
        return None

    tf = _timeframe_yahoo(interval)
    try:
        if start_date and end_date:
            df = yf.download(symbol, start=start_date, end=end_date, interval=tf, progress=False, auto_adjust=False)
        else:
            df = yf.download(symbol, period=period, interval=tf, progress=False, auto_adjust=False)
            
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        if df is None or df.empty:
            return None
        df.rename(columns={"open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume"}, inplace=True)
        return df
    except Exception:
        return None

def _fetch_twelve(symbol, interval="1h", period="3mo", start_date=None, end_date=None):
    try:
        from twelvedata import TDClient
    except ImportError:
        return None

    td = TDClient(apikey=TWELVE_DATA_API_KEY)
    tf = _timeframe_twelve(interval)
    sym = _symbol_twelve(symbol)

    kwargs = {"symbol": sym, "interval": tf, "timezone": "UTC"}

    if start_date and end_date:
        kwargs["start_date"] = start_date
        kwargs["end_date"] = end_date
    else:
        kwargs["outputsize"] = 5000

    try:
        ts = td.time_series(**kwargs)
        df = ts.as_pandas()
        if df is None or df.empty:
            return None
        df = df.iloc[::-1]
        df.rename(columns={"open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume"}, inplace=True)
        time.sleep(8) 
        return df
    except Exception:
        return None

def fetch_data(symbol, interval="1h", period="3mo", start_date=None, end_date=None, cache_hours=None, **kwargs):
    if PROVIDER == "twelve_data":
        df = _fetch_twelve(symbol, interval, period, start_date, end_date)
    else:
        df = _fetch_yahoo(symbol, interval, period, start_date, end_date)
    
    if df is not None and not df.empty:
        df = adjust_timezone(df)
    return df
