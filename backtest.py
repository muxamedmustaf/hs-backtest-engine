# -*- coding: utf-8 -*-
import calendar, datetime
import streamlit as st
import plotly.graph_objects as go
import pandas as pd
import numpy as np
from data_provider import fetch_data

try:
    from engine import run_full_analysis, backtest_strategy, diagnose_no_signals
except ImportError:
    st.error("تأكد من وجود engine.py"); st.stop()

st.set_page_config(page_title="Box Hunter", page_icon="📦", layout="wide")

st.markdown("""
<style>
    .main .block-container { max-width: 100% !important; padding: 0.5rem 1rem !important; }
    html, body, [class*="css"] { direction: rtl; text-align: right; font-size: 15px; }
    h1, h2, h3, h4, h5, h6 { direction: rtl; text-align: right; }
    div[data-testid="stMetricLabel"] { direction: rtl; text-align: right; }
    div[data-testid="stMetricValue"] { direction: ltr; text-align: right; }
    .stDataFrame { direction: ltr; }
    
    /* 🎯 السحر هنا: إجبار الشارت على التقاط حركة الإصبع بدلاً من تحريك الصفحة */
    .js-plotly-plot .plotly, .js-plotly-plot .plotly .main-svg {
        touch-action: none !important;
    }
</style>
""", unsafe_allow_html=True)

ALL_GLOBAL_INTERVALS = ["15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d", "1wk"]

# 🎯 تفعيل التمرير السلس والزوم بالإصبع
PLOTLY_CONFIG = {
    'responsive': True,
    'scrollZoom': True, # يسمح بالزوم بإصبعين
    'displaylogo': False,
    'displayModeBar': True,
    'modeBarButtonsToRemove': ['sendDataToCloud', 'lasso2d', 'select2d', 'autoScale2d', 'toggleSpikelines'],
    'dragmode': 'pan', # يسمح بالسحب للتحريك
    'doubleClick': 'reset+autosize',
}

def fix_symbol(sym):
    sym = str(sym).strip().upper()
    if sym in ("XAUUSD", "GOLD"): return "GC=F"
    if len(sym) == 6 and sym.isalpha(): return f"{sym}=X"
    return sym

@st.cache_data(ttl=3600, show_spinner=False)
def _cached_fetch(symbol, interval, start_date=None, end_date=None, period=None):
    try:
        if start_date and end_date: return fetch_data(symbol, interval=interval, start_date=start_date, end_date=end_date, cache_hours=1)
        return fetch_data(symbol, interval=interval, period=period, cache_hours=1)
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

