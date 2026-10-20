# -*- coding: utf-8 -*-
import calendar, datetime
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
import numpy as np
from data_provider import fetch_data, get_github_repo

try:
    from engine import run_full_analysis, backtest_strategy, REASON_MAP, diagnose_no_signals, diagnose_filters
except ImportError as e:
    st.error(f"❌ فشل الاستيراد من engine: {e}"); st.stop()

try:
    from ffff import get_symbols_from_sheet
except ImportError:
    def get_symbols_from_sheet(*args, **kwargs): return [["EURUSD=X", "BTC-USD"]]

st.set_page_config(page_title="Box Hunter Pro", page_icon="📦", layout="wide")

st.markdown("""
<head><meta charset="UTF-8"></head>
<style>
    .main .block-container { max-width: 100% !important; padding: 0.5rem 1rem !important; }
    html, body, [class*="css"] { direction: rtl; text-align: right; font-size: 15px; }
    h1, h2, h3, h4, h5, h6 { direction: rtl; text-align: right; }
    label, .stRadio label, .stTextInput label, .stSelectbox label { direction: rtl; text-align: right; }
    .js-plotly-plot .plotly, .js-plotly-plot .plotly .main-svg { touch-action: none !important; } 
</style>
""", unsafe_allow_html=True)

SHEET_ID = "1TXvF6RhSgfJ631UpnWB38Ww1OMvZVx7VonDB_y1pO3s"
ALL_GLOBAL_INTERVALS = ["1m", "5m", "15m", "30m", "1h", "4h", "1d"]
ALL_PERIODS = ["1mo", "3mo", "6mo", "1y", "2y", "5y", "max"]

IC_MARKETS_SPECS = {"BTC-USD": {"pip": 1.0}, "EURUSD": {"pip": 0.0001}, "GBPUSD": {"pip": 0.0001}}
PLOTLY_CONFIG = {'responsive': True, 'scrollZoom': True, 'displaylogo': False, 'displayModeBar': True, 'dragmode': 'pan', 'doubleClick': 'reset+autosize'}

def fix_symbol(sym):
    sym = str(sym).strip().upper()
    if sym in ("XAUUSD", "GOLD"): return "GC=F"
    if len(sym) == 6 and sym.isalpha(): return f"{sym}=X"
    return sym

def pip_size_for(symbol):
    s = str(symbol).upper()
    for key, spec in IC_MARKETS_SPECS.items():
        if key.upper() == s: return spec["pip"]
    return 0.0001

def get_available_symbols():
    s = set(IC_MARKETS_SPECS.keys())
    try:
        sheet_symbols = get_symbols_from_sheet(SHEET_ID, "GOLD", "TOKENS")
        if sheet_symbols and isinstance(sheet_symbols, list) and len(sheet_symbols) > 0:
            for x in sheet_symbols[0]: s.add(str(x).strip().upper())
    except Exception: pass
    return sorted(s)

@st.cache_data(ttl=3600, show_spinner=False)
def _cached_fetch(symbol, interval, start_date=None, end_date=None, period=None, force_download=False):
    try:
        if start_date and end_date: return fetch_data(symbol, interval=interval, start_date=start_date, end_date=end_date, force_download=force_download)
        return fetch_data(symbol, interval=interval, period=period)
    except Exception: return None

@st.cache_data(ttl=3600, show_spinner=False)
def _cached_backtest(symbol, interval, start_date, end_date):
    df = _cached_fetch(symbol, interval, start_date, end_date, None)
    if df is None or df.empty: return None, None
    try: trades = backtest_strategy(df, interval=interval, symbol=symbol)
    except Exception: return df, None
    return df, trades

@st.cache_data(ttl=1800, show_spinner=False)
def _cached_live(symbol, interval, period):
    df = _cached_fetch(symbol, interval, None, None, period)
    if df is None or df.empty: return None, None
    try: res = run_full_analysis(df, interval=interval, symbol=symbol)
    except Exception: return df, None
    return df, res

@st.cache_data(ttl=3600, show_spinner=False)
def _prepare_chart_data(symbol, interval, start_date, end_date):
    df = _cached_fetch(symbol, interval, start_date, end_date, None)
    if df is None or df.empty: return None
    df = df.copy()
    df["EMA50"] = df["Close"].ewm(span=50, adjust=False).mean()
    df["EMA200"] = df["Close"].ewm(span=200, adjust=False).mean()
    return df

