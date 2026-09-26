# -*- coding: utf-8 -*-
import calendar, datetime
import streamlit as st, yfinance as yf, plotly.graph_objects as go, pandas as pd
from engine import run_full_analysis, backtest_strategy
try: from ffff import get_symbols_from_sheet
except ImportError: pass

st.set_page_config(page_title="Smart Market Analyzer & Backtest Lab", page_icon="📈", layout="wide", initial_sidebar_state="collapsed")

# 1. تنسيق CSS لتوسيع الشارت والشاشة أفقياً بالكامل
st.markdown("<style>.main .block-container{max-width:100%!important;padding:0.5rem!important;} div[data-testid='stPlotlyChart']{width:100%!important;}</style>", unsafe_allow_html=True)

SHEET_ID, DEFAULT_SHEET_NAME, DEFAULT_COL_NAME = "1TXvF6RhSgfJ631UpnWB38Ww1OMvZVx7VonDB_y1pO3s", "GOLD", "TOKENS"
ALL_GLOBAL_INTERVALS = ["1m","2m","3m","4m","5m","10m","15m","30m","45m","1h","2h","3h","4h","6h","8h","12h","1d","2d","3d","1wk","1mo","3mo","6mo","1y"]

for k, v in [("current_symbol", "NZDCAD=X"), ("status_summary", "⚡ Live Scan & Backtest Lab • جاهز"), ("scanned_signals", []), ("backtest_scanned_signals", []), ("backtest_dfs", {})]:
    if k not in st.session_state: st.session_state[k] = v

st.markdown(f'''<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:15px;">
    <div style="border:1px solid #DADCE0;background:#FFF;border-radius:16px;padding:8px 14px;font-weight:700;color:#0B57D0;">📈 {st.session_state.current_symbol}</div>
    <div style="border:1px solid #DADCE0;background:#FFF;border-radius:30px;padding:8px 14px;font-weight:700;color:#0B57D0;">{st.session_state.status_summary}</div>
</div>''', unsafe_allow_html=True)

app_mode = st.radio("وضع التطبيق:", ["🚀 الماسح الحي للأسواق", "🧪 مختبر الاختبار الرجعي (Backtest)"], horizontal=True)
st.markdown("---")

