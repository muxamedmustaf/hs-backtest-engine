import streamlit as st
import yfinance as yf
import pandas as pd
from ffff import get_symbols_from_sheet
from engine import run_strategy

st.set_page_config(page_title="نظام الاختبار الرجعي", layout="wide")
st.title("📊 لوحة الاختبار الرجعي الآلي")

col1, col2, col3 = st.columns(3)
with col1:
 start_date = st.date_input("تاريخ البدء", value=pd.to_datetime("2023-01-01"))
with col2:
 end_date = st.date_input("تاريخ الانتهاء", value=pd.to_datetime("today"))
with col3:
 interval = st.selectbox("الفاصل الزمني", ["1d", "1h", "4h", "15m"])

if st.button("بدء تحليل الاستراتيجية"):
 with st.spinner("جاري الاتصال بالشيت وجلب البيانات..."):
 try:
 symbols = get_symbols_from_sheet()
 st.write(f"تم العثور على {len(symbols)} رمزاً.")

 results_list = []

 for symbol in symbols:
 df = yf.download(symbol, start=start_date, end=end_date, interval=interval, progress=False)
 
 if not df.empty:
 analysis = run_strategy(df)
 
 if analysis.get('pattern_found'):
 results_list.append({
 "Symbol": symbol,
 "Pattern": analysis.get('pattern_name'),
 "Action": analysis.get('action'),
 "Entry": analysis.get('entry_price')
 })

 if results_list:
 st.success("تم العثور على أنماط!")
 st.table(pd.DataFrame(results_list))
 else:
 st.warning("لم يتم العثور على أنماط مطابقة في الرموز المختارة.")

 except Exception as e:
 st.error(f"حدث خطأ أثناء التنفيذ: {e}")