def compute_pips(df):
    if df is None or df.empty: return df
    df = df.copy()
    def _f(v): return float(v) if pd.notna(v) else None
    pips_l = []
    for _, row in df.iterrows():
        pip = pip_size_for(row.get("symbol") or row.get("Symbol") or "")
        e, x = _f(row.get("Entry Price")), _f(row.get("Exit Price"))
        bias = str(row.get("bias") or "").upper()
        is_sell = "BEAR" in bias
        p = (e - x) / pip if (e and x and is_sell) else (x - e) / pip if (e and x) else None
        pips_l.append(round(p, 1) if p is not None else None)
    df["Pips"] = pips_l
    return df

def compute_dollar_pnl(df, lot=0.01):
    if df is None or df.empty: return df
    df = df.copy()
    usd = []
    for _, row in df.iterrows():
        sym = str(row.get("symbol") or "").upper()
        try: e, x = float(row.get("Entry Price")), float(row.get("Exit Price"))
        except: usd.append(None); continue
        move = (x - e) if "BEAR" not in str(row.get("bias")).upper() else (e - x)
        if "BTC" in sym: pnl = move * lot
        elif "XAU" in sym: pnl = move * lot * 100
        elif sym.endswith("USD"): pnl = move * lot * 100000
        else: pnl = move * lot * 100000 / x if x else None
        usd.append(round(pnl, 2) if pnl is not None else None)
    df["PnL_USD"] = usd
    return df

def draw_box_pattern(fig, source):
    if source is None: return
    nodes = source.get("nodes", [])
    box_nodes = source.get("neckline_nodes", [])
    if len(nodes) < 3 or len(box_nodes) < 4: return

    fig.add_trace(go.Scatter(x=[nodes[0][0], nodes[1][0]], y=[nodes[0][1], nodes[1][1]], mode="lines", name="Trend", line=dict(color="#FF9800", width=2, dash="dot")), row=1, col=1)
    top_x, top_y = [box_nodes[0][0], box_nodes[1][0]], [box_nodes[0][1], box_nodes[1][1]]
    bot_x, bot_y = [box_nodes[2][0], box_nodes[3][0]], [box_nodes[2][1], box_nodes[3][1]]
    
    fig.add_trace(go.Scatter(x=top_x, y=top_y, mode="lines", name="Resistance", line=dict(color="#2196F3", width=2)), row=1, col=1)
    fig.add_trace(go.Scatter(x=bot_x, y=bot_y, mode="lines", name="Support", line=dict(color="#2196F3", width=2)), row=1, col=1)
    fig.add_trace(go.Scatter(x=[top_x[0], bot_x[0]], y=[top_y[0], bot_y[0]], mode="lines", line=dict(color="#B0BEC5", width=1), showlegend=False), row=1, col=1)
    fig.add_trace(go.Scatter(x=[top_x[1], bot_x[1]], y=[top_y[1], bot_y[1]], mode="lines", line=dict(color="#B0BEC5", width=1), showlegend=False), row=1, col=1)
    fig.add_trace(go.Scatter(x=[nodes[2][0]], y=[nodes[2][1]], mode="markers+text", name="Breakout", marker=dict(size=14, color="#E91E63", symbol="star"), text=["كسر"], textposition="top center"), row=1, col=1)