# ================= BACKTEST MODE =================
if app_mode == "🧪 مختبر الاختبار الرجعي (Backtest)":
    st.markdown("### 🧪 مختبر تحليل الأداء التاريخي")
    bt_scan_mode = st.radio("طريقة فحص الاختبار الرجعي:", ["سهم فردي", "مسح كلي لشيت الأصول"], horizontal=True)
    bt_symbols = [st.text_input("رمز الأصل", value="EURUSD=X")] if bt_scan_mode == "سهم فردي" else get_symbols_from_sheet(SHEET_ID, DEFAULT_SHEET_NAME, DEFAULT_COL_NAME)[0]

    # قائمة السنوات والشهور للـ 24 شهراً الماضية
    now = datetime.datetime.now()
    available_years = [now.year, now.year - 1, now.year - 2]
    months_dict = {
        1: "01 - يناير", 2: "02 - فبراير", 3: "03 - مارس", 4: "04 - إبريل",
        5: "05 - مايو", 6: "06 - يونيو", 7: "07 - يوليو", 8: "08 - أغسطس",
        9: "09 - سبتمبر", 10: "10 - أكتوبر", 11: "11 - نوفمبر", 12: "12 - ديسمبر"
    }

    c_yr, c_mo, c_tf = st.columns(3)
    selected_year = c_yr.selectbox("📅 السنة:", available_years, index=0)
    selected_month = c_mo.selectbox("🗓️ الشهر:", list(months_dict.keys()), format_func=lambda x: months_dict[x], index=now.month - 1)
    selected_interval = c_tf.selectbox("⏱️ الإطار الزمني:", ALL_GLOBAL_INTERVALS, index=17)

    # حساب تاريخ بداية ونهاية الشهر المختار تلقائياً
    _, last_day = calendar.monthrange(selected_year, selected_month)
    start_date = f"{selected_year}-{selected_month:02d}-01"
    end_date = f"{selected_year}-{selected_month:02d}-{last_day:02d}"

    if st.button("📊 بدء محاكاة الاختبار الرجعي", use_container_width=True) and bt_symbols:
        results, dfs = [], {}
        dl_int = selected_interval if selected_interval in ["1m","5m","15m","30m","1h","1d","1wk","1mo"] else "1h"
        p_bar, s_txt = st.progress(0), st.empty()
        for idx, sym in enumerate(bt_symbols):
            s_txt.text(f"محاكاة ({idx+1}/{len(bt_symbols)}): {sym}...")
            p_bar.progress((idx + 1) / len(bt_symbols))
            try:
                # تنزيل البيانات عبر تواريخ start و end للشهر المحدد
                df = yf.download(sym, start=start_date, end=end_date, interval=dl_int, progress=False, auto_adjust=False)
                if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
                trades = backtest_strategy(df, interval=selected_interval)
                if trades:
                    tdf = pd.DataFrame(trades)
                    results.append({"symbol": sym, "trades_df": tdf, "total_signals": len(tdf)})
                    dfs[sym] = df
            except Exception: pass
        s_txt.empty(); p_bar.empty()
        st.session_state.backtest_scanned_signals, st.session_state.backtest_dfs = results, dfs

    if st.session_state.backtest_scanned_signals:
        res_list, dfs_dict = st.session_state.backtest_scanned_signals, st.session_state.backtest_dfs
        
        if bt_scan_mode == "مسح كلي لشيت الأصول":
            opts = [f"{i['symbol']} | الصفقات: {i['total_signals']}" for i in res_list]
            active_item = res_list[opts.index(st.selectbox("👇 اختر الأصل:", opts))]
        else:
            active_item = res_list[0]
            
        active_sym, trades_df = active_item["symbol"], active_item["trades_df"]
        st.session_state.current_symbol = active_sym

        # 2. حساب النتائج المحددة (أ، ب، ج، د)
        res_col = "Result" if "Result" in trades_df else ("Head Result" if "Head Result" in trades_df else None)
        wins = len(trades_df[trades_df[res_col].astype(str).str.upper().str.contains("WIN")]) if res_col else 0
        losses = len(trades_df) - wins

        dur_str = "غير متاح"
        if "Entry Date" in trades_df and "Exit Date" in trades_df:
            days = (pd.to_datetime(trades_df["Exit Date"]) - pd.to_datetime(trades_df["Entry Date"])).dt.days
            dur_str = f"{days.mean():.1f} يوم (متوسط)"
        elif "time" in trades_df and "close_time" in trades_df:
            days = (pd.to_datetime(trades_df["close_time"]) - pd.to_datetime(trades_df["time"])).dt.days
            dur_str = f"{days.mean():.1f} يوم (متوسط)"

        conds = trades_df.get("Entry Conditions", trades_df.get("Pattern", trades_df.get("pattern", pd.Series()))).dropna().unique().tolist()
        cond_str = " | ".join(map(str, conds)) if conds else "اختراق خط العنق + اكتمال هيكل النمط"

        st.markdown(f"### 📊 نتائج الاختبار لشهر {selected_month}/{selected_year}: **{active_sym}**")
        m1, m2, m3 = st.columns(3)
        m1.metric("✅ أ. الإشارات الناجحة", wins)
        m2.metric("❌ ب. الإشارات الخاسرة", losses)
        m3.metric("⏱️ ج. مدة المركز بالأيام", dur_str)

        st.info(f"**د. شروط الدخول المتحققة:** {cond_str}")

        if active_sym in dfs_dict and not dfs_dict[active_sym].empty:
            df_res = dfs_dict[active_sym]
            fig = go.Figure(data=[go.Candlestick(x=df_res.index, open=df_res["Open"], high=df_res["High"], low=df_res["Low"], close=df_res["Close"], name="السعر")])
            if "nodes" in trades_df:
                for idx, row in trades_df.iterrows():
                    if isinstance(row.get('nodes'), list) and row['nodes']:
                        sn = sorted(row['nodes'], key=lambda x: pd.to_datetime(x[0]))
                        fig.add_trace(go.Scatter(x=[n[0] for n in sn], y=[n[1] for n in sn], mode="lines+markers", name=f"نمط #{idx+1}"))
            fig.update_layout(template="plotly_white", height=500, margin=dict(l=5, r=5, t=10, b=10), xaxis_rangeslider_visible=False)
            st.plotly_chart(fig, use_container_width=True)
        st.dataframe(trades_df, use_container_width=True)

