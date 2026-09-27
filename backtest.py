# -*- coding: utf-8 -*-
import calendar, datetime
import streamlit as st, yfinance as yf, plotly.graph_objects as go, pandas as pd
from engine import run_full_analysis, backtest_strategy
try: from ffff import get_symbols_from_sheet
except ImportError: pass

st.set_page_config(page_title="Smart Market Analyzer & Backtest Lab", page_icon="ًں“ˆ", layout="wide", initial_sidebar_state="collapsed")

# 1. طھظ†ط³ظٹظ‚ CSS ظ„طھظˆط³ظٹط¹ ط§ظ„ط´ط§ط±طھ ظˆط§ظ„ط´ط§ط´ط© ط£ظپظ‚ظٹط§ظ‹ ط¨ط§ظ„ظƒط§ظ…ظ„
st.markdown("<style>.main .block-container{max-width:100%!important;padding:0.5rem!important;} div[data-testid='stPlotlyChart']{width:100%!important;}</style>", unsafe_allow_html=True)

SHEET_ID, DEFAULT_SHEET_NAME, DEFAULT_COL_NAME = "1TXvF6RhSgfJ631UpnWB38Ww1OMvZVx7VonDB_y1pO3s", "GOLD", "TOKENS"
ALL_GLOBAL_INTERVALS = ["1m","2m","3m","4m","5m","10m","15m","30m","45m","1h","2h","3h","4h","6h","8h","12h","1d","2d","3d","1wk","1mo","3mo","6mo","1y"]

for k, v in [("current_symbol", "NZDCAD=X"), ("status_summary", "âڑ، Live Scan & Backtest Lab â€¢ ط¬ط§ظ‡ط²"), ("scanned_signals", []), ("backtest_scanned_signals", []), ("backtest_dfs", {})]:
    if k not in st.session_state: st.session_state[k] = v

st.markdown(f'''<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:15px;">
    <div style="border:1px solid #DADCE0;background:#FFF;border-radius:16px;padding:8px 14px;font-weight:700;color:#0B57D0;">ًں“ˆ {st.session_state.current_symbol}</div>
    <div style="border:1px solid #DADCE0;background:#FFF;border-radius:30px;padding:8px 14px;font-weight:700;color:#0B57D0;">{st.session_state.status_summary}</div>
</div>''', unsafe_allow_html=True)

app_mode = st.radio("ظˆط¶ط¹ ط§ظ„طھط·ط¨ظٹظ‚:", ["ًںڑ€ ط§ظ„ظ…ط§ط³ط­ ط§ظ„ط­ظٹ ظ„ظ„ط£ط³ظˆط§ظ‚", "ًں§ھ ظ…ط®طھط¨ط± ط§ظ„ط§ط®طھط¨ط§ط± ط§ظ„ط±ط¬ط¹ظٹ (Backtest)"], horizontal=True)
st.markdown("---")

