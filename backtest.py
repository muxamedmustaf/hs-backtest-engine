# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
from engine import run_full_analysis, backtest_strategy

# Streamlit Page Config
st.set_page_config(page_title="Smart Market Analyzer & Backtest", layout="wide")

st.title("📊 Smart Market Analyzer & Backtest Lab")

# Sidebar
st.sidebar.header("⚙️ Settings / الإعدادات")
symbol = st.sidebar.selectbox("👇 اختر الأصل (Select Asset)", ["BTC-USD", "ETH-USD", "EURUSD=X", "GC=F"], index=0)
period = st.sidebar.selectbox("Period", ["1mo", "3mo", "6mo", "1y", "2y"], index=2)
interval = st.sidebar.selectbox("Interval", ["1h", "4h", "1d"], index=2)

@st.cache_data(ttl=300)
def load_data(ticker, p, i):
    try:
        df = yf.download(ticker, period=p, interval=i)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return df
    except Exception as e:
        st.error(f"Error fetching data: {e}")
        return None

df = load_data(symbol, period, interval)

if df is not None and not df.empty:
    # Analysis & Backtest Execution
    analysis = run_full_analysis(df)
    df_active = analysis["df"]
    trades = backtest_strategy(df_active)
    trades_df = pd.DataFrame(trades)

    st.subheader(f"📊 نتائج الاختبار : {symbol}")

    # Kala soocida saxda ah ee OPEN, WIN, iyo LOSS
    if not trades_df.empty and "Head Result" in trades_df.columns:
        win_count = len(trades_df[trades_df['Head Result'] == 'WIN'])
        loss_count = len(trades_df[trades_df['Head Result'] == 'LOSS'])
        open_count = len(trades_df[trades_df['Head Result'] == 'OPEN'])
        total_trades = len(trades_df)

        win_rate = round((win_count / total_trades) * 100, 2) if total_trades > 0 else 0.0
        loss_rate = round((loss_count / total_trades) * 100, 2) if total_trades > 0 else 0.0
    else:
        win_count = loss_count = open_count = total_trades = 0
        win_rate = loss_rate = 0.0

    # Kaadhadhka Natiijooyinka (Cards / Metrics)
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("✅ أ. الإشارات الناجحة", f"{win_count}", delta=f"{win_rate}% Win Rate")
    col2.metric("❌ ب. الإشارات الخاسرة", f"{loss_count}", delta=f"{loss_rate}% Loss Rate", delta_color="inverse")
    col3.metric("⏳ ج. الصفقات المفتوحة", f"{open_count}")
    col4.metric("📈 د. إجمالي الصفقات", f"{total_trades}")

    st.markdown("---")

    # Shuruudaha الدخول المتحققة (Pattern Summary Box)
    pattern_name = analysis.get('pattern', 'NO PATTERN DETECTED')
    signal_type = analysis.get('signal', 'WAITING')
    st.info(f"**د. شروط الدخول المتحققة:** {pattern_name} | **Signal:** {signal_type}")

    # Candlestick Chart
    fig = go.Figure()

    fig.add_trace(go.Candlestick(
        x=df_active.index,
        open=df_active['Open'],
        high=df_active['High'],
        low=df_active['Low'],
        close=df_active['Close'],
        name="Price"
    ))

    # EMA Lines
    if "EMA50" in df_active.columns:
        fig.add_trace(go.Scatter(x=df_active.index, y=df_active['EMA50'], line=dict(color='orange', width=1), name="EMA 50"))
    if "EMA200" in df_active.columns:
        fig.add_trace(go.Scatter(x=df_active.index, y=df_active['EMA200'], line=dict(color='blue', width=1), name="EMA 200"))

    # Drawing pattern lines/nodes
    if analysis.get("nodes"):
        node_x = [n[0] for n in analysis["nodes"]]
        node_y = [n[1] for n in analysis["nodes"]]
        fig.add_trace(go.Scatter(
            x=node_x, 
            y=node_y, 
            mode='lines+markers', 
            line=dict(color='cyan', width=2), 
            marker=dict(size=6, color='red'),
            name="Detected Pattern"
        ))

    fig.update_layout(
        xaxis_rangeslider_visible=False,
        template="plotly_dark",
        height=550,
        margin=dict(l=20, r=20, t=30, b=20)
    )
    
    st.plotly_chart(fig, use_container_width=True)

    # Trades Table
    st.subheader("📋 جدول الصفقات (Backtest Results)")
    if not trades_df.empty:
        st.dataframe(trades_df, use_container_width=True)
    else:
        st.warning("لا توجد صفقات متطابقة مع الشروط في هذه الفترة.")

else:
    st.error("لم يتم العثور على بيانات. يرجى التحقق من رمز الأصل أو الفترة الزمنية.")
