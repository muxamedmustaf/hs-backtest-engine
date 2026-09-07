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

st.set_page_config(page_title="Advanced Multi-TF Backtester", layout="wide")
engine = importlib.reload(engine)

st.title("⚡ Advanced Multi-Timeframe H&S Backtester")
st.caption("مقارنة شاملة لجميع الفواصل الزمنية (من 1m إلى 5y)، المفاضلة بين وقف الرأس والكتف، وتقرير استراتيجي نهائي.")

SHEET_ID = "1TXvF6RhSgfJ631UpnWB38Ww1OMvZVx7VonDB_y1pO3s"
DEFAULT_SHEET_NAME = "GOLD"
DEFAULT_COL_NAME = "TOKENS"

st.sidebar.header("⚙️ إعدادات التحليل المتقدم")
symbol_input = st.sidebar.text_input("Symbol", "BTC-USD").strip()

all_timeframes = ["1m", "5m", "15m", "30m", "1h", "4h", "1d", "1wk", "1mo", "3mo", "6mo", "1y", "2y", "5y"]
selected_tfs = st.sidebar.multiselect("اختر الفواصل الزمنية للمقارنة", all_timeframes, default=["1h", "4h", "1d"])

sl_strategy = st.sidebar.radio("استراتيجية وقف الخسارة للمقارنة:", ["الكل (مقارنة الرأس والكتف معاً)", "وقف الرأس فقط (Head SL)", "وقف الكتف فقط (Shoulder SL)"])

run = st.sidebar.button("🚀 تشغيل الاختبار والمقارنة الشاملة", use_container_width=True)

def get_safe_period_for_tf(tf):
    if tf in ["1m"]:
        return "7d"
    elif tf in ["5m", "15m", "30m"]:
        return "60d"
    elif tf in ["1h", "2h", "4h"]:
        return "730d"
    else:
        return "2y"

if run:
    with st.spinner("جاري جلب البيانات، فحص الفواصل، ومحاكاة استراتيجيات وقف الخسارة عبر إمكانيات engine.py..."):
        tf_results = []
        
        for tf in selected_tfs:
            period = get_safe_period_for_tf(tf)
            fetch_tf = "1d" if tf in ["1y", "2y", "3y", "5y", "6mo"] else tf
            fetch_period = tf if tf in ["1y", "2y", "3y", "5y", "6mo"] else period
            
            df = yf.download(symbol_input, period=fetch_period, interval=fetch_tf, progress=False)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
                
            if df.empty or len(df) < 50:
                continue
                
            for sl_type in ["Head SL", "Shoulder SL"]:
                if sl_strategy != "الكل (مقارنة الرأس والكتف معاً)" and sl_type not in sl_strategy:
                    continue
                
                trades = []
                start_idx = min(100, len(df) // 2)
                for i in range(start_idx, len(df), max(1, len(df) // 50)):
                    df_slice = df.iloc[:i].copy()
                    
                    # استخدام دوال engine.py للتحليل الفني وحساب المؤشرات[span_0](start_span)[span_0](end_span)
                    df_ind = engine.calculate_indicators(df_slice)
                    df_ind = engine.calculate_zigzag(df_ind)
                    pivots = engine.get_chronological_pivots(df_ind)
                    patterns = engine.detect_all_head_shoulders(pivots, df_ind)
                    
                    if patterns:
                        pat = patterns[-1]
                        end_idx = pat.get("neckline_end_idx")
                        if any(t.get("End_Idx") == end_idx and t.get("SL_Type") == sl_type for t in trades):
                            continue
                            
                        bias = pat.get("bias")
                        entry = pat.get("entry")
                        tp = pat.get("tp")
                        
                        if sl_type == "Head SL":
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
                        for f_idx, row in future_df.iterrows():
                            h, l = row["High"], row["Low"]
                            if bias == "Bearish":
                                if h >= sl: outcome = "LOSS"; break
                                elif l <= tp: outcome = "WIN"; break
                            elif bias == "Bullish":
                                if l <= sl: outcome = "LOSS"; break
                                elif h >= tp: outcome = "WIN"; break
                                
                        trades.append({
                            "TF": tf,
                            "SL_Type": sl_type,
                            "Outcome": outcome,
                            "End_Idx": end_idx
                        })
                
                if trades:
                    tdf = pd.DataFrame(trades)
                    wins = len(tdf[tdf["Outcome"] == "WIN"])
                    losses = len(tdf[tdf["Outcome"] == "LOSS"])
                    total = wins + losses
                    wr = (wins / total) * 100 if total > 0 else 0
                    tf_results.append({
                        "Timeframe": tf,
                        "SL Method": sl_type,
                        "Total Trades": total,
                        "Wins": wins,
                        "Losses": losses,
                        "Win Rate (%)": round(wr, 2)
                    })
        
        if tf_results:
            res_df = pd.DataFrame(tf_results).sort_values(by="Win Rate (%)", ascending=False)
            best_row = res_df.iloc[0]
            
            st.subheader("📊 جدول مقارنة الفواصل الزمنية وأساليب وقف الخسارة")
            st.dataframe(res_df, use_container_width=True)
            
            st.markdown("---")
            st.markdown("**📋 التقرير الشامل والتوصية الاستراتيجية**")
            
            report_lines = [
                f"1. **أفضل فاصل زمني محقق للنجاح:** الفاصل ({best_row['Timeframe']}) أظهر أعلى كفاءة بمعامل نجاح بلغ {best_row['Win Rate (%)']}% باستخدام منهجية ({best_row['SL Method']}).",
                f"2. **مقارنة أساليب وقف الخسارة:** أثبتت المقارنة تفوق طريقة ({best_row['SL Method']}) في التحكم بالمخاطر مقارنة بالبدائل الأخرى.",
                f"3. **كفاءة الأنماط التاريخية:** إجمالي الصفقات الخاضعة للاختبار على الرمز ({symbol_input}) تعكس دقة استراتيجية المحرك الفني.",
                f"4. **التقييم العام للسوق:** تباين النتائج بين الفواصل المختلفة يبرز أهمية اختيار النطاق الزمني المناسب لتفادي الضوضاء.",
                f"5. **التوصية الاستراتيجية:** يُنصح باعتماد التداول على الفاصل الزمني **{best_row['Timeframe']}** مع تفعيل وقف خسارة بنظام **{best_row['SL Method']}** لتعظيم العائد المتوقع."
            ]
            
            for line in report_lines:
                st.markdown(line)
        else:
            st.warning("لم يتم تسجيل صفقات كافية للمقارنة عبر الفواصل الزمنية المحددة.")
            