# ================= BACKTEST MODE =================
if app_mode == "ًں§ھ ظ…ط®طھط¨ط± ط§ظ„ط§ط®طھط¨ط§ط± ط§ظ„ط±ط¬ط¹ظٹ (Backtest)":
    st.markdown("### ًں§ھ ظ…ط®طھط¨ط± طھط­ظ„ظٹظ„ ط§ظ„ط£ط¯ط§ط، ط§ظ„طھط§ط±ظٹط®ظٹ")
    bt_scan_mode = st.radio("ط·ط±ظٹظ‚ط© ظپط­طµ ط§ظ„ط§ط®طھط¨ط§ط± ط§ظ„ط±ط¬ط¹ظٹ:", ["ط³ظ‡ظ… ظپط±ط¯ظٹ", "ظ…ط³ط­ ظƒظ„ظٹ ظ„ط´ظٹطھ ط§ظ„ط£طµظˆظ„"], horizontal=True)
    bt_symbols = [st.text_input("ط±ظ…ط² ط§ظ„ط£طµظ„", value="EURUSD=X")] if bt_scan_mode == "ط³ظ‡ظ… ظپط±ط¯ظٹ" else get_symbols_from_sheet(SHEET_ID, DEFAULT_SHEET_NAME, DEFAULT_COL_NAME)[0]

    # ظ‚ط§ط¦ظ…ط© ط§ظ„ط³ظ†ظˆط§طھ ظˆط§ظ„ط´ظ‡ظˆط± ظ„ظ„ظ€ 24 ط´ظ‡ط±ط§ظ‹ ط§ظ„ظ…ط§ط¶ظٹط©
    now = datetime.datetime.now()
    available_years = [now.year, now.year - 1, now.year - 2]
    months_dict = {
        1: "01 - ظٹظ†ط§ظٹط±", 2: "02 - ظپط¨ط±ط§ظٹط±", 3: "03 - ظ…ط§ط±ط³", 4: "04 - ط¥ط¨ط±ظٹظ„",
        5: "05 - ظ…ط§ظٹظˆ", 6: "06 - ظٹظˆظ†ظٹظˆ", 7: "07 - ظٹظˆظ„ظٹظˆ", 8: "08 - ط£ط؛ط³ط·ط³",
        9: "09 - ط³ط¨طھظ…ط¨ط±", 10: "10 - ط£ظƒطھظˆط¨ط±", 11: "11 - ظ†ظˆظپظ…ط¨ط±", 12: "12 - ط¯ظٹط³ظ…ط¨ط±"
    }

    c_yr, c_mo, c_tf = st.columns(3)
    selected_year = c_yr.selectbox("ًں“… ط§ظ„ط³ظ†ط©:", available_years, index=0)
    selected_month = c_mo.selectbox("ًں—“ï¸ڈ ط§ظ„ط´ظ‡ط±:", list(months_dict.keys()), format_func=lambda x: months_dict[x], index=now.month - 1)
    selected_interval = c_tf.selectbox("âڈ±ï¸ڈ ط§ظ„ط¥ط·ط§ط± ط§ظ„ط²ظ…ظ†ظٹ:", ALL_GLOBAL_INTERVALS, index=17)

    # ط­ط³ط§ط¨ طھط§ط±ظٹط® ط¨ط¯ط§ظٹط© ظˆظ†ظ‡ط§ظٹط© ط§ظ„ط´ظ‡ط± ط§ظ„ظ…ط®طھط§ط± طھظ„ظ‚ط§ط¦ظٹط§ظ‹
    _, last_day = calendar.monthrange(selected_year, selected_month)
    start_date = f"{selected_year}-{selected_month:02d}-01"
    end_date = f"{selected_year}-{selected_month:02d}-{last_day:02d}"

    if st.button("ًں“ٹ ط¨ط¯ط، ظ…ط­ط§ظƒط§ط© ط§ظ„ط§ط®طھط¨ط§ط± ط§ظ„ط±ط¬ط¹ظٹ", use_container_width=True) and bt_symbols:
        results, dfs = [], {}
        dl_int = selected_interval if selected_interval in ["1m","5m","15m","30m","1h","1d","1wk","1mo"] else "1h"
        p_bar, s_txt = st.progress(0), st.empty()
        for idx, sym in enumerate(bt_symbols):
            s_txt.text(f"ظ…ط­ط§ظƒط§ط© ({idx+1}/{len(bt_symbols)}): {sym}...")
            p_bar.progress((idx + 1) / len(bt_symbols))
            try:
                # طھظ†ط²ظٹظ„ ط§ظ„ط¨ظٹط§ظ†ط§طھ ط¹ط¨ط± طھظˆط§ط±ظٹط® start ظˆ end ظ„ظ„ط´ظ‡ط± ط§ظ„ظ…ط­ط¯ط¯
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
        
        if bt_scan_mode == "ظ…ط³ط­ ظƒظ„ظٹ ظ„ط´ظٹطھ ط§ظ„ط£طµظˆظ„":
            opts = [f"{i['symbol']} | ط§ظ„طµظپظ‚ط§طھ: {i['total_signals']}" for i in res_list]
            active_item = res_list[opts.index(st.selectbox("ًں‘‡ ط§ط®طھط± ط§ظ„ط£طµظ„:", opts))]
        else:
            active_item = res_list[0]
            
        active_sym, trades_df = active_item["symbol"], active_item["trades_df"]
        st.session_state.current_symbol = active_sym

        # 2. ط­ط³ط§ط¨ ط§ظ„ظ†طھط§ط¦ط¬ ط§ظ„ظ…ط­ط¯ط¯ط© (ط£طŒ ط¨طŒ ط¬طŒ ط¯)
        res_col = "Result" if "Result" in trades_df else ("Head Result" if "Head Result" in trades_df else None)
        wins = len(trades_df[trades_df[res_col].astype(str).str.upper().str.contains("WIN")]) if res_col else 0
        losses = len(trades_df) - wins

        dur_str = "ط؛ظٹط± ظ…طھط§ط­"
        if "Entry Date" in trades_df and "Exit Date" in trades_df:
            days = (pd.to_datetime(trades_df["Exit Date"]) - pd.to_datetime(trades_df["Entry Date"])).dt.days
            dur_str = f"{days.mean():.1f} ظٹظˆظ… (ظ…طھظˆط³ط·)"
        elif "time" in trades_df and "close_time" in trades_df:
            days = (pd.to_datetime(trades_df["close_time"]) - pd.to_datetime(trades_df["time"])).dt.days
            dur_str = f"{days.mean():.1f} ظٹظˆظ… (ظ…طھظˆط³ط·)"

        conds = trades_df.get("Entry Conditions", trades_df.get("Pattern", trades_df.get("pattern", pd.Series()))).dropna().unique().tolist()
        cond_str = " | ".join(map(str, conds)) if conds else "ط§ط®طھط±ط§ظ‚ ط®ط· ط§ظ„ط¹ظ†ظ‚ + ط§ظƒطھظ…ط§ظ„ ظ‡ظٹظƒظ„ ط§ظ„ظ†ظ…ط·"

        st.markdown(f"### ًں“ٹ ظ†طھط§ط¦ط¬ ط§ظ„ط§ط®طھط¨ط§ط± ظ„ط´ظ‡ط± {selected_month}/{selected_year}: **{active_sym}**")
        m1, m2, m3 = st.columns(3)
        m1.metric("âœ… ط£. ط§ظ„ط¥ط´ط§ط±ط§طھ ط§ظ„ظ†ط§ط¬ط­ط©", wins)
        m2.metric("â‌Œ ط¨. ط§ظ„ط¥ط´ط§ط±ط§طھ ط§ظ„ط®ط§ط³ط±ط©", losses)
        m3.metric("âڈ±ï¸ڈ ط¬. ظ…ط¯ط© ط§ظ„ظ…ط±ظƒط² ط¨ط§ظ„ط£ظٹط§ظ…", dur_str)

        st.info(f"**ط¯. ط´ط±ظˆط· ط§ظ„ط¯ط®ظˆظ„ ط§ظ„ظ…طھط­ظ‚ظ‚ط©:** {cond_str}")

        if active_sym in dfs_dict and not dfs_dict[active_sym].empty:
            df_res = dfs_dict[active_sym]
            fig = go.Figure(data=[go.Candlestick(x=df_res.index, open=df_res["Open"], high=df_res["High"], low=df_res["Low"], close=df_res["Close"], name="ط§ظ„ط³ط¹ط±")])
            if "nodes" in trades_df:
                for idx, row in trades_df.iterrows():
                    if isinstance(row.get('nodes'), list) and row['nodes']:
                        sn = sorted(row['nodes'], key=lambda x: pd.to_datetime(x[0]))
                        fig.add_trace(go.Scatter(x=[n[0] for n in sn], y=[n[1] for n in sn], mode="lines+markers", name=f"ظ†ظ…ط· #{idx+1}"))
            fig.update_layout(template="plotly_white", height=500, margin=dict(l=5, r=5, t=10, b=10), xaxis_rangeslider_visible=False)
            st.plotly_chart(fig, use_container_width=True)
        st.dataframe(trades_df, use_container_width=True)

