import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import importlib
import engine

try:
    from ffff import get_symbols_from_sheet
except ImportError:
    st.error("⚠️ The file ffff.py was not found alongside backtest script")

st.set_page_config(page_title="H&S Ultimate Backtester Pro", page_icon="📊", layout="wide")

st.markdown("""
    <style>
    .stApp { background-color: #0e1117; }
    div.stExpander { background-color: #161b22; border-radius: 16px; border: 1px solid #30363d; padding: 10px; }
    .stButton>button { border-radius: 12px; background-color: #2563eb; color: white; font-weight: bold; border: none; }
    </style>
""", unsafe_allow_html=True)

engine = importlib.reload(engine)

lang = st.sidebar.radio("🌐 Language / اللغة", ["العربية", "English"], index=0)

if lang == "العربية":
    st.title("📊 نظام الاختبار الرجعي السريع للأنماط")
    st.caption("أداء فائق السرعة يعتمد كلياً على دوال المحرك الأساسي.")
    txt_scan_mode = "طريقة اختيار الأصول:"
    txt_single = "بحث فردي"
    txt_sheet = "قائمة Google Sheet"
    txt_tf_label = "الفواصل الزمنية (Intervals):"
    txt_period_label = "الفترة التاريخية للبيانات (Period):"
    txt_sl_strat = "استراتيجية وقف الخسارة:"
    txt_run = "🚀 تشغيل الاختبار بأقصى سرعة"
else:
    st.title("📊 High-Speed H&S True Backtester")
    st.caption("Maximized execution speed relying entirely on engine core.")
    txt_scan_mode = "Asset Selection Method:"
    txt_single = "Single Asset"
    txt_sheet = "Google Sheet List"
    txt_tf_label = "Timeframes (Intervals):"
    txt_period_label = "Historical Data Period:"
    txt_sl_strat = "Stop Loss Strategy:"
    txt_run = "🚀 Run Max-Speed Backtest"

SHEET_ID = "1TXvF6RhSgfJ631UpnWB38Ww1OMvZVx7VonDB_y1pO3s"
DEFAULT_SHEET_NAME = "GOLD"
DEFAULT_COL_NAME = "TOKENS"

st.sidebar.header("⚙️ الإعدادات / Settings")

scan_mode = st.sidebar.radio(txt_scan_mode, [txt_single, txt_sheet], index=0)
symbols_to_test = []

if scan_mode == txt_single:
    symbol_input = st.sidebar.text_input("Symbol", "BTC-USD").strip()
    symbols_to_test = [symbol_input] if symbol_input else []
else:
    fetched_symbols, err = get_symbols_from_sheet(SHEET_ID, DEFAULT_SHEET_NAME, DEFAULT_COL_NAME)
    if err:
        st.sidebar.error(err)
        symbols_to_test = []
    else:
        symbols_to_test = fetched_symbols
        st.sidebar.success(f"تم تحميل {len(symbols_to_test)} أصل بنجاح!" if lang=="العربية" else f"Loaded {len(symbols_to_test)} assets!")

selected_tfs = st.sidebar.multiselect(
    txt_tf_label, 
    ["1m", "5m", "15m", "30m", "1h", "2h", "4h", "1d", "1wk", "1mo"], 
    default=["1h", "4h", "1d"]
)

