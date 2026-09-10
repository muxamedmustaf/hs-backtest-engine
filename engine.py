# -*- coding: utf-8 -*-
import streamlit as st
import yfinance as yf
import plotly.graph_objects as go
import pandas as pd
from engine import run_full_analysis, backtest_strategy

try:
    from ffff import get_symbols_from_sheet
except ImportError:
    st.error("⚠️ تنبيه: لم يتم العثور على ملف ffff.py بجانب ملف الواجهة")

st.set_page_config(page_title="Smart Market Analyzer & Backtest Lab", page_icon="📈", layout="wide", initial_sidebar_state="collapsed")

SHEET_ID = "1TXvF6RhSgfJ631UpnWB38Ww1OMvZVx7VonDB_y1pO3s"
DEFAULT_SHEET_NAME = "GOLD"
DEFAULT_COL_NAME = "TOKENS"

if "current_symbol" not in st.session_state:
    st.session_state.current_symbol = "NZDCAD=X"
if "status_summary" not in st.session_state:
    st.session_state.status_summary = "⚡ Live Scan & Backtest Lab • جاهز"
if "scanned_signals" not in st.session_state:
    st.session_state.scanned_signals = []
if "backtest_scanned_signals" not in st.session_state:
    st.session_state.backtest_scanned_signals = []
if "backtest_dfs" not in st.session_state:
    st.session_state.backtest_dfs = {}

st.markdown(f'''
<div style="display: flex; justify-content: space-between; align-items: center; gap: 14px; margin-bottom: 15px;">
    <div style="border: 1px solid #DADCE0; background: #FFFFFF; border-radius: 16px; padding: 8px 14px; font-weight: 700; color: #0B57D0; font-size: 14px;">📈 {st.session_state.current_symbol}</div>
    <div style="border: 1px solid #DADCE0; background: #FFFFFF; border-radius: 30px; padding: 8px 14px; font-weight: 700; color: #0B57D0; font-size: 13px;">{st.session_state.status_summary}</div>
</div>
''', unsafe_allow_html=True)

app_mode = st.radio("وضع التطبيق:", ["🚀 الماسح الحي للأسواق", "🧪 مختبر الاختبار الرجعي (Backtest)"], horizontal=True)

st.markdown("---")

