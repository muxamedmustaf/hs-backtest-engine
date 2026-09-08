import streamlit as st
import pandas as pd
import numpy as np
import importlib
import engine

try:
 # إضافة المنطق الخاص بك هنا
 st.title("Backtest Application")
except Exception as e:
 st.error(f"Error: {e}")
