# -*- coding: utf-8 -*-
"""
DATA PROVIDER — Yahoo Finance ama Twelve Data
"""
import pandas as pd
import streamlit as st
from datetime import datetime, timedelta

# ══════════════════════════════════════════════════════════════════════════════
# 🎛️ DOORASHADA PROVIDER
# ══════════════════════════════════════════════════════════════════════════════
PROVIDER = "twelve_data"  # ← "yahoo" ama "twelve_data"

# ══════════════════════════════════════════════════════════════════════════════
# 🔑 API KEY — Twelve Data
# ══════════════════════════════════════════════════════════════════════════════
TWELVE_DATA_API_KEY = "951d7884292c4734aee5e4fc82878dc3 "  # ← Copy key-gaaga halkan


# ══════════════════════════════════════════════════════════════════════════════
# 🛠️ HELPERS — Timeframe + Symbol Conversion
# ══════════════════════════════════════════════════════════════════════════════
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
    """Yahoo → Twelve Data format."""
    s = str(symbol).upper().strip()
    # Crypto
    if "-USD" in s:
        return s.replace("-USD", "/USD")
    if s in ["BTC-USD", "ETH-USD"]:
        return s.replace("-USD", "/USD")
    # Gold / Silver
    if s in ["GC=F", "XAUUSD", "XAUUSD=X", "GOLD"]:
        return "XAU/USD"
    if s in ["SI=F", "XAGUSD", "XAGUSD=X", "SILVER"]:
        return "XAG/USD"
    # Forex
    if s.endswith("=X"):
        s = s.replace("=X", "")
        if len(s) == 6:
            return f"{s[:3]}/{s[3:]}"
        return s
    # Forex without =X (EURUSD)
    if len(s) == 6 and s.isalpha():
        return f"{s[:3]}/{s[3:]}"
    return s


# ══════════════════════════════════════════════════════════════════════════════
# 📡 YAHOO FINANCE
# ══════════════════════════════════════════════════════════════════════════════
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


# ══════════════════════════════════════════════════════════════════════════════
# 📡 TWELVE DATA
# ══════════════════════════════════════════════════════════════════════════════
def _fetch_twelve_data(symbol, interval="1h", period="3mo",
                       start_date=None, end_date=None, count=5000):
    """Twelve Data (bilaash: 800 calls/maalin, 8 calls/daqiiqo)."""
    try:
        import requests
    except ImportError:
        raise ImportError("Ku shub: pip install requests")

    if TWELVE_DATA_API_KEY == "HALKAN_GELI_KEY_GAAGA":
        raise ValueError("❌ Geli TWELVE_DATA_API_KEY ee data_provider.py")

    td_symbol = _symbol_twelve(symbol)
    tf = _timeframe_twelve(interval)

    url = "https://api.twelvedata.com/time_series"

    params = {
        "symbol": td_symbol,
        "interval": tf,
        "outputsize": count,
        "apikey": TWELVE_DATA_API_KEY,
        "order": "ASC",
        "timezone": "UTC",
    }

    # Haddii taariikhda la bixiyay, isticmaal start_date/end_date
    if start_date and end_date:
        params["start_date"] = start_date
        params["end_date"] = end_date
        params.pop("outputsize", None)

    try:
        r = requests.get(url, params=params, timeout=30)
        data = r.json()

        # Hubi khaladaad
        if data.get("status") == "error":
            msg = data.get("message", "Unknown error")
            if "API key" in msg or "apikey" in msg.lower():
                raise ValueError(f"🔑 API key khalad: {msg}")
            if "limit" in msg.lower() or "credits" in msg.lower():
                raise ValueError(f"⚠️ Rate limit: {msg}")
            raise ValueError(f"Twelve Data: {msg}")

        if "values" not in data:
            return None

        df = pd.DataFrame(data["values"])
        df["datetime"] = pd.to_datetime(df["datetime"])
        df.set_index("datetime", inplace=True)
        df.rename(columns={
            "open": "Open", "high": "High", "low": "Low",
            "close": "Close", "volume": "Volume",
        }, inplace=True)

        for col in ["Open", "High", "Low", "Close"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        if "Volume" in df.columns:
            df["Volume"] = pd.to_numeric(df["Volume"], errors="coerce").fillna(0)
        else:
            df["Volume"] = 0

        df = df.sort_index()
        return df

    except requests.exceptions.Timeout:
        raise ValueError("⏱️ Twelve Data timeout")
    except requests.exceptions.RequestException as e:
        raise ValueError(f"🌐 Network: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# 🎯 MAIN — Isticmaal tan
# ══════════════════════════════════════════════════════════════════════════════
def fetch_data(symbol, interval="1h", period="3mo",
               start_date=None, end_date=None,
               cache_hours=1, live=False):
    """
    Soo qaado xogta — Provider-ka la doortay.

    Args:
        symbol: Yahoo format (EURUSD=X, BTC-USD)
        interval: 1m, 5m, 15m, 30m, 1h, 4h, 1d
        period: 1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max
        start_date, end_date: YYYY-MM-DD (optional)
        cache_hours: Cache duration
        live: True = real-time mode (skip cache)
    """
    # Cache key
    cache_key = f"data_{symbol}_{interval}_{period}_{start_date}_{end_date}_{PROVIDER}"
    time_key = f"data_time_{symbol}_{interval}_{period}_{start_date}_{end_date}_{PROVIDER}"

    # Hubi cache (haddii aan live ahayn)
    if not live and cache_hours > 0 and cache_key in st.session_state:
        cache_time = st.session_state.get(time_key)
        if cache_time:
            age = datetime.now() - cache_time
            if age < timedelta(hours=cache_hours):
                return st.session_state[cache_key]

    # Fetch
    try:
        if PROVIDER == "twelve_data":
            df = _fetch_twelve_data(symbol, interval, period, start_date, end_date)
        else:
            df = _fetch_yahoo(symbol, interval, period, start_date, end_date)

        # Cache
        if df is not None and cache_hours > 0:
            st.session_state[cache_key] = df
            st.session_state[time_key] = datetime.now()

        return df

    except Exception as e:
        # Fallback: isticmaal cache hore
        if cache_key in st.session_state:
            st.warning(f"⚠️ Provider fashilmay, cache ayaa la isticmaalayaa: {e}")
            return st.session_state[cache_key]
        raise e


def get_provider_info():
    """Xogta provider-ka."""
    if PROVIDER == "twelve_data":
        return {
            "name": "Twelve Data",
            "status": "🟢 Active",
            "api_key": "✅" if TWELVE_DATA_API_KEY != "HALKAN_GELI_KEY_GAAGA" else "❌ Maqan",
            "rate_limit": "800 calls/maalin | 8 calls/daqiiqo",
            "timezone": "UTC",
            "quality": "~70% MT5",
        }
    return {
        "name": "Yahoo Finance",
        "status": "🟢 Active",
        "api_key": "N/A",
        "rate_limit": "Xad aan la garanayn",
        "timezone": "UTC",
        "quality": "~50% MT5",
    }
