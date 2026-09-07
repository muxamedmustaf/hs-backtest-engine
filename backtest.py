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

# اختيار اللغة (العربية / English)
lang = st.sidebar.radio("🌐 Language / اللغة", ["العربية", "English"], index=0)

if lang == "العربية":
    st.title("📊 نظام الاختبار الرجعي المتقدم للأنماط")
    st.caption("إصدار دقيق يدمج الفواصل المنفصلة، تفاصيل الصفقات بالأرقام، التقرير الثنائي، وإخفاء الأصول الخالية من الصفقات.")
    txt_scan_mode = "طريقة اختيار الأصول:"
    txt_single = "بحث فردي"
    txt_sheet = "قائمة Google Sheet"
    txt_small_tf = "الفواصل الزمنية الصغيرة والمتوسطة"
    txt_large_tf = "الفواصل الزمنية الكبيرة"
    txt_sl_strat = "استراتيجية وقف الخسارة:"
    txt_run = "🚀 تشغيل الاختبار الشامل"
else:
    st.title("📊 Advanced H&S True Backtester")
    st.caption("Accurate engine integrating split timeframes, precise numerical trade logs, bilingual reports, and empty asset filtering.")
    txt_scan_mode = "Asset Selection Method:"
    txt_single = "Single Asset"
    txt_sheet = "Google Sheet List"
    txt_small_tf = "Small & Medium Timeframes"
    txt_large_tf = "Large Timeframes"
    txt_sl_strat = "Stop Loss Strategy:"
    txt_run = "🚀 Run Comprehensive Backtest"

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

# فصل الفواصل الزمنية إلى مجموعتين (صغيرة وكبيرة)
small_tfs = st.sidebar.multiselect(txt_small_tf, ["1m", "5m", "15m", "30m", "1h", "2h", "4h", "1d"], default=["1h", "4h", "1d"])
large_tfs = st.sidebar.multiselect(txt_large_tf, ["1wk", "1mo", "3mo", "6mo", "1y", "2y", "5y"], default=[])
selected_tfs = small_tfs + large_tfs

sl_strategy = st.sidebar.radio(txt_sl_strat, ["الكل (Head & Shoulder)", "وقف الرأس فقط (Head SL)", "وقف الكتف فقط (Shoulder SL)"] if lang=="العربية" else ["All", "Head SL Only", "Shoulder SL Only"])
run = st.sidebar.button(txt_run, use_container_width=True)

def get_safe_period_for_tf(tf):
    if tf in ["1m"]: return "7d"
    elif tf in ["5m", "15m", "30m"]: return "60d"
    elif tf in ["1h", "2h", "4h"]: return "730d"
    else: return "5y"

