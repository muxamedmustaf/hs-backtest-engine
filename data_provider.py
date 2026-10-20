# -*- coding: utf-8 -*-
import pandas as pd
import streamlit as st
from datetime import datetime
import time
import base64
import io

try:
    from github import Github
    HAS_GITHUB = True
except ImportError:
    HAS_GITHUB = False

PROVIDER = "twelve_data"
TWELVE_DATA_API_KEY = "951d7884292c4734aee5e4fc82878dc3" 
TARGET_TIMEZONE = "GMT+2"

GITHUB_TOKEN = st.secrets.get("GITHUB_TOKEN", "YOUR_GITHUB_TOKEN_HERE")
GITHUB_REPO = st.secrets.get("GITHUB_REPO", "muxamedmustaf/hs-backtest-engine")
DATA_BRANCH = "main"
DATA_FOLDER = "market_data"

def get_github_repo():
    if not HAS_GITHUB or GITHUB_TOKEN == "YOUR_GITHUB_TOKEN_HERE": return None
    try:
        g = Github(GITHUB_TOKEN)
        return g.get_repo(GITHUB_REPO)
    except Exception: return None

def load_from_github(symbol, interval):
    repo = get_github_repo()
    if repo is None: return None
    file_path = f"{DATA_FOLDER}/{symbol.replace('=','_').replace('-','_')}_{interval}.parquet"
    try:
        contents = repo.get_contents(file_path, ref=DATA_BRANCH)
        decoded = base64.b64decode(contents.content)
        df = pd.read_parquet(io.BytesIO(decoded))
        return df
    except Exception: return None

def save_to_github(symbol, interval, df):
    repo = get_github_repo()
    if repo is None: return False
    file_path = f"{DATA_FOLDER}/{symbol.replace('=','_').replace('-','_')}_{interval}.parquet"
    buffer = io.BytesIO()
    df.to_parquet(buffer, engine='pyarrow')
    content = base64.b64encode(buffer.getvalue()).decode('utf-8')
    try:
        contents = repo.get_contents(file_path, ref=DATA_BRANCH)
        repo.update_file(contents.path, f"Update {symbol} {interval}", content, contents.sha, branch=DATA_BRANCH)
    except Exception:
        try: repo.create_file(file_path, f"Create {symbol} {interval}", content, branch=DATA_BRANCH)
        except Exception as e:
            st.error(f"فشل حفظ البيانات في GitHub: {e}"); return False
    return True

def adjust_timezone(df):
    if df is None or df.empty: return df
    df = df.copy()
    df.index = df.index + pd.Timedelta(hours=2)
    return df

def _timeframe_twelve(tf):
    return {"1m": "1min", "5m": "5min", "15m": "15min", "30m": "30min", "1h": "1h", "4h": "4h", "1d": "1day"}.get(tf, "1h")

def _symbol_twelve(symbol):
    s = str(symbol).upper().strip()
    if "-USD" in s: return s.replace("-USD", "/USD")
    if s.endswith("=X"):
        s = s.replace("=X", "")
        if len(s) == 6: return f"{s[:3]}/{s[3:]}"
        return s
    if len(s) == 6 and s.isalpha(): return f"{s[:3]}/{s[3:]}"
    return s

def _fetch_twelve(symbol, interval="1h", start_date=None, end_date=None):
    try:
        from twelvedata import TDClient
    except ImportError: return None

    td = TDClient(apikey=TWELVE_DATA_API_KEY)
    tf = _timeframe_twelve(interval)
    sym = _symbol_twelve(symbol)
    
    kwargs = {"symbol": sym, "interval": tf, "timezone": "UTC", "outputsize": 5000}

    if start_date and end_date:
        kwargs["start_date"] = start_date
        kwargs["end_date"] = end_date
        kwargs.pop("outputsize", None) 

    try:
        ts = td.time_series(**kwargs)
        df = ts.as_pandas()
        if df is None or df.empty: return None
        df = df.iloc[::-1]
        df.rename(columns={"open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume"}, inplace=True)
        time.sleep(8) 
        return df
    except Exception as e: 
        return None

def fetch_data(symbol, interval="1h", period="3mo", start_date=None, end_date=None, cache_hours=None, force_download=False, **kwargs):
    df_github = load_from_github(symbol, interval)
    
    # 🚨 الشرط الذكي: إذا كانت البيانات المحفوظة أقل من 100 شمعة، اعتبرها تالفة واجلب من الإنترنت
    if df_github is not None and len(df_github) < 100:
        force_download = True

    # إذا لم نطلب تحديثاً، ولدينا بيانات كافية، نرجعها
    if not force_download and df_github is not None and not df_github.empty:
        return adjust_timezone(df_github)

    # جلب 5000 شمعة جديدة
    if force_download:
        df_new = _fetch_twelve(symbol, interval, None, None)
    else:
        fetch_start = start_date
        if df_github is not None and not df_github.empty:
            last_date = df_github.index.max()
            fetch_start = (last_date + pd.Timedelta(minutes=1)).strftime('%Y-%m-%d %H:%M:%S')
        df_new = _fetch_twelve(symbol, interval, fetch_start, end_date)
    
    if df_new is not None and not df_new.empty:
        if force_download:
            df_merged = df_new 
        elif df_github is not None and not df_github.empty:
            df_merged = pd.concat([df_github, df_new]).drop_duplicates().sort_index()
        else: 
            df_merged = df_new
        
        save_to_github(symbol, interval, df_merged)
        return adjust_timezone(df_merged)
        
    return adjust_timezone(df_github)