# ================= LIVE SCAN MODE =================
else:
    scan_mode = st.radio("ط·ط±ظٹظ‚ط© ط§ظ„ظپط­طµ:", ["ط³ظ‡ظ… ظپط±ط¯ظٹ", "ظ…ط³ط­ ظƒظ„ظٹ ظ„ط´ظٹطھ ط§ظ„ط£طµظˆظ„"], horizontal=True)
    symbols = [st.text_input("ط±ظ…ط² ط§ظ„ط£طµظ„", value="NZDCAD=X")] if scan_mode == "ط³ظ‡ظ… ظپط±ط¯ظٹ" else get_symbols_from_sheet(SHEET_ID, DEFAULT_SHEET_NAME, DEFAULT_COL_NAME)[0]
    c1, c2 = st.columns(2)
    selected_interval = c1.selectbox("âڈ±ï¸ڈ ط§ظ„ط¥ط·ط§ط± ط§ظ„ط²ظ…ظ†ظٹ:", ALL_GLOBAL_INTERVALS, index=17)
    selected_period = c2.selectbox("ًں“… ظ†ط·ط§ظ‚ ط§ظ„ط¨ظٹط§ظ†ط§طھ:", ["1d","5d","1mo","3mo","6mo","1y","2y","5y","10y","ytd","max"], index=10)

    if st.button("ًںڑ€ ط¨ط¯ط، ط§ظ„ظ…ط³ط­ ظˆط§ظ„طھط­ظ„ظٹظ„ ط§ظ„ظپظˆط±ظٹ", use_container_width=True) and symbols:
        valid, p_bar, s_txt = [], st.progress(0), st.empty()
        dl_int = selected_interval if selected_interval in ["1m","5m","15m","30m","1h","1d","1wk","1mo"] else "1h"
        for idx, sym in enumerate(symbols):
            s_txt.text(f"ظپط­طµ ({idx+1}/{len(symbols)}): {sym}...")
            p_bar.progress((idx + 1) / len(symbols))
            try:
                df = yf.download(sym, period=selected_period, interval=dl_int, progress=False, auto_adjust=False)
                if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
                if not df.empty and len(df) >= 20:
                    res = run_full_analysis(df, interval=selected_interval)
                    if res["signal"] in ["STRONG BUY", "STRONG SELL"] or scan_mode == "ط³ظ‡ظ… ظپط±ط¯ظٹ":
                        valid.append({"symbol": sym, "result": res})
            except Exception: pass
        s_txt.empty(); p_bar.empty()
        st.session_state.scanned_signals = valid

    if st.session_state.scanned_signals:
        sigs = st.session_state.scanned_signals
        
        if scan_mode == "ظ…ط³ط­ ظƒظ„ظٹ ظ„ط´ظٹطھ ط§ظ„ط£طµظˆظ„":
            opts = [f"{i['symbol']} | {i['result']['signal']}" for i in sigs]
            active_res = sigs[opts.index(st.selectbox("ًں‘‡ ط§ط®طھط± ط§ظ„ط£طµظ„:", opts))]['result']
        else:
            active_res = sigs[0]['result']

        st.session_state.current_symbol = active_res.get("symbol", symbols[0])
        e1, e2, e3 = st.columns(3)
        e1.metric("ًںژ¯ ط³ط¹ط± ط§ظ„ط¯ط®ظˆظ„", f"{active_res.get('entry', 0)}")
        e2.metric("ًں›‘ ظˆظ‚ظپ ط§ظ„ط®ط³ط§ط±ط©", f"{active_res.get('sl', 0)}")
        e3.metric("ًںڈ† ط§ظ„ظ‡ط¯ظپ", f"{active_res.get('tp', 0)}")

        df_res = active_res.get("df")
        if df_res is not None and not df_res.empty:
            fig = go.Figure(data=[go.Candlestick(x=df_res.index, open=df_res["Open"], high=df_res["High"], low=df_res["Low"], close=df_res["Close"], name="ط§ظ„ط³ط¹ط±")])
            for val, col, txt in [(active_res.get('entry'), "#2196F3", "ط¯ط®ظˆظ„"), (active_res.get('sl'), "#F44336", "ظˆظ‚ظپ"), (active_res.get('tp'), "#4CAF50", "ظ‡ط¯ظپ")]:
                if val: fig.add_hline(y=val, line_dash="dash", line_color=col, annotation_text=txt)
            fig.update_layout(template="plotly_white", height=500, margin=dict(l=5, r=5, t=10, b=10), xaxis_rangeslider_visible=False)
            st.plotly_chart(fig, use_container_width=True)
            
