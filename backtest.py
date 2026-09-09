import streamlit as st
import yfinance as yf
import plotly.graph_objects as go
import pandas as pd
from engine import run_full_analysis, backtest_strategy

try:
    from ffff import get_symbols_from_sheet
except ImportError:
    st.error("âš ï¸ The file ffff.py was not found alongside backtest.py")

st.set_page_config(page_title="Smart Market Analyzer & Backtest Lab", page_icon="ðŸ“ˆ", layout="wide", initial_sidebar_state="collapsed")

SHEET_ID = "1TXvF6RhSgfJ631UpnWB38Ww1OMvZVx7VonDB_y1pO3s"
DEFAULT_SHEET_NAME = "GOLD"
DEFAULT_COL_NAME = "TOKENS"

if "current_symbol" not in st.session_state:
    st.session_state.current_symbol = "NZDCAD=X"
if "status_summary" not in st.session_state:
    st.session_state.status_summary = "âš¡ Live Scan & Backtest Lab â€¢ Ready"
if "scanned_signals" not in st.session_state:
    st.session_state.scanned_signals = []

st.markdown(f'''
<div style="display: flex; justify-content: space-between; align-items: center; gap: 14px; margin-bottom: 15px;">
    <div style="border: 1px solid #DADCE0; background: #FFFFFF; border-radius: 16px; padding: 8px 14px; font-weight: 700; color: #0B57D0; font-size: 14px;">ðŸ“ˆ {st.session_state.current_symbol}</div>
    <div style="border: 1px solid #DADCE0; background: #FFFFFF; border-radius: 30px; padding: 8px 14px; font-weight: 700; color: #0B57D0; font-size: 13px;">{st.session_state.status_summary}</div>
</div>
''', unsafe_allow_html=True)

app_mode = st.radio("App Mode:", ["ðŸš€ Live Market Scanner", "ðŸ§ª Backtesting Lab"], horizontal=True)

st.markdown("---")

