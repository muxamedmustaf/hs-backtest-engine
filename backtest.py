import streamlit as st
import yfinance as yf
import plotly.graph_objects as go
import pandas as pd
from engine import run_full_analysis, backtest_strategy

try:
    from ffff import get_symbols_from_sheet
except ImportError:
    st.error("⚠️ The file ffff.py was not found alongside backtest.py")

st.set_page_config(page_title="Smart Market Analyzer & Backtest Lab", page_icon="📈", layout="wide", initial_sidebar_state="collapsed")

SHEET_ID = "1TXvF6RhSgfJ631UpnWB38Ww1OMvZVx7VonDB_y1pO3s"
DEFAULT_SHEET_NAME = "GOLD"
DEFAULT_COL_NAME = "TOKENS"

if "current_symbol" not in st.session_state:
    st.session_state.current_symbol = "NZDCAD=X"
if "status_summary" not in st.session_state:
    st.session_state.status_summary = "⚡ Live Scan & Backtest Lab • Ready"
if "scanned_signals" not in st.session_state:
    st.session_state.scanned_signals = []

st.markdown(f'''
<div style="display: flex; justify-content: space-between; align-items: center; gap: 14px; margin-bottom: 20px;">
    <div style="border: 1px solid #DADCE0; background: #FFFFFF; border-radius: 16px; padding: 10px 18px; font-weight: 700; color: #0B57D0;">📈 {st.session_state.current_symbol}</div>
    <div style="border: 1px solid #DADCE0; background: #FFFFFF; border-radius: 30px; padding: 10px 18px; font-weight: 700; color: #0B57D0;">{st.session_state.status_summary}</div>
</div>
''', unsafe_allow_html=True)

app_mode = st.radio("App Mode:", ["🚀 Live Market Scanner", "🧪 Backtesting Lab (مختبر الاختبار الرجعي)"], horizontal=True)

st.markdown("---")

# شريط اختيار الفترة الزمنية (Timeframe Bar)
col_tf1, col_tf2 = st.columns([2, 3])
with col_tf1:
    tf_options = ["1m", "5m", "15m", "30m", "1h", "4h", "1D", "1W", "1M"]
    selected_tf = st.selectbox("⏱️ حدد الإطار الزمني (Timeframe):", options=tf_options, index=6)

tf_map = {
    "1m": {"interval": "1m", "period": "7d"}, "5m": {"interval": "5m", "period": "60d"},
    "15m": {"interval": "15m", "period": "60d"}, "30m": {"interval": "30m", "period": "60d"},
    "1h": {"interval": "1h", "period": "2y"}, "4h": {"interval": "1h", "period": "2y"},
    "1D": {"interval": "1d", "period": "max"}, "1W": {"interval": "1wk", "period": "max"},
    "1M": {"interval": "1mo", "period": "max"},
}
current_setting = tf_map[selected_tf]

st.markdown("---")

