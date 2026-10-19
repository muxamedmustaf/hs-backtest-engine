# -*- coding: utf-8 -*-
import calendar, datetime
import streamlit as st
import plotly.graph_objects as go
import pandas as pd
import numpy as np
from data_provider import fetch_data

try:
    from engine import run_full_analysis, backtest_strategy, diagnose_no_signals, diagnose_filters
except ImportError as e:
    st.error(f"❌ فشل استيراد المحرك: {e}")
    st.stop()

try:
    from ffff import get_symbols_from_sheet
except ImportError:
    def get_symbols_from_sheet(*args, **kwargs): return [["EURUSD=X", "BTC-USD"]]

st.set_page_config(page_title="Box Breakout Hunter", page_icon="📦", layout="wide")

st.markdown("""
<style>
    .main .block-container { max-width: 100% !important; padding: 0.5rem 1rem !important; }
    html, body, [class*="css"] { direction: rtl; text-align: right; font-size: 15px; }
    h1, h2, h3, h4, h5, h6 { direction: rtl; text-align: right; }
    div[data-testid="stMetricLabel"] { direction: rtl; text-align: right; }
    div[data-testid="stMetricValue"] { direction: ltr; text-align: right; }
    .stDataFrame { direction: ltr; }
</style>
""", unsafe_allow_html=True)

ALL_GLOBAL_INTERVALS = ["15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d", "1wk"]
PLOTLY_CONFIG = {'responsive': True, 'scrollZoom': True, 'displaylogo': False}

def fix_symbol(sym):
    sym = str(sym).strip().upper()
    if sym in ("XAUUSD", "GOLD"): return "GC=F"
    if len(sym) == 6 and sym.isalpha(): return f"{sym}=X"
    return sym

@st.cache_data(ttl=3600, show_spinner=False)
def _cached_fetch(symbol, interval, start_date=None, end_date=None, period=None):
    try:
        if start_date and end_date:
            return fetch_data(symbol, interval=interval, start_date=start_date, end_date=end_date, cache_hours=1)
        return fetch_data(symbol, interval=interval, period=period, cache_hours=1)
    except Exception:
        return None

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

@st.cache_data(ttl=3600, show_spinner=False)
def _cached_diagnose_no_signals(symbol, interval, start_date, end_date):
    df = _cached_fetch(symbol, interval, start_date, end_date, None)
    if df is not None and not df.empty: return diagnose_no_signals(df, interval=interval)
    return None

# ══════════════════════════════════════════════════════════════════════════════
# 🎨 دالة رسم الصندوق (Box Breakout)
# ══════════════════════════════════════════════════════════════════════════════
def draw_box_pattern(fig, source, df):
    if source is None: return
    nodes = source.get("nodes", [])
    if len(nodes) < 3: return

    # رسم خط الحركة السابقة
    trend_x = [nodes[0][0], nodes[1][0]]
    trend_y = [nodes[0][1], nodes[1][1]]
    fig.add_trace(go.Scatter(x=trend_x, y=trend_y, mode="lines", name="Trend", line=dict(color="#FF9800", width=2, dash="dot")))

    # رسم الصندوق (Box)
    box_x = [n[0] for n in source.get("neckline_nodes", [])]
    box_y = [n[1] for n in source.get("neckline_nodes", [])]
    
    # إذا كانت الإحداثيات 4 نقاط للصندوق
    if len(box_x) == 4:
        # نرسم مستطيل
        fig.add_shape(type="rect",
            x0=box_x[0], y0=box_y[2], x1=box_x[1], y1=box_y[0],
            line=dict(color="#2196F3", width=2),
            fillcolor="rgba(33, 150, 243, 0.1)",
        )

    # رسم نقطة الاختراق
    fig.add_trace(go.Scatter(
        x=[nodes[2][0]], y=[nodes[2][1]],
        mode="markers+text", name="Breakout",
        marker=dict(size=15, color="#E91E63", symbol="star"),
        text=["Breakout"], textposition="top center"
    ))

    # رسم SL و TP
    entry = source.get("entry")
    sl = source.get("sl")
    tp = source.get("tp")
    entry_x = nodes[2][0]
    
    if entry and sl:
        fig.add_annotation(x=entry_x, y=sl, text=f"SL ({sl})", showarrow=True, arrowhead=1, ax=20, ay=20, font=dict(color="red"))
    if entry and tp:
        fig.add_annotation(x=entry_x, y=tp, text=f"TP ({tp})", showarrow=True, arrowhead=1, ax=20, ay=-20, font=dict(color="green"))