# ==========================================
# MODE 1: BACKTESTING LAB (مختبر الاختبار الرجعي)
# ==========================================
if app_mode == "🧪 مختبر الاختبار الرجعي (Backtest)":
    st.markdown("### 🧪 مختبر تحليل الأداء التاريخي")
    
    bt_scan_mode = st.radio("طريقة فحص الاختبار الرجعي:", ["سهم فردي", "مسح كلي لشيت الأصول"], horizontal=True, key="bt_scan_mode_radio")
    
    bt_symbols_to_scan = []
    if bt_scan_mode == "سهم فردي":
        backtest_symbol = st.text_input("رمز الأصل للاختبار الرجعي", value="EURUSD=X")
        st.session_state.current_symbol = backtest_symbol
        bt_symbols_to_scan = [backtest_symbol]
    else:
        fetched_symbols, err = get_symbols_from_sheet(SHEET_ID, DEFAULT_SHEET_NAME, DEFAULT_COL_NAME)
        if err:
            st.error(err)
        else:
            bt_symbols_to_scan = fetched_symbols
            st.success(f"تم تحميل {len(bt_symbols_to_scan)} أصل بنجاح من جدول بيانات جوجل!")

    col_bar1, col_bar2 = st.columns(2)
    with col_bar1:
        interval_options = ["1m", "5m", "15m", "30m", "1h", "4h", "1d", "1wk", "1mo"]
        selected_interval = st.selectbox("⏱️ الإطار الزمني:", options=interval_options, index=6, key="bt_interval")
    with col_bar2:
        period_options = ["1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "10y", "ytd", "max"]
        selected_period = st.selectbox("📅 فترة البيانات:", options=period_options, index=5, key="bt_period")

    run_backtest = st.button("📊 بدء محاكاة الاختبار الرجعي", use_container_width=True, key="run_bt_btn")
    
    if run_backtest and bt_symbols_to_scan:
        bt_results_list = []
        bt_dfs_dict = {}
        progress_bar = st.progress(0)
        status_text = st.empty()

        for idx, sym in enumerate(bt_symbols_to_scan):
            status_text.text(f"جاري محاكاة الأصل ({idx+1}/{len(bt_symbols_to_scan)}): {sym}...")
            progress_bar.progress((idx + 1) / len(bt_symbols_to_scan))

            try:
                df_bt = yf.download(sym, period=selected_period, interval=selected_interval, progress=False, auto_adjust=False)
                if isinstance(df_bt.columns, pd.MultiIndex):
                    df_bt.columns = df_bt.columns.get_level_values(0)
                
                trades = backtest_strategy(df_bt)
                if trades:
                    trades_df = pd.DataFrame(trades)
                    bt_results_list.append({
                        "symbol": sym,
                        "trades_df": trades_df,
                        "total_signals": len(trades_df)
                    })
                    bt_dfs_dict[sym] = df_bt
            except Exception:
                continue

        status_text.empty()
        progress_bar.empty()
        st.session_state.backtest_scanned_signals = bt_results_list
        st.session_state.backtest_dfs = bt_dfs_dict
        st.success(f"اكتملت محاكاة الاختبار الرجعي! تم العثور على نتائج لـ {len(bt_results_list)} أصل.")

    if st.session_state.backtest_scanned_signals:
        bt_results_list = st.session_state.backtest_scanned_signals
        bt_dfs_dict = st.session_state.backtest_dfs

        if bt_scan_mode == "مسح كلي لشيت الأصول":
            bt_options = [f"{item['symbol']} | عدد الصفقات: {item['total_signals']}" for item in bt_results_list]
            if bt_options:
                selected_bt_option = st.selectbox("👇 اختر الأصل المعروض للباك تست:", bt_options, key="bt_sheet_select")
                selected_bt_index = bt_options.index(selected_bt_option)
                active_bt_item = bt_results_list[selected_bt_index]
            else:
                active_bt_item = None
        else:
            if bt_results_list:
                active_bt_item = bt_results_list[0]
            else:
                active_bt_item = None

        if active_bt_item:
            active_sym = active_bt_item["symbol"]
            st.session_state.current_symbol = active_sym
            trades_df = active_bt_item["trades_df"]
            total_signals = active_bt_item["total_signals"]
            
            st.markdown(f"### 📊 إجمالي الإشارات المكتشفة للأصل {active_sym}: **{total_signals}**")
            head_wins = len(trades_df[trades_df["Head Result"] == "WIN"]) if "Head Result" in trades_df.columns else 0
            shoulder_wins = len(trades_df[trades_df["Shoulder Result"] == "WIN"]) if "Shoulder Result" in trades_df.columns else 0
            
            m1, m2, m3 = st.columns(3)
            m1.metric("📊 إجمالي الصفقات", total_signals)
            m2.metric("🎯 نجاح الرأس", head_wins)
            m3.metric("🎯 نجاح الكتف", shoulder_wins)
            
            # --- رسم الشارت البياني مع رسم تفاصيل الأنماط والدوائر تماماً كالصورة المطلوبة ---
            if active_sym in bt_dfs_dict and not bt_dfs_dict[active_sym].empty:
                df_bt_res = bt_dfs_dict[active_sym]
                st.markdown("#### 📈 الشارت البياني التاريخي مع ترسيم النمط الفني")
                
                fig_bt = go.Figure()
                fig_bt.add_trace(go.Candlestick(
                    x=df_bt_res.index, open=df_bt_res["Open"], high=df_bt_res["High"], low=df_bt_res["Low"], close=df_bt_res["Close"],
                    name="السعر", increasing_line_color="#137333", decreasing_line_color="#C5221F"
                ))
                
                # سحب ورسم خطوط وعقد النمط (Nodes) من كل صفقة
                if not trades_df.empty and 'nodes' in trades_df.columns:
                    for idx, row in trades_df.iterrows():
                        nodes = row.get('nodes', [])
                        if isinstance(nodes, list) and nodes:
                            sorted_nodes = sorted(nodes, key=lambda item: pd.to_datetime(item[0]))
                            x_nodes = [n[0] for n in sorted_nodes]
                            y_nodes = [n[1] for n in sorted_nodes]
                            fig_bt.add_trace(go.Scatter(
                                x=x_nodes, y=y_nodes,
                                mode="lines+markers", 
                                line=dict(color="#C5221F", width=2.5),
                                marker=dict(size=8, color="#0B57D0"), 
                                name=f"النمط #{idx+1}"
                            ))

                fig_bt.update_layout(template="plotly_white", height=480, xaxis_rangeslider_visible=False, margin=dict(l=10, r=20, t=10, b=20))
                st.plotly_chart(fig_bt, use_container_width=True)

            st.markdown("---")
            st.dataframe(trades_df, use_container_width=True)

# ==========================================
# MODE 2: LIVE MARKET SCANNER
# ==========================================
else:
    scan_mode = st.radio("طريقة الفحص:", ["سهم فردي", "مسح كلي لشيت الأصول"], horizontal=True, key="live_scan_mode_radio")
    
    symbols_to_scan = []
    if scan_mode == "سهم فردي":
        symbol = st.text_input("رمز أصل السوق", value="NZDCAD=X", key="live_single_symbol")
        st.session_state.current_symbol = symbol
        symbols_to_scan = [symbol]
    else:
        fetched_symbols, err = get_symbols_from_sheet(SHEET_ID, DEFAULT_SHEET_NAME, DEFAULT_COL_NAME)
        if err:
            st.error(err)
        else:
            symbols_to_scan = fetched_symbols
            st.success(f"تم تحميل {len(symbols_to_scan)} أصل بنجاح من جدول بيانات جوجل!")

    col_bar1, col_bar2 = st.columns(2)
    with col_bar1:
        interval_options = ["1m", "5m", "15m", "30m", "1h", "4h", "1d", "1wk", "1mo"]
        selected_interval = st.selectbox("⏱️ الإطار الزمني للفحص:", options=interval_options, index=6, key="live_interval")
    with col_bar2:
        period_options = ["1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "10y", "ytd", "max"]
        selected_period = st.selectbox("📅 نطاق البيانات:", options=period_options, index=10, key="live_period")

    run_scan = st.button("🚀 بدء المسح والتحليل الفوري", use_container_width=True, key="run_live_btn")

    if run_scan and symbols_to_scan:
        valid_signals = []
        progress_bar = st.progress(0)
        status_text = st.empty()

        for idx, sym in enumerate(symbols_to_scan):
            status_text.text(f"جاري الفحص ({idx+1}/{len(symbols_to_scan)}): {sym}...")
            progress_bar.progress((idx + 1) / len(symbols_to_scan))

            try:
                df = yf.download(sym, period=selected_period, interval=selected_interval, progress=False, auto_adjust=False)
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)

                if not df.empty and len(df) >= 20:
                    result = run_full_analysis(df)
                    signal = result["signal"]
                    pattern = result["pattern"]

                    if signal in ["STRONG BUY", "STRONG SELL"] or scan_mode == "سهم فردي":
                        valid_signals.append({
                            "symbol": sym, "signal": signal, "pattern": pattern, "result": result
                        })
            except Exception:
                continue

        status_text.empty()
        progress_bar.empty()
        st.session_state.scanned_signals = valid_signals
        st.success(f"اكتمل المسح! تم رصد: {len(valid_signals)} إشارة.")

    if st.session_state.scanned_signals:
        valid_signals = st.session_state.scanned_signals

        if scan_mode == "مسح كلي لشيت الأصول":
            options = [f"{item['symbol']} | {item['signal']} ({item['pattern']})" for item in valid_signals]
            if options:
                selected_option = st.selectbox("👇 اختر الأصل المعروض:", options, key="live_sheet_select")
                selected_index = options.index(selected_option)
                active_result = valid_signals[selected_index]["result"]
                active_symbol = valid_signals[selected_index]["symbol"]
            else:
                active_result = None
                active_symbol = ""
        else:
            if valid_signals:
                active_result = valid_signals[0]["result"]
                active_symbol = valid_signals[0]["result"]["symbol"] if "symbol" in valid_signals[0]["result"] else symbols_to_scan[0]
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
                    <div style="font-size: 14px; color: #202124;">مؤشر القوة النسبية RSI (14): {latest_rsi:.2f}</div>
                </div>
                """, unsafe_allow_html=True)

            e1, e2, e3 = st.columns(3)
            e1.metric("🎯 سعر الدخول (Entry)", f"{active_result.get('entry', 0)}")
            e2.metric("🛑 وقف الخسارة (Stop Loss)", f"{active_result.get('sl', 0)}")
            e3.metric("🏆 الهدف (Target)", f"{active_result.get('tp', 0)}")

            if df_res is not None and not df_res.empty:
                fig = go.Figure()
                fig.add_trace(go.Candlestick(
                    x=df_res.index, open=df_res["Open"], high=df_res["High"], low=df_res["Low"], close=df_res["Close"],
                    name="السعر", increasing_line_color="#137333", decreasing_line_color="#C5221F"
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
        