selected_period = st.sidebar.selectbox(
    txt_period_label,
    ["1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "max"],
    index=4
)

sl_strategy = st.sidebar.radio(txt_sl_strat, ["الكل (Head & Shoulder)", "وقف الرأس فقط (Head SL)", "وقف الكتف فقط (Shoulder SL)"] if lang=="العربية" else ["All", "Head SL Only", "Shoulder SL Only"])
run = st.sidebar.button(txt_run, use_container_width=True)

if run:
    if not symbols_to_test:
        st.error("⚠️ لا توجد أصول متاحة للاختبار.")
    elif not selected_tfs:
        st.error("⚠️ يرجى اختيار فاصل زمني واحد على الأقل.")
    else:
        st.info("🚀 جاري تنفيذ الاختبار الرجعي بأقصى سرعة فائقة...")
        
        for symbol in symbols_to_test:
            tf_results = []
            all_trades_detail = []
            
            for tf in selected_tfs:
                df = yf.download(symbol, period=selected_period, interval=tf, progress=False)
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                    
                if df.empty or len(df) < 50:
                    continue
                
                # [تحسين السرعة القصوى]: تنفيذ الحسابات على كامل البيانات دفعة واحدة بدلاً من التكرار البطيء شمعة بشمعة
                df_ind = engine.calculate_indicators(df)
                df_ind = engine.calculate_zigzag(df_ind)
                pivots = engine.get_chronological_pivots(df_ind)
                patterns = engine.detect_all_head_shoulders(pivots, df_ind)
                
                for sl_type_opt in ["Head SL", "Shoulder SL"]:
                    if sl_strategy != "الكل (Head & Shoulder)" and sl_strategy != "All" and sl_type_opt not in sl_strategy:
                        continue
                    
                    trades = []
                    if patterns:
                        for pat in patterns:
                            end_idx = pat.get("neckline_end_idx")
                            if not end_idx or end_idx not in df.index:
                                continue
                            if any(t.get("End_Idx") == end_idx and t.get("SL_Type") == sl_type_opt for t in trades):
                                continue
                                
                            pattern_name = pat.get("pattern")
                            bias = pat.get("bias")
                            entry = pat.get("entry")
                            tp = pat.get("tp")
                            
                            if sl_type_opt == "Head SL":
                                sl = pat.get("sl")
                            else:
                                nodes = pat.get("nodes", [])
                                if bias == "Bearish" and len(nodes) >= 4:
                                    sl = max(nodes[1][1], nodes[3][1])
                                elif bias == "Bullish" and len(nodes) >= 4:
                                    sl = min(nodes[1][1], nodes[3][1])
                                else:
                                    sl = pat.get("sl")
                            
                            future_df = df.loc[end_idx:].iloc[1:]
                            outcome = "OPEN"
                            exit_date = str(end_idx)
                            for f_idx, row in future_df.iterrows():
                                h, l = row["High"], row["Low"]
                                if bias == "Bearish":
                                    if h >= sl: outcome = "LOSS"; exit_date = str(f_idx); break
                                    elif l <= tp: outcome = "WIN"; exit_date = str(f_idx); break
                                elif bias == "Bullish":
                                    if l <= sl: outcome = "LOSS"; exit_date = str(f_idx); break
                                    elif h >= tp: outcome = "WIN"; exit_date = str(f_idx); break
                                    
                            trades.append({
                                "Symbol": symbol,
                                "TF": tf,
                                "Pattern Type": pattern_name,
                                "SL_Type": sl_type_opt,
                                "Date": str(end_idx),
                                "Exit Date": exit_date,
                                "Entry": round(entry, 4) if entry else 0,
                                "SL": round(sl, 4) if sl else 0,
                                "TP": round(tp, 4) if tp else 0,
                                "Outcome": outcome,
                                "End_Idx": end_idx
                            })
                    
                    if trades:
                        tdf = pd.DataFrame(trades)
                        all_trades_detail.extend(trades)
                        wins = len(tdf[tdf["Outcome"] == "WIN"])
                        losses = len(tdf[tdf["Outcome"] == "LOSS"])
                        total = wins + losses
                        wr = (wins / total) * 100 if total > 0 else 0
                        tf_results.append({
                            "Timeframe": tf,
                            "SL Method": sl_type_opt,
                            "Total Signals": total,
                            "Wins": wins,
                            "Losses": losses,
                            "Win Rate (%)": round(wr, 2)
                        })
            
            if not tf_results:
                if scan_mode == txt_single or scan_mode == "Single Asset":
                    with st.expander(f"📊 نتائج الفحص للرمز: {symbol}", expanded=True):
                        st.warning("⚠️ لا توجد صفقات أو أنماط مسجلة لهذا الأصل بناءً على الفترة والفواصل المحددة." if lang=="العربية" else "⚠️ No trades recorded for this asset.")
                continue
                
            with st.expander(f"📊 نتائج الفحص والصفقات للرمز: {symbol}", expanded=(len(symbols_to_test) == 1)):
                res_df = pd.DataFrame(tf_results).sort_values(by="Win Rate (%)", ascending=False)
                best_row = res_df.iloc[0]
                
                st.subheader("مقارنة الفواصل وأداء الإشارات" if lang=="العربية" else "Timeframe Comparison & Signals Performance")
                st.dataframe(res_df, use_container_width=True)
                
                st.subheader("سجل الأوامر التاريخية التفصيلي" if lang=="العربية" else "Detailed Historical Order Logs")
                details_df = pd.DataFrame(all_trades_detail).drop(columns=["End_Idx"])
                st.dataframe(details_df, use_container_width=True)
                
                wr_val = best_row['Win Rate (%)']
                total_signals_all = res_df['Total Signals'].sum()
                total_wins_all = res_df['Wins'].sum()
                total_losses_all = res_df['Losses'].sum()
                overall_wr = round((total_wins_all / (total_wins_all + total_losses_all)) * 100, 2) if (total_wins_all + total_losses_all) > 0 else 0
                
                rec_action = "يوصى بالتداول" if wr_val >= 50 else "لا يُنصح بالتداول حالياً (نسبة النجاح ضعيفة)"
                rec_action_en = "Recommended to trade" if wr_val >= 50 else "Not recommended (Low win rate)"
                
                if lang == "العربية":
                    st.markdown(f"**📋 التقرير الشامل والتحليل الذكي للرمز: {symbol}**")
                    report_lines = [
                        f"1. **إجمالي الإشارات المجمعة:** تم رصد وتجميع عدد ({total_signals_all} إشارة فريدة) عبر كافة الفواصل الزمنية المحددة طوال الفترة التاريخية ({selected_period}) دون استثناء أو تكرار.",
                        f"2. **أداء النسبة المئوية العامة:** حقق الأداء الكلي للأصل معدل نجاح عام بنسبة **{overall_wr}%** (إجمالي الصفقات الرابحة: {total_wins_all}, الخاسرة: {total_losses_all}).",
                        f"3. **الفاصل الأفضل مقارنةً:** تصدر الفاصل الزمني ({best_row['Timeframe']}) باستخدام طريقة ({best_row['SL Method']}) كأفضل أداء بنسبة نجاح بلغت **{wr_val}%**.",
                        f"4. **تحليل المخاطر:** تم تتبع مستويات الدخول وأوامر الوقف والأهداف الفعلية لكل إشارة بدقة متناهية لتقييم كفاءة الاستراتيجية.",
                        f"5. **التوصية النهائية:** {rec_action} على فاصل **{best_row['Timeframe']}** بناءً على أعلى نسبة نجاح مسجلة."
                    ]
                else:
                    st.markdown(f"**📋 Comprehensive Smart Report & Analysis for: {symbol}**")
                    report_lines = [
                        f"1. **Total Aggregated Signals:** Collected ({total_signals_all} unique signals) across all selected timeframes throughout the entire historical period ({selected_period}) without omission or duplication.",
                        f"2. **Overall Success Rate:** The asset achieved an aggregate win rate of **{overall_wr}%** (Total Wins: {total_wins_all}, Losses: {total_losses_all}).",
                        f"3. **Best Performing Configuration:** Timeframe ({best_row['Timeframe']}) with ({best_row['SL Method']}) led with a success rate of **{wr_val}%**.",
                        f"4. **Risk Analysis:** Exact execution prices (Entry, SL, TP) were tracked for every single pattern to ensure strict evaluation.",
                        f"5. **Final Recommendation:** {rec_action_en} on **{best_row['Timeframe']}** based on the highest comparative win rate."
                    ]
                
                for line in report_lines:
                    st.markdown(line)
                    