# ══════════════════════════════════════════════════════════════════════════════
# 🎯 دالة رسم الشارت
# ══════════════════════════════════════════════════════════════════════════════
def render_chart_fast(sym, cur, df_chart_full):
    if df_chart_full is None or df_chart_full.empty: return
    nodes = cur.get("nodes", [])
    if not nodes: return
    
    pattern_start = nodes[0][0]
    pattern_end = nodes[-1][0]
    span = pattern_end - pattern_start
    
    x_min = pattern_start - span * 1.5
    x_max = pattern_end + span * 2.0
    
    try:
        idx_min = max(0, df_chart_full.index.searchsorted(x_min))
        idx_max = min(len(df_chart_full), df_chart_full.index.searchsorted(x_max))
        df_window = df_chart_full.iloc[idx_min:idx_max]
    except: df_window = df_chart_full
    
    fig = go.Figure(data=[go.Candlestick(
        x=df_window.index, open=df_window["Open"], high=df_window["High"],
        low=df_window["Low"], close=df_window["Close"], name="Price"
    )])
    
    if "EMA50" in df_window.columns: fig.add_trace(go.Scatter(x=df_window.index, y=df_window["EMA50"], line=dict(color="orange", width=1), name="EMA 50"))
    if "EMA200" in df_window.columns: fig.add_trace(go.Scatter(x=df_window.index, y=df_window["EMA200"], line=dict(color="blue", width=1), name="EMA 200"))
    
    draw_box_pattern(fig, cur, df_window)
    
    fig.update_layout(
        template="plotly_white", height=700, autosize=True,
        xaxis_rangeslider_visible=False, dragmode="pan", hovermode="x unified",
        yaxis=dict(side="left", showgrid=True, gridcolor="#EEEEEE"),
        xaxis=dict(showgrid=True, gridcolor="#F5F5F5", range=[x_min, x_max]),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5)
    )
    st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)

# ══════════════════════════════════════════════════════════════════════════════
# 📊 التقرير المالي
# ══════════════════════════════════════════════════════════════════════════════
def render_financial_report(df, lot_size=0.01, symbol="—", period="—"):
    st.markdown("### 📊 التقرير المالي")
    if df is None or df.empty: st.info("لا صفقات"); return
    
    # (تبسيط الحسابات للسرعة)
    s = df["Result"].astype(str).str.upper() if "Result" in df.columns else pd.Series()
    w, l = len(df[s.str.contains("WIN")]), len(df[s.str.contains("LOSS")])
    total = len(df)
    wr = round(w/(w+l)*100, 1) if (w+l)>0 else 0
    
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("الصفقات", total)
    c2.metric("رابحة", w, f"{wr}%")
    c3.metric("خاسرة", l)
    c4.metric("مفتوحة/تعادل", total - w - l)
    
    csv = df.to_csv(index=False).encode('utf-8-sig')
    st.download_button("📥 تنزيل CSV", csv, f"backtest_{symbol}_{period}.csv", "text/csv", type="primary")

# ══════════════════════════════════════════════════════════════════════════════
# 📱 الواجهة الرئيسية
# ══════════════════════════════════════════════════════════════════════════════
app_mode = st.radio("وضع التطبيق:", ["🚀 الماسح الحي", "🧪 مختبر الاختبار الرجعي"], horizontal=True)
st.markdown("---")