# ================= LIVE SCAN MODE =================
else:
    scan_mode = st.radio("طريقة الفحص:", ["سهم فردي", "مسح كلي لشيت الأصول"], horizontal=True)
    symbols = [st.text_input("رمز الأصل", value="NZDCAD=X")] if scan_mode == "سهم فردي" else get_symbols_from_sheet(SHEET_ID, DEFAULT_SHEET_NAME, DEFAULT_COL_NAME)[0]
    c1, c2 = st.columns(2)
    selected_interval = c1.selectbox("⏱️ الإطار الزمني:", ALL_GLOBAL_INTERVALS, index=17)
    selected_period = c2.selectbox("📅 نطاق البيانات:", ["1d","5d","1mo","3mo","6mo","1y","2y","5y","10y","ytd","max"], index=10)

    if st.button("🚀 بدء المسح والتحليل الفوري", use_container_width=True) and symbols:
        valid, p_bar, s_txt = [], st.progress(0), st.empty()
        dl_int = selected_interval if selected_interval in ["1m","5m","15m","30m","1h","1d","1wk","1mo"] else "1h"
        for idx, sym in enumerate(symbols):
            s_txt.text(f"فحص ({idx+1}/{len(symbols)}): {sym}...")
            p_bar.progress((idx + 1) / len(symbols))
            try:
                df = yf.download(sym, period=selected_period, interval=dl_int, progress=False, auto_adjust=False)
                if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
                if not df.empty and len(df) >= 20:
                    res = run_full_analysis(df, interval=selected_interval)
                    if res["signal"] in ["STRONG BUY", "STRONG SELL"] or scan_mode == "سهم فردي":
                        valid.append({"symbol": sym, "result": res})
            except Exception: pass
        s_txt.empty(); p_bar.empty()
        st.session_state.scanned_signals = valid

    if st.session_state.scanned_signals:
        sigs = st.session_state.scanned_signals
        
        if scan_mode == "مسح كلي لشيت الأصول":
            opts = [f"{i['symbol']} | {i['result']['signal']}" for i in sigs]
            active_res = sigs[opts.index(st.selectbox("👇 اختر الأصل:", opts))]['result']
        else:
            active_res = sigs[0]['result']

        st.session_state.current_symbol = active_res.get("symbol", symbols[0])
        e1, e2, e3 = st.columns(3)
        e1.metric("🎯 سعر الدخول", f"{active_res.get('entry', 0)}")
        e2.metric("🛑 وقف الخسارة", f"{active_res.get('sl', 0)}")
        e3.metric("🏆 الهدف", f"{active_res.get('tp', 0)}")

        df_res = active_res.get("df")
        if df_res is not None and not df_res.empty:
            fig = go.Figure(data=[go.Candlestick(x=df_res.index, open=df_res["Open"], high=df_res["High"], low=df_res["Low"], close=df_res["Close"], name="السعر")])
            for val, col, txt in [(active_res.get('entry'), "#2196F3", "دخول"), (active_res.get('sl'), "#F44336", "وقف"), (active_res.get('tp'), "#4CAF50", "هدف")]:
                if val: fig.add_hline(y=val, line_dash="dash", line_color=col, annotation_text=txt)
            fig.update_layout(template="plotly_white", height=500, margin=dict(l=5, r=5, t=10, b=10), xaxis_rangeslider_visible=False)
            st.plotly_chart(fig, use_container_width=True)
            