# ==========================================
# MODE 1: BACKTESTING LAB (مختبر الاختبار الرجعي)
# ==========================================
if app_mode == "🧪 Backtesting Lab (مختبر الاختبار الرجعي)":
    st.markdown("### 🧪 Strategy Backtesting Lab & SL Comparison")
    st.markdown("Simulate unique historical signals and compare Head SL vs Shoulder SL performance.")
    
    backtest_symbol = st.text_input("Asset Symbol for Backtest", value="EURUSD=X")
    st.session_state.current_symbol = backtest_symbol
    
    run_backtest = st.button("📊 Run Backtest Simulation", use_container_width=True)
    
    if run_backtest:
        with st.spinner(f"Running historical simulation for {backtest_symbol}..."):
            try:
                df_bt = yf.download(backtest_symbol, period=current_setting["period"], interval=current_setting["interval"], progress=False, auto_adjust=False)
                if isinstance(df_bt.columns, pd.MultiIndex):
                    df_bt.columns = df_bt.columns.get_level_values(0)
                
                trades = backtest_strategy(df_bt)
                
                if not trades:
                    st.warning("⚠️ No completed historical trades found with current parameters on this asset/timeframe.")
                else:
                    trades_df = pd.DataFrame(trades)
                    total_signals = len(trades_df)
                    
                    st.markdown(f"### 📊 إجمالي الإشارات المكتشفة للزوج: **{total_signals}** إشارة فريدة")
                    
                    head_wins = len(trades_df[trades_df["Head Result"] == "WIN"])
                    shoulder_wins = len(trades_df[trades_df["Shoulder Result"] == "WIN"])
                    
                    m1, m2, m3 = st.columns(3)
                    m1.metric("📊 إجمالي الإشارات الفريدة", total_signals)
                    m2.metric("🏆 صفقات رابحة (وقف الرأس)", head_wins)
                    m3.metric("🏆 صفقات رابحة (وقف الكتف)", shoulder_wins)
                    
                    st.markdown("---")
                    st.markdown("#### 📋 جدول مقارنة أداء وقف الرأس مقابل وقف الكتف لكل صفقة")
                    st.dataframe(trades_df, use_container_width=True)
                    
                    trades_df["Cumulative Head Wins"] = (trades_df["Head Result"] == "WIN").astype(int).cumsum()
                    trades_df["Cumulative Shoulder Wins"] = (trades_df["Shoulder Result"] == "WIN").astype(int).cumsum()
                    
                    fig_eq = go.Figure()
                    fig_eq.add_trace(go.Scatter(
                        x=trades_df["Entry Time"], y=trades_df["Cumulative Head Wins"],
                        mode="lines+markers", line=dict(color="#0B57D0", width=3),
                        name="Head SL Performance"
                    ))
                    fig_eq.add_trace(go.Scatter(
                        x=trades_df["Entry Time"], y=trades_df["Cumulative Shoulder Wins"],
                        mode="lines+markers", line=dict(color="#0F9D58", width=3, dash="dot"),
                        name="Shoulder SL Performance"
                    ))
                    fig_eq.update_layout(
                        title="Cumulative Strategy Performance Comparison (Head vs Shoulder SL)",
                        template="plotly_white", height=400,
                        margin=dict(l=10, r=20, t=30, b=20)
                    )
                    st.plotly_chart(fig_eq, use_container_width=True)
            except Exception as e:
                st.error(f"Error during backtest execution: {e}")