if app_mode == "🧪 مختبر الاختبار الرجعي":
    st.markdown("### 🧪 مختبر الصناديق (Box Backtest)")
    
    bt_mode = st.radio("طريقة الفحص:", ["سهم فردي", "🎯 مجموعة"], horizontal=True)
    bt_symbols = []
    if bt_mode == "سهم فردي":
        bt_symbols = [st.text_input("رمز الأصل", value="BTC-USD")]
    else:
        bt_symbols = st.multiselect("اختر العملات:", ["BTC-USD", "GBPUSD=X", "EURUSD=X", "ETH-USD"], default=["BTC-USD"])

    now = datetime.datetime.now()
    c1, c2, c3 = st.columns(3)
    sd = c1.date_input("من:", value=datetime.date(now.year-1, 1, 1)).strftime("%Y-%m-%d")
    ed = c2.date_input("إلى:", value=datetime.date.today()).strftime("%Y-%m-%d")
    interval = c3.selectbox("الإطار الزمني:", ALL_GLOBAL_INTERVALS, index=4)
    
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
                    tdf["symbol"] = sym
                    results.append({"symbol": sym, "trades_df": tdf, "total": len(tdf)})
                else:
                    results.append({"symbol": sym, "trades_df": pd.DataFrame(), "total": 0})
        
        st.session_state["bt_results"] = results
        st.session_state["bt_dfs"] = dfs
        st.session_state["bt_sd"] = sd
        st.session_state["bt_ed"] = ed
        st.session_state["bt_int"] = interval

    if "bt_results" in st.session_state and st.session_state["bt_results"]:
        rl = st.session_state["bt_results"]
        dfs_dict = st.session_state["bt_dfs"]
        
        # التشخيص
        no_sig = [r for r in rl if r["total"] == 0]
        if no_sig:
            with st.expander("🔍 لماذا لم توجد إشارات؟"):
                diag_sym = st.selectbox("اختر الأصل:", [r["symbol"] for r in no_sig])
                stats = _cached_diagnose_no_signals(fix_symbol(diag_sym), st.session_state["bt_int"], st.session_state["bt_sd"], st.session_state["bt_ed"])
                if stats:
                    st.json(stats)

        all_dfs = [r["trades_df"] for r in rl if not r["trades_df"].empty]
        if all_dfs:
            comb = pd.concat(all_dfs, ignore_index=True)
            
            view = st.radio("العرض:", ["📉 الشارت والصفقات", "📊 التقرير المالي"], horizontal=True)
            
            if view == "📊 التقرير المالي":
                render_financial_report(comb, symbol="الكل", period="مخصص")
            else:
                opts = [f"{r['symbol']} ({r['total']})" for r in rl]
                ai = rl[opts.index(st.selectbox("اختر الأصل:", opts))]
                sym = ai["symbol"]
                tdf = ai["trades_df"]
                
                if not tdf.empty:
                    si = st.slider("الصفقة:", 0, len(tdf)-1, len(tdf)-1)
                    cur = tdf.iloc[si]
                    
                    st.markdown(f"### {sym} - إشارة {si+1}")
                    st.write(cur.get("Trade Recommendation", ""))
                    
                    df_chart = _prepare_chart_data(fix_symbol(sym), st.session_state["bt_int"], st.session_state["bt_sd"], st.session_state["bt_ed"])
                    render_chart_fast(sym, cur, df_chart)

else:
    st.markdown("### 🚀 الماسح الحي (Live Scan)")
    symbols = st.multiselect("اختر العملات:", ["BTC-USD", "GBPUSD=X", "ETH-USD"], default=["BTC-USD"])
    c1, c2 = st.columns(2)
    interval = c1.selectbox("الإطار:", ALL_GLOBAL_INTERVALS, index=4)
    period = c2.selectbox("النطاق:", ["1mo", "3mo", "6mo", "1y"], index=2)
    
    if st.button("🚀 بدء المسح", use_container_width=True):
        valid = []
        for sym in symbols:
            df, res = _cached_live(fix_symbol(sym), interval, period)
            if res and res.get("signal") in ("STRONG BUY", "STRONG SELL"):
                valid.append({"symbol": sym, "result": res})
        
        if valid:
            st.success(f"تم العثور على {len(valid)} إشارة")
            si = st.slider("الإشارة:", 0, len(valid)-1, 0)
            ar = valid[si]["result"]
            sym = valid[si]["symbol"]
            
            st.write(f"**{sym}** - {ar['signal']}")
            df_chart = _prepare_chart_data(fix_symbol(sym), interval, None, None)
            # في المسح الحي، نقوم بتمرير البيانات للرسم
            if df_chart is not None:
                render_chart_fast(sym, ar, df_chart)