if run:
    if not symbols_to_test:
        st.error("⚠️ لا توجد أصول متاحة للاختبار.")
    else:
        st.info("🚀 جاري بدء الاختبار الرجعي ومعالجة البيانات...")
        
        for symbol in symbols_to_test:
            tf_results = []
            all_trades_detail = []
            
            for tf in selected_tfs:
                fetch_period = get_safe_period_for_tf(tf)
                df = yf.download(symbol, period=fetch_period, interval=tf, progress=False)
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                    
                if df.empty or len(df) < 50:
                    continue
                    
                for sl_type_opt in ["Head SL", "Shoulder SL"]:
                    if sl_strategy != "الكل (Head & Shoulder)" and sl_strategy != "All" and sl_type_opt not in sl_strategy:
                        continue
                    
                    trades = []
                    start_idx = min(100, len(df) // 2)
                    for i in range(start_idx, len(df), max(1, len(df) // 40)):
                        df_slice = df.iloc[:i].copy()
                        
                        df_ind = engine.calculate_indicators(df_slice)
                        df_ind = engine.calculate_zigzag(df_ind)
                        pivots = engine.get_chronological_pivots(df_ind)
                        patterns = engine.detect_all_head_shoulders(pivots, df_ind)
                        
                        if patterns:
                            pat = patterns[-1]
                            end_idx = pat.get("neckline_end_idx")
                            if any(t.get("End_Idx") == end_idx and t.get("SL_Type") == sl_type_opt for t in trades):
                                continue
                                
                            pattern_name = pat.get("pattern") # يحدد نوع النمط عادياً أو مقلوباً
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
                                "Entry": round(entry, 4),
                                "SL": round(sl, 4),
                                "TP": round(tp, 4),
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
            
            # شرط منع ظهور الرموز التي بلا صفقات إلا في البحث الفردي
            if not tf_results:
                if scan_mode == txt_single or scan_mode == "Single Asset":
                    with st.expander(f"📊 نتائج الفحص للرمز: {symbol}", expanded=True):
                        st.warning("⚠️ لا توجد صفقات أو أنماط مسجلة لهذا الأصل بناءً على الشروط الحالية." if lang=="العربية" else "⚠️ No trades recorded for this asset.")
                continue
                
            with st.expander(f"📊 نتائج الفحص والتصفيقات للرمز: {symbol}", expanded=(len(symbols_to_test) == 1)):
                res_df = pd.DataFrame(tf_results).sort_values(by="Win Rate (%)", ascending=False)
                best_row = res_df.iloc[0]
                
                st.subheader("مقارنة الفواصل وأداء الإشارات" if lang=="العربية" else "Timeframe Comparison & Signals Performance")
                st.dataframe(res_df, use_container_width=True)
                
                st.subheader("سجل الأوامر التاريخية التفصيلي" if lang=="العربية" else "Detailed Historical Order Logs")
                details_df = pd.DataFrame(all_trades_detail).drop(columns=["End_Idx"])
                st.dataframe(details_df, use_container_width=True)
                
                # تقرير دقيق ومبني على النتائج الحقيقية (لا يعطي توصيات موجبة خاطئة إذا كانت النسبة ضعيفة)
                wr_val = best_row['Win Rate (%)']
                rec_action = "يوصى بالتداول" if wr_val >= 50 else "لا يُنصح بالتداول حالياً (نسبة النجاح ضعيفة)"
                rec_action_en = "Recommended to trade" if wr_val >= 50 else "Not recommended (Low win rate)"
                
                if lang == "العربية":
                    st.markdown(f"**📋 التقرير الشامل والتوصية الاستراتيجية للرمز: {symbol}**")
                    report_lines = [
                        f"1. **إجمالي عدد الإشارات:** تم رصد ({sum(res_df['Total Signals'])} إشارة) تاريخية عبر الفواصل الزمنية المحددة.",
                        f"2. **أفضل أداء:** حقق الفاصل ({best_row['Timeframe']}) أعلى كفاءة بنسبة نجاح بلغت {wr_val}% باستخدام ({best_row['SL Method']}).",
                        f"3. **تحليل المخاطر:** تم تقييم وتتبع الأوامر مع الأخذ بالاعتبار أسعار الدخول والوقف والأهداف الفعلية بدقة.",
                        f"4. **حالة الأداء:** بناءً على النتائج الفعلية، الأداء العام للصفقات لهذا الأصل يسجل معدل ربحية {wr_val}%.",
                        f"5. **التوصية النهائية:** {rec_action} على فاصل **{best_row['Timeframe']}** باستخدام وقف **{best_row['SL Method']}**."
                    ]
                else:
                    st.markdown(f"**📋 Comprehensive Report & Strategic Recommendation for: {symbol}**")
                    report_lines = [
                        f"1. **Total Signals:** Detected ({sum(res_df['Total Signals'])} historical signals) across selected timeframes.",
                        f"2. **Best Performance:** Timeframe ({best_row['Timeframe']}) achieved highest success rate of {wr_val}% using ({best_row['SL Method']}).",
                        f"3. **Risk Analysis:** Orders and precise execution prices (Entry, SL, TP) were successfully tracked.",
                        f"4. **Performance State:** Based on actual metrics, overall win rate for this asset stands at {wr_val}%.",
                        f"5. **Final Recommendation:** {rec_action_en} on **{best_row['Timeframe']}** with **{best_row['SL Method']}**."
                    ]
                
                for line in report_lines:
                    st.markdown(line)
                    