def render_chart_fast(sym, cur, df_chart_full, chart_mode):
    if df_chart_full is None or df_chart_full.empty: return
    nodes = cur.get("nodes", [])
    if not nodes: return
    
    pattern_start, pattern_end = nodes[0][0], nodes[-1][0]
    span = pattern_end - pattern_start
    
    if chart_mode == "adaptive":
        x_min = pattern_start - span * 1.5
        x_max = pattern_end + span * 1.5
        try:
            idx_min = max(0, df_chart_full.index.searchsorted(x_min))
            idx_max = min(len(df_chart_full), df_chart_full.index.searchsorted(x_max))
            df_window = df_chart_full.iloc[idx_min:idx_max].copy()
            if len(df_window) > 250:
                mid = len(df_window) // 2
                df_window = df_window.iloc[max(0, mid-125):min(len(df_window), mid+125)]
        except: df_window = df_chart_full.tail(150).copy()
    else:
        df_window = df_chart_full.copy()
        x_min = df_window.index[0] if not df_window.empty else pattern_start
        x_max = df_window.index[-1] if not df_window.empty else pattern_end

    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.8, 0.2])
    fig.add_trace(go.Candlestick(x=df_window.index, open=df_window["Open"], high=df_window["High"], low=df_window["Low"], close=df_window["Close"], name="Price"), row=1, col=1)
    
    if "EMA50" in df_window.columns: fig.add_trace(go.Scatter(x=df_window.index, y=df_window["EMA50"], line=dict(color="orange", width=1), name="EMA 50"), row=1, col=1)
    if "EMA200" in df_window.columns: fig.add_trace(go.Scatter(x=df_window.index, y=df_window["EMA200"], line=dict(color="blue", width=1), name="EMA 200"), row=1, col=1)
    
    draw_box_pattern(fig, cur)
    
    if "Volume" in df_window.columns:
        fig.add_trace(go.Bar(x=df_window.index, y=df_window["Volume"], name="Volume", marker_color='rgba(158, 158, 158, 0.5)'), row=2, col=1)
    
    fig.update_layout(
        template="plotly_white", height=700, autosize=True, xaxis_rangeslider_visible=False, 
        dragmode="pan", hovermode="x unified", margin=dict(l=10, r=60, t=30, b=30), 
        yaxis=dict(side="right", showgrid=True, gridcolor="#EEEEEE", fixedrange=False, automargin=True),
        yaxis2=dict(side="right", showgrid=False, fixedrange=False, automargin=True),
        xaxis=dict(showgrid=True, gridcolor="#F5F5F5", range=[x_min, x_max], fixedrange=False),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5)
    )
    st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)

app_mode = st.radio("وضع التطبيق:", ["🚀 الماسح الحي", "🧪 مختبر الاختبار الرجعي"], horizontal=True)

# 🎯 القائمة الجانبية
with st.sidebar:
    st.markdown("### ⚙️ إدارة البيانات (GitHub)")
    repo = get_github_repo()
    if repo:
        st.success(f"✅ متصل بـ: {repo.full_name}")
        if st.button("📥 تحديث وحفظ البيانات (الكل)", use_container_width=True):
            av = get_available_symbols()[:10]
            intervals = ["1h", "4h"]
            progress_bar = st.progress(0)
            for i, sym in enumerate(av):
                for intv in intervals:
                    _cached_fetch(fix_symbol(sym), intv, start_date="2020-01-01", end_date=datetime.datetime.now().strftime("%Y-%m-%d"), force_download=True)
                progress_bar.progress((i+1)/len(av))
            st.cache_data.clear()
            st.success("✅ تم التحديث والحفظ في GitHub!")
    else:
        st.warning("⚠️ لم يتم ربط GitHub. يرجى إضافة التوكن في الإعدادات.")

st.markdown("---")