# ==========================================
# MODE 1: BACKTESTING LAB (Ù…Ø®ØªØ¨Ø± Ø§Ù„Ø§Ø®ØªØ¨Ø§Ø± Ø§Ù„Ø±Ø¬Ø¹ÙŠ)
# ==========================================
if app_mode == "ðŸ§ª Backtesting Lab":
    st.markdown("### ðŸ§ª Strategy Backtesting Lab")
    
    backtest_symbol = st.text_input("Asset Symbol for Backtest", value="EURUSD=X")
    st.session_state.current_symbol = backtest_symbol
    
    col_bar1, col_bar2 = st.columns(2)
    with col_bar1:
        interval_options = ["1m", "5m", "15m", "30m", "1h", "4h", "1d", "1wk", "1mo"]
        selected_interval = st.selectbox("â±ï¸ Ø§Ù„ÙØ§ØµÙ„:", options=interval_options, index=6)
    with col_bar2:
        period_options = ["1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "10y", "ytd", "max"]
        selected_period = st.selectbox("ðŸ“… Ø§Ù„ÙØªØ±Ø©:", options=period_options, index=5)

    run_backtest = st.button("ðŸ“Š Run Backtest Simulation", use_container_width=True)
    
    if run_backtest:
        with st.spinner(f"Running historical simulation for {backtest_symbol}..."):
            try:
                df_bt = yf.download(backtest_symbol, period=selected_period, interval=selected_interval, progress=False, auto_adjust=False)
                if isinstance(df_bt.columns, pd.MultiIndex):
                    df_bt.columns = df_bt.columns.get_level_values(0)
                
                trades = backtest_strategy(df_bt)
                
                if not trades:
                    st.warning("âš ï¸ No completed historical trades found with current parameters.")
                else:
                    trades_df = pd.DataFrame(trades)
                    total_signals = len(trades_df)
                    
                    st.markdown(f"### ðŸ“Š Ø¥Ø¬Ù…Ø§Ù„ÙŠ Ø§Ù„Ø¥Ø´Ø§Ø±Ø§Øª: **{total_signals}**")
                    head_wins = len(trades_df[trades_df["Head Result"] == "WIN"])
                    shoulder_wins = len(trades_df[trades_df["Shoulder Result"] == "WIN"])
                    
                    m1, m2, m3 = st.columns(3)
                    m1.metric("ðŸ“Š Ø§Ù„Ø¥Ø´Ø§Ø±Ø§Øª", total_signals)
                    m2.metric("ðŸ† ÙˆÙ‚Ù Ø§Ù„Ø±Ø£Ø³", head_wins)
                    m3.metric("ðŸ† ÙˆÙ‚Ù Ø§Ù„ÙƒØªÙ", shoulder_wins)
                    
                    st.markdown("---")
                    st.dataframe(trades_df, use_container_width=True)
            except Exception as e:
                st.error(f"Error: {e}")

# ==========================================
# MODE 2: LIVE MARKET SCANNER
# ==========================================
else:
    scan_mode = st.radio("Scan Method:", ["Ø³Ù‡Ù… ÙØ±Ø¯ÙŠ", "Ù…Ø³Ø­ ÙƒÙ„ÙŠ Ù„Ø´ÙŠØª Ø§Ù„Ø£ØµÙˆÙ„"], horizontal=True)
    
    symbols_to_scan = []
    if scan_mode == "Ø³Ù‡Ù… ÙØ±Ø¯ÙŠ":
        symbol = st.text_input("Market Asset Symbol", value="NZDCAD=X")
        st.session_state.current_symbol = symbol
        symbols_to_scan = [symbol]
    else:
        fetched_symbols, err = get_symbols_from_sheet(SHEET_ID, DEFAULT_SHEET_NAME, DEFAULT_COL_NAME)
        if err:
            st.error(err)
        else:
            symbols_to_scan = fetched_symbols
            st.success(f"Loaded {len(symbols_to_scan)} assets from Google Sheet!")

    col_bar1, col_bar2 = st.columns(2)
    with col_bar1:
        interval_options = ["1m", "5m", "15m", "30m", "1h", "4h", "1d", "1wk", "1mo"]
        selected_interval = st.selectbox("â±ï¸ Ø§Ù„ÙØ§ØµÙ„ (Interval):", options=interval_options, index=6)
    with col_bar2:
        period_options = ["1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "10y", "ytd", "max"]
        selected_period = st.selectbox("ðŸ“… Ø§Ù„ÙØªØ±Ø© (Period):", options=period_options, index=10)

    run_scan = st.button("ðŸš€ Start Scan & Analysis", use_container_width=True)

    if run_scan and symbols_to_scan:
        valid_signals = []
        progress_bar = st.progress(0)
        status_text = st.empty()

        for idx, sym in enumerate(symbols_to_scan):
            status_text.text(f"Scanning ({idx+1}/{len(symbols_to_scan)}): {sym}...")
            progress_bar.progress((idx + 1) / len(symbols_to_scan))

            try:
                df = yf.download(sym, period=selected_period, interval=selected_interval, progress=False, auto_adjust=False)
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)

                if not df.empty and len(df) >= 20:
                    result = run_full_analysis(df)
                    signal = result["signal"]
                    pattern = result["pattern"]

                    if signal in ["STRONG BUY", "STRONG SELL"] or scan_mode == "Ø³Ù‡Ù… ÙØ±Ø¯ÙŠ":
                        valid_signals.append({
                            "symbol": sym, "signal": signal, "pattern": pattern, "result": result
                        })
            except Exception:
                continue

        status_text.empty()
        progress_bar.empty()
        st.session_state.scanned_signals = valid_signals
        st.success(f"Scan finished! Found: {len(valid_signals)} signals.")

    if st.session_state.scanned_signals:
        valid_signals = st.session_state.scanned_signals

        if scan_mode == "Ù…Ø³Ø­ ÙƒÙ„ÙŠ Ù„Ø´ÙŠØª Ø§Ù„Ø£ØµÙˆÙ„":
            options = [f"{item['symbol']} | {item['signal']} ({item['pattern']})" for item in valid_signals]
            if options:
                selected_option = st.selectbox("ðŸ‘‡ Select asset:", options)
                selected_index = options.index(selected_option)
                active_result = valid_signals[selected_index]["result"]
                active_symbol = valid_signals[selected_index]["symbol"]
            else:
                active_result = None
                active_symbol = ""
        else:
            if valid_signals:
                active_result = valid_signals[0]["result"]
                active_symbol = valid_signals[0]["symbol"]
            else:
                active_result = None
                active_symbol = ""

        if active_result:
            st.session_state.current_symbol = active_symbol
            df_res = active_result.get("df", None)
            signal, pattern = active_result["signal"], active_result["pattern"]
            
            if df_res is not None and not df_res.empty:
                latest_rsi = df_res['RSI'].iloc[-1] if 'RSI' in df_res.columns else 0.0
                latest_close = df_res['Close'].iloc[-1]
                st.markdown(f"""
                <div style="margin-top: 10px; margin-bottom: 10px;">
                    <div style="font-size: 36px; font-weight: 650; color: #0B57D0;">{latest_close:.5f}</div>
                    <div style="font-size: 14px; color: #202124;">RSI (14): {latest_rsi:.2f}</div>
                </div>
                """, unsafe_allow_html=True)

            e1, e2, e3 = st.columns(3)
            e1.metric("ðŸŽ¯ Entry", f"{active_result.get('entry', 0)}")
            e2.metric("ðŸ›‘ Stop Loss", f"{active_result.get('sl', 0)}")
            e3.metric("ðŸ† Target", f"{active_result.get('tp', 0)}")

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
                fig.update_layout(template="plotly_white", height=450, xaxis_rangeslider_visible=False, margin=dict(l=10, r=20, t=10, b=20))
                st.plotly_chart(fig, use_container_width=True)
                    
