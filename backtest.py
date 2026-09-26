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

st.set_page_config(
    page_title="Smart Market Analyzer & Backtest Lab",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# 1. إضافة قواعد CSS لتوسيع نافذة عرض الشارت أفقياً لملء كامل عرض الواجهة
st.markdown("""
    <style>
        .main .block-container {
            max-width: 100% !important;
            padding-left: 0.5rem !important;
            padding-right: 0.5rem !important;
        }
        div[data-testid="stPlotlyChart"],
        div[data-testid="stPlotlyChart"] > div,
        .js-plotly-plot,
        .plot-container,
        .svg-container,
        svg.main-svg {
            width: 100% !important;
            min-width: 100% !important;
        }
    </style>
""", unsafe_allow_html=True)

SHEET_ID = "1TXvF6RhSgfJ631UpnWB38Ww1OMvZVx7VonDB_y1pO3s"
DEFAULT_SHEET_NAME = "GOLD"
DEFAULT_COL_NAME = "TOKENS"

# قائمة كافة الأطر الزمانية العالمية المدعومة
ALL_GLOBAL_INTERVALS = [
    "1m", "2m", "3m", "4m", "5m", "10m", "15m", "30m", "45m",
    "1h", "2h", "3h", "4h", "6h", "8h", "12h",
    "1d", "2d", "3d", "1wk", "1mo", "3mo", "6mo", "1y"
]

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
        selected_interval = st.selectbox("⏱️ الإطار الزمني العالمي:", options=ALL_GLOBAL_INTERVALS, index=17, key="bt_interval") # 1d
    with col_bar2:
        period_options = ["1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "10y", "ytd", "max"]
        selected_period = st.selectbox("📅 فترة البيانات:", options=period_options, index=5, key="bt_period")

    run_backtest = st.button("📊 بدء محاكاة الاختبار الرجعي", use_container_width=True, key="run_bt_btn")
    
    if run_backtest and bt_symbols_to_scan:
        bt_results_list = []
        bt_dfs_dict = {}
        progress_bar = st.progress(0)
        status_text = st.empty()

        download_interval = selected_interval if selected_interval in ["1m", "5m", "15m", "30m", "1h", "1d", "1wk", "1mo"] else "1h"

        for idx, sym in enumerate(bt_symbols_to_scan):
            status_text.text(f"جاري محاكاة الأصل ({idx+1}/{len(bt_symbols_to_scan)}): {sym}...")
            progress_bar.progress((idx + 1) / len(bt_symbols_to_scan))

            try:
                df_bt = yf.download(sym, period=selected_period, interval=download_interval, progress=False, auto_adjust=False)
                if isinstance(df_bt.columns, pd.MultiIndex):
                    df_bt.columns = df_bt.columns.get_level_values(0)
                
                trades = backtest_strategy(df_bt, interval=selected_interval)
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
            
            # أ & ب. الإشارات الناجحة والخاسرة
            if "Result" in trades_df.columns:
                wins_count = len(trades_df[trades_df["Result"].astype(str).str.upper().str.contains("WIN")])
                losses_count = len(trades_df[trades_df["Result"].astype(str).str.upper().str.contains("LOSS")])
            elif "Head Result" in trades_df.columns:
                wins_count = len(trades_df[trades_df["Head Result"] == "WIN"])
                losses_count = total_signals - wins_count
            else:
                wins_count = 0
                losses_count = 0

            # ج. كم يوم ما بين الدخول وإغلاق المركز
            duration_str = "غير متاح"
            if "Entry Date" in trades_df.columns and "Exit Date" in trades_df.columns:
                trades_df["Entry Date"] = pd.to_datetime(trades_df["Entry Date"])
                trades_df["Exit Date"] = pd.to_datetime(trades_df["Exit Date"])
                trades_df["مدة المركز (أيام)"] = (trades_df["Exit Date"] - trades_df["Entry Date"]).dt.days
                avg_duration = trades_df["مدة المركز (أيام)"].mean()
                duration_str = f"{avg_duration:.1f} يوم (متوسط)" if not pd.isna(avg_duration) else "غير محدد"
            elif "time" in trades_df.columns and "close_time" in trades_df.columns:
                trades_df["time"] = pd.to_datetime(trades_df["time"])
                trades_df["close_time"] = pd.to_datetime(trades_df["close_time"])
                trades_df["مدة المركز (أيام)"] = (trades_df["close_time"] - trades_df["time"]).dt.days
                avg_duration = trades_df["مدة المركز (أيام)"].mean()
                duration_str = f"{avg_duration:.1f} يوم (متوسط)" if not pd.isna(avg_duration) else "غير محدد"

            # د. شروط الدخول للمركز التي تحققت
            conditions_found = []
            if "Entry Conditions" in trades_df.columns:
                conditions_found = trades_df["Entry Conditions"].dropna().unique().tolist()
            elif "Pattern" in trades_df.columns:
                conditions_found = trades_df["Pattern"].dropna().unique().tolist()
            elif "pattern" in trades_df.columns:
                conditions_found = trades_df["pattern"].dropna().unique().tolist()
            
            cond_display = " | ".join([str(c) for c in conditions_found]) if conditions_found else "اختراق خط العنق + اكتمال هيكل النمط (engine.py)"

            st.markdown(f"### 📊 النتائج التفصيلية للأصل: **{active_sym}**")
            
            m1, m2, m3 = st.columns(3)
            m1.metric("✅ أ. الإشارات الناجحة", wins_count)
            m2.metric("❌ ب. الإشارات الخاسرة", losses_count)
            m3.metric("⏱️ ج. الأيام بين الدخول والإغلاق", duration_str)

            st.markdown(f"""
            <div style="background-color: #F8F9FA; border: 1px solid #DADCE0; border-radius: 12px; padding: 16px; margin-top: 10px; margin-bottom: 20px;">
                <h4 style="margin-top:0; color: #0B57D0;">📋 ملخص نتائج المحاكاة والشروط المتحققة:</h4>
                <ul style="line-height: 1.8; margin-bottom: 0;">
                    <li><b>أ. عدد الإشارات الناجحة:</b> <span style="color: #137333; font-weight: bold;">{wins_count} إشارة ناجحة</span></li>
                    <li><b>ب. عدد الإشارات الخاسرة:</b> <span style="color: #C5221F; font-weight: bold;">{losses_count} إشارة خاسرة</span></li>
                    <li><b>ج. مدة المركز (من الدخول حتى الإغلاق):</b> <b>{duration_str}</b></li>
                    <li><b>د. شروط الدخول المتحققة للمركز:</b> <code>{cond_display}</code></li>
                </ul>
            </div>
            """, unsafe_allow_html=True)
            
            if active_sym in bt_dfs_dict and not bt_dfs_dict[active_sym].empty:
                df_bt_res = bt_dfs_dict[active_sym]
                st.markdown("#### 📈 الرسم الفني المطور (هيكل النمط + خط العنق)")
                
                fig_bt = go.Figure()
                fig_bt.add_trace(go.Candlestick(
                    x=df_bt_res.index, 
                    open=df_bt_res["Open"], 
                    high=df_bt_res["High"], 
                    low=df_bt_res["Low"], 
                    close=df_bt_res["Close"],
                    name="السعر", 
                    increasing_line_color="#137333", 
                    decreasing_line_color="#C5221F"
                ))
                
                if not trades_df.empty and 'nodes' in trades_df.columns:
                    for idx, row in trades_df.iterrows():
                        nodes = row.get('nodes', [])
                        if isinstance(nodes, list) and nodes:
                            sorted_nodes = sorted(nodes, key=lambda item: pd.to_datetime(item[0]))
                            x_nodes = [n[0] for n in sorted_nodes]
                            y_nodes = [n[1] for n in sorted_nodes]
                            
                            fig_bt.add_trace(go.Scatter(
                                x=x_nodes, 
                                y=y_nodes, 
                                mode="lines+markers", 
                                line=dict(color="#C5221F", width=2.5),
                                marker=dict(size=7, color="#0B57D0"), 
                                name=f"النمط #{idx+1}"
                            ))

                            neck_nodes = row.get('neckline_nodes', [])
                            if isinstance(neck_nodes, list) and len(neck_nodes) >= 2:
                                fig_bt.add_trace(go.Scatter(
                                    x=[neck_nodes[0][0], neck_nodes[1][0]], 
                                    y=[neck_nodes[0][1], neck_nodes[1][1]],
                                    mode="lines", 
                                    line=dict(color="#FF9800", width=2, dash="dot"),
                                    name=f"خط العنق #{idx+1}"
                                ))

                fig_bt.update_layout(
                    template="plotly_white", 
                    height=550, 
                    xaxis_rangeslider_visible=False, 
                    margin=dict(l=10, r=20, t=10, b=20), 
                    autosize=True
                )
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
        selected_interval = st.selectbox("⏱️ الإطار الزمني للفحص:", options=ALL_GLOBAL_INTERVALS, index=17, key="live_interval") # 1d
    with col_bar2:
        period_options = ["1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "10y", "ytd", "max"]
        selected_period = st.selectbox("📅 نطاق البيانات:", options=period_options, index=10, key="live_period")

    run_scan = st.button("🚀 بدء المسح والتحليل الفوري", use_container_width=True, key="run_live_btn")

    if run_scan and symbols_to_scan:
        valid_signals = []
        progress_bar = st.progress(0)
        status_text = st.empty()

        download_interval = selected_interval if selected_interval in ["1m", "5m", "15m", "30m", "1h", "1d", "1wk", "1mo"] else "1h"

        for idx, sym in enumerate(symbols_to_scan):
            status_text.text(f"جاري الفحص ({idx+1}/{len(symbols_to_scan)}): {sym}...")
            progress_bar.progress((idx + 1) / len(symbols_to_scan))

            try:
                df = yf.download(sym, period=selected_period, interval=download_interval, progress=False, auto_adjust=False)
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)

                if not df.empty and len(df) >= 20:
                    result = run_full_analysis(df, interval=selected_interval)
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
            entry_val = active_result.get('entry', 0)
            sl_val = active_result.get('sl', 0)
            tp_val = active_result.get('tp', 0)

            e1.metric("🎯 سعر الدخول (Entry)", f"{entry_val}")
            e2.metric("🛑 وقف الخسارة (Stop Loss)", f"{sl_val}")
            e3.metric("🏆 الهدف (Target)", f"{tp_val}")

            if df_res is not None and not df_res.empty:
                fig = go.Figure()
                fig.add_trace(go.Candlestick(
                    x=df_res.index, 
                    open=df_res["Open"], 
                    high=df_res["High"], 
                    low=df_res["Low"], 
                    close=df_res["Close"],
                    name="السعر", 
                    increasing_line_color="#137333", 
                    decreasing_line_color="#C5221F"
                ))

                nodes = active_result.get("nodes", [])
                if nodes:
                    sorted_nodes = sorted(nodes, key=lambda item: pd.to_datetime(item[0]))
                    x_nodes = [n[0] for n in sorted_nodes]
                    y_nodes = [n[1] for n in sorted_nodes]
                    fig.add_trace(go.Scatter(
                        x=x_nodes, 
                        y=y_nodes, 
                        mode="lines+markers",
                        line=dict(color="#C5221F", width=2.5),
                        marker=dict(size=7, color="#0B57D0"), 
                        name=f"{pattern}"
                    ))

                neckline_nodes = active_result.get("neckline_nodes", [])
                if neckline_nodes and len(neckline_nodes) >= 2:
                    x_neck = [n[0] for n in neckline_nodes]
                    y_neck = [n[1] for n in neckline_nodes]
                    fig.add_trace(go.Scatter(
                        x=x_neck, 
                        y=y_neck, 
                        mode="lines",
                        line=dict(color="#FF9800", width=2, dash="dash"),
                        name="خط العنق (Neckline)"
                    ))

                            if entry_val:
                fig.add_hline(
                    y=entry_val, 
                    line_dash="dash", 
                    line_color="#2196F3", 
                    annotation_text="دخول (Entry)", 
                    annotation_position="top right"
                )
            if sl_val:
                fig.add_hline(
                    y=sl_val, 
                    line_dash="dash", 
                    line_color="#F44336", 
                    annotation_text="وقف (SL)", 
                    annotation_position="bottom right"
                )
            if tp_val:
                fig.add_hline(
                    y=tp_val, 
                    line_dash="dash", 
                    line_color="#4CAF50", 
                    annotation_text="هدف (TP)", 
                    annotation_position="top right"
                )

            fig.update_layout(
                template="plotly_white", 
                height=550, 
                xaxis_rangeslider_visible=False, 
                margin=dict(l=10, r=20, t=10, b=20), 
                autosize=True
            )
            st.plotly_chart(fig, use_container_width=True)
            