# ══════════════════════════════════════════════════════════════════════════════
# 🎨 دالة رسم الصندوق بدقة (ربط القمم والقيعان)
# ══════════════════════════════════════════════════════════════════════════════
def draw_box_pattern(fig, source, df):
    if source is None: return
    nodes = source.get("nodes", [])
    box_nodes = source.get("neckline_nodes", [])
    
    if len(nodes) < 3 or len(box_nodes) < 4: return

    # 1. رسم خط الحركة السابقة
    fig.add_trace(go.Scatter(
        x=[nodes[0][0], nodes[1][0]], y=[nodes[0][1], nodes[1][1]], 
        mode="lines", name="Trend", line=dict(color="#FF9800", width=2, dash="dot")
    ))

    # 2. رسم الصندوق (الخطوط العلوية والسفلية والجانبية)
    # النقاط: [0]=بداية علوي, [1]=نهاية علوي, [2]=بداية سفلي, [3]=نهاية سفلي
    top_x = [box_nodes[0][0], box_nodes[1][0]]
    top_y = [box_nodes[0][1], box_nodes[1][1]]
    bot_x = [box_nodes[2][0], box_nodes[3][0]]
    bot_y = [box_nodes[2][1], box_nodes[3][1]]
    
    # الخط العلوي (المقاومة)
    fig.add_trace(go.Scatter(x=top_x, y=top_y, mode="lines", name="Resistance", line=dict(color="#2196F3", width=2)))
    # الخط السفلي (الدعم)
    fig.add_trace(go.Scatter(x=bot_x, y=bot_y, mode="lines", name="Support", line=dict(color="#2196F3", width=2)))
    
    # الخطوط الجانبية (لتكتمل هيئة الصندوق)
    fig.add_trace(go.Scatter(x=[top_x[0], bot_x[0]], y=[top_y[0], bot_y[0]], mode="lines", line=dict(color="#B0BEC5", width=1), showlegend=False))
    fig.add_trace(go.Scatter(x=[top_x[1], bot_x[1]], y=[top_y[1], bot_y[1]], mode="lines", line=dict(color="#B0BEC5", width=1), showlegend=False))

    # 3. رسم نقطة الاختراق
    fig.add_trace(go.Scatter(
        x=[nodes[2][0]], y=[nodes[2][1]],
        mode="markers+text", name="Breakout",
        marker=dict(size=14, color="#E91E63", symbol="star"),
        text=["كسر"], textposition="top center"
    ))

    # 4. رسم SL و TP
    entry = source.get("entry")
    sl = source.get("sl")
    tp = source.get("tp")
    entry_x = nodes[2][0]
    
    if entry and sl: fig.add_annotation(x=entry_x, y=sl, text=f"SL ({sl})", showarrow=True, arrowhead=1, ax=20, ay=20, font=dict(color="red"))
    if entry and tp: fig.add_annotation(x=entry_x, y=tp, text=f"TP ({tp})", showarrow=True, arrowhead=1, ax=20, ay=-20, font=dict(color="green"))

# ══════════════════════════════════════════════════════════════════════════════
# 🎯 دالة رسم الشارت (ناعمة وتدعم التمرير)
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
    
    # 🎯 التعديلات لجعل الشارت مرناً (Fixedrange = False)
    fig.update_layout(
        template="plotly_white", height=700, autosize=True,
        xaxis_rangeslider_visible=False, 
        dragmode="pan", # تفعيل وضع السحب
        hovermode="x unified",
        yaxis=dict(side="left", showgrid=True, gridcolor="#EEEEEE", fixedrange=False), # يسمح بالتحريك العمودي
        xaxis=dict(showgrid=True, gridcolor="#F5F5F5", range=[x_min, x_max], fixedrange=False), # يسمح بالتحريك الأفقي
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5)
    )
    st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)

def render_financial_report(df, lot_size=0.01, symbol="—", period="—"):
    st.markdown("### 📊 التقرير المالي")
    if df is None or df.empty: st.info("لا صفقات"); return
    s = df["Result"].astype(str).str.upper() if "Result" in df.columns else pd.Series()
    w, l = len(df[s.str.contains("WIN")]), len(df[s.str.contains("LOSS")])
    total = len(df); wr = round(w/(w+l)*100, 1) if (w+l)>0 else 0
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("الصفقات", total); c2.metric("رابحة", w, f"{wr}%"); c3.metric("خاسرة", l); c4.metric("مفتوحة/تعادل", total - w - l)
    csv = df.to_csv(index=False).encode('utf-8-sig')
    st.download_button("📥 تنزيل CSV", csv, f"backtest_{symbol}_{period}.csv", "text/csv", type="primary")

# الواجهة
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
                    if "Trade Recommendation" in cur: st.write(cur["Trade Recommendation"])
                    
                    df_chart = _prepare_chart_data(fix_symbol(sym), st.session_state["bt_int"], st.session_state["bt_sd"], st.session_state["bt_ed"])
                    render_chart_fast(sym, cur, df_chart)
else:
    st.markdown("### 🚀 الماسح الحي")
    symbols = st.multiselect("اختر العملات:", ["BTC-USD", "GBPUSD=X", "ETH-USD"], default=["BTC-USD"])
    interval = st.selectbox("الإطار:", ALL_GLOBAL_INTERVALS, index=4)
    period = st.selectbox("النطاق:", ["1mo", "3mo", "6mo", "1y"], index=2)
    
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
            if df_chart is not None: render_chart_fast(sym, ar, df_chart)