# ==========================================
# MODE 2: LIVE MARKET SCANNER
# ==========================================
else:
    scan_mode = st.radio("Scan Method:", ["Single Asset", "Google Sheet (Scan List for Completed Setups)"], horizontal=True)
    symbols_to_scan = []

    if scan_mode == "Single Asset":
        symbol = st.text_input("Market Asset Symbol", value="NZDCAD=X")
        st.session_state.current_symbol = symbol
        symbols_to_scan = [symbol]
    else:
        fetched_symbols, err = get_symbols_from_sheet(SHEET_ID, DEFAULT_SHEET_NAME, DEFAULT_COL_NAME)
        if err:
            st.error(err)
        else:
            symbols_to_scan = fetched_symbols
            st.success(f"Successfully loaded {len(symbols_to_scan)} assets from Google Sheet!")

    run_scan = st.button("🚀 Start Scan & Analysis", use_container_width=True)

    if run_scan and symbols_to_scan:
        valid_signals = []
        progress_bar = st.progress(0)
        status_text = st.empty()

        for idx, sym in enumerate(symbols_to_scan):
            status_text.text(f"Scanning asset ({idx+1}/{len(symbols_to_scan)}): {sym}...")
            progress_bar.progress((idx + 1) / len(symbols_to_scan))

            try:
                df = yf.download(sym, period=current_setting["period"], interval=current_setting["interval"], progress=False, auto_adjust=False)
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)

                if not df.empty and len(df) >= 20:
                    result = run_full_analysis(df)
                    signal = result["signal"]
                    pattern = result["pattern"]

                    if signal in ["STRONG BUY", "STRONG SELL"] or scan_mode == "Single Asset":
                        valid_signals.append({
                            "symbol": sym,
                            "signal": signal,
                            "pattern": pattern,
                            "result": result
                        })
            except Exception:
                continue

        status_text.empty()
        progress_bar.empty()
        st.session_state.scanned_signals = valid_signals
        st.success(f"Scan finished! Total results found: {len(valid_signals)} valid signals.")

    if st.session_state.scanned_signals:
        valid_signals = st.session_state.scanned_signals

        if scan_mode == "Google Sheet (Scan List for Completed Setups)":
            options = [f"{item['symbol']} | {item['signal']} ({item['pattern']})" for item in valid_signals]
            selected_option = st.selectbox("👇 Select asset to view analysis, target levels, and chart:", options)
            selected_index = options.index(selected_option)
            selected_data = valid_signals[selected_index]
            active_result = selected_data["result"]
            active_symbol = selected_data["symbol"]
        else:
            active_result = valid_signals[0]["result"]
            active_symbol = valid_signals[0]["symbol"]

        if active_result:
            st.session_state.current_symbol = active_symbol
            df_res = active_result.get("df", None)
            signal, pattern = active_result["signal"], active_result["pattern"]
            
            if df_res is not None and not df_res.empty:
                latest_rsi = df_res['RSI'].iloc[-1] if 'RSI' in df_res.columns else 0.0
                latest_close = df_res['Close'].iloc[-1]

                st.markdown(f"""
                <div style="margin-top: 14px; margin-bottom: 15px;">
                    <div style="font-size: 42px; font-weight: 650; color: #0B57D0;">{latest_close:.5f}</div>
                    <div style="font-size: 15px; color: #202124;">RSI (14): {latest_rsi:.2f}</div>
                </div>
                """, unsafe_allow_html=True)

            e1, e2, e3 = st.columns(3)
            e1.metric("🎯 Entry", f"{active_result.get('entry', 0)}")
            e2.metric("🛑 Stop Loss", f"{active_result.get('sl', 0)}")
            e3.metric("🏆 Target", f"{active_result.get('tp', 0)}")

            bias_text = "Bullish" if signal == "STRONG BUY" else "Bearish" if signal == "STRONG SELL" else "Neutral"
            st.info(
                f"**ANALYSIS REPORT:** A confirmed **{pattern}** pattern has been detected for **{active_symbol}** indicating a **{bias_text}** trend shift.\n"
                f"**EXECUTION PLAN:** Recommendation is **{signal}** at **{active_result.get('entry', 0)}** with Stop Loss set at **{active_result.get('sl', 0)}** and Target at **{active_result.get('tp', 0)}**."
            )

            if df_res is not None and not df_res.empty:
                fig = go.Figure()
                fig.add_trace(go.Candlestick(
                    x=df_res.index, open=df_res["Open"], high=df_res["High"], low=df_res["Low"], close=df_res["Close"],
                    name="Price", increasing_line_color="#137333", decreasing_line_color="#C5221F"
                ))

                nodes = active_result.get("nodes", [])
                if nodes:
                    sorted_nodes = sorted(nodes, key=lambda item: pd.to_datetime(item[0]))
                    x_nodes = [n[0] for n in sorted_nodes]
                    y_nodes = [n[1] for n in sorted_nodes]
                    fig.add_trace(go.Scatter(
                        x=x_nodes, y=y_nodes,
                        mode="lines+markers", line=dict(color="#C5221F", width=2.5),
                        marker=dict(size=7, color="#0B57D0"), name=f"{pattern}"
                    ))

                fig.update_layout(
                    template="plotly_white", height=520,
                    xaxis_rangeslider_visible=False,
                    margin=dict(l=10, r=40, t=10, b=30),
                    showlegend=False, dragmode='pan'
                )

                st.plotly_chart(fig, use_container_width=True, config={'scrollZoom': True, 'displayModeBar': True, 'responsive': True})
                
