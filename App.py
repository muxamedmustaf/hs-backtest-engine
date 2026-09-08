import streamlit as st
import pandas as pd
import engine

def main():
 st.sidebar.title("Settings")
 uploaded_file = st.file_uploader("Upload CSV", type="csv")
 
 if uploaded_file:
 df = pd.read_csv(uploaded_file)
 result = engine.run_analysis(df)
 st.write(result)

if __name__ == "__main__":
 main()