if app_mode == "🧪 مختبر الاختبار الرجعي":
    st.markdown("### 🧪 مختبر الصناديق")
    bt_mode = st.radio("طريقة الفحص:", ["سهم فردي", "🎯 مجموعة"], horizontal=True)
    bt_symbols = [st.text_input("رمز الأصل", value="BTC-USD")] if bt_mode == "سهم فردي" else st.multiselect("اختر:", get_available_symbols(), default=["BTC-USD"])

    now = datetime.datetime.now()
    c1, c2, c3 = st.columns(3)
    sd = c1.date_input("من:", value=datetime.date(now.year-1, 1, 1)).strftime("%Y-%m-%d")
    ed = c2.date_input("إلى:", value=datetime.date.today()).strftime("%Y-%m-%d")
    interval = c3.selectbox("الإطار:", ALL_GLOBAL_INTERVALS, index=4)
    
    if st.button("📊 بدء المحاكاة", use_container_width=True) and bt_symbols:
        results, dfs = [], {}
        bar = st.progress(0)
        for i, sym in enumerate(bt_symbols):
            bar.progress((i+1)/len(bt_symbols))
            df, trades = _cached_backtest(fix_symbol(sym), interval, sd, ed)
            if df is not None:
                dfs[sym] = df
                if trades:
                    tdf = pd.DataFrame(trades)
                    results.append({"symbol": sym, "trades_df": tdf, "total": len(tdf)})
        st.session_state["bt_results"] = results
        st.session_state["bt_dfs"] = dfs
        st.session_state["bt_sd"], st.session_state["bt_ed"], st.session_state["bt_int"] = sd, ed, interval

    if "bt_results" in st.session_state and st.session_state["bt_results"]:
        rl = st.session_state["bt_results"]
        all_dfs = [r["trades_df"] for r in rl if not r["trades_df"].empty]
        
        if all_dfs:
            tab1, tab2 = st.tabs(["📉 الرسوم البيانية", "🧠 التشخيص"])
            with tab2: st.info("قيد التطوير")
            with tab1:
                opts = [f"{r['symbol']} ({r['total']})" for r in rl]
                ai = rl[opts.index(st.selectbox("اختر الأصل:", opts))]
                sym, tdf = ai["symbol"], ai["trades_df"]
                if not tdf.empty:
                    chart_mode_label = st.radio("نطاق الرسم:", ["📉 الرسم المتكيف (سريع جداً)", "🗺️ كامل الفترة (قد يكون بطيئاً)"], horizontal=True)
                    chart_mode = "adaptive" if "المتكيف" in chart_mode_label else "full"
                    
                    si = st.session_state.get(f"signal_index_{sym}", len(tdf)-1)
                    n1, n2, n3 = st.columns([1, 2, 1])
                    with n1:
                        if st.button("⬅️ السابق", use_container_width=True): st.session_state[f"signal_index_{sym}"] = max(0, si - 1); st.rerun()
                    with n2:
                        st.markdown(f"<div style='text-align:center;padding-top:8px;font-weight:bold;'>إشارة {si+1} من {len(tdf)}</div>", unsafe_allow_html=True)
                    with n3:
                        if st.button("التالي ➡️", use_container_width=True): st.session_state[f"signal_index_{sym}"] = min(len(tdf)-1, si + 1); st.rerun()
                            
                    cur = tdf.iloc[si]
                    st.write(cur.get("Trade Recommendation", ""))
                    df_chart = _prepare_chart_data(fix_symbol(sym), st.session_state["bt_int"], st.session_state["bt_sd"], st.session_state["bt_ed"])
                    render_chart_fast(sym, cur, df_chart, chart_mode)

else:
    st.markdown("### 🚀 الماسح الحي")
    live_mode = st.radio("طريقة الفحص:", ["سهم فردي", "🎯 مجموعة"], horizontal=True, key="live_mode_radio")
    symbols = [st.text_input("رمز:", value="BTC-USD", key="live_sym_input")] if live_mode == "سهم فردي" else st.multiselect("اختر العملات:", get_available_symbols(), default=["BTC-USD"])

    interval = st.selectbox("الإطار:", ALL_GLOBAL_INTERVALS, index=4)
    period = st.selectbox("النطاق:", ALL_PERIODS, index=2)
    
    if st.button("🚀 بدء المسح", use_container_width=True) and symbols:
        valid = []
        for sym in symbols:
            df, res = _cached_live(fix_symbol(sym), interval, period)
            if res and res.get("signal") in ("STRONG BUY", "STRONG SELL"):
                valid.append({"symbol": sym, "result": res})
        if valid:
            st.success(f"تم العثور على {len(valid)} إشارة")
            si = st.session_state.get("live_signal_index", 0)
            
            n1, n2, n3 = st.columns([1, 2, 1])
            with n1:
                if st.button("⬅️ السابق", use_container_width=True): st.session_state["live_signal_index"] = max(0, si - 1); st.rerun()
            with n2:
                st.markdown(f"<div style='text-align:center;padding-top:8px;font-weight:bold;'>إشارة {si+1} من {len(valid)}</div>", unsafe_allow_html=True)
            with n3:
                if st.button("التالي ➡️", use_container_width=True): st.session_state["live_signal_index"] = min(len(valid)-1, si + 1); st.rerun()

            ar, sym = valid[si]["result"], valid[si]["symbol"]
            st.write(f"**{sym}** - {ar['signal']}")
            df_chart = _prepare_chart_data(fix_symbol(sym), interval, None, None)
            if df_chart is not None: render_chart_fast(sym, ar, df_chart, "adaptive")
