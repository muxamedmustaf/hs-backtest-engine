import os
import pandas as pd
import gspread
import streamlit as st
from google.oauth2.service_account import Credentials

SHEET_GOLD_ID = "1TXvF6RhSgfJ631UpnWB38Ww1OMvZVx7VonDB_y1pO3s"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

def get_symbols_from_sheet(spreadsheet_id=SHEET_GOLD_ID, sheet_name="Sheet1", column_name="Ticker", json_path=None):
    try:
        # Ø§Ù„Ù‚Ø±Ø§Ø¡Ø© Ø¹Ø¨Ø± Streamlit Secrets Ø£Ù…Ù†ÙŠØ§Ù‹ ÙˆØ¨Ø¯ÙˆÙ† Ù…Ù„ÙØ§Øª Ø®Ø§Ø±Ø¬ÙŠØ©
        if "gcp_service_account" in st.secrets:
            creds = Credentials.from_service_account_info(
                st.secrets["gcp_service_account"], 
                scopes=SCOPES
            )
            gc = gspread.authorize(creds)
            sh = gc.open_by_key(spreadsheet_id)
            worksheet = sh.worksheet(sheet_name)
            data = worksheet.get_all_records()
            df = pd.DataFrame(data)
        elif json_path and os.path.exists(json_path):
            creds = Credentials.from_service_account_file(json_path, scopes=SCOPES)
            gc = gspread.authorize(creds)
            sh = gc.open_by_key(spreadsheet_id)
            worksheet = sh.worksheet(sheet_name)
            data = worksheet.get_all_records()
            df = pd.DataFrame(data)
        else:
            url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/gviz/tq?tqx=out:csv&sheet={sheet_name}"
            df = pd.read_csv(url)

        if df.empty:
            return [], "Ø¬Ø¯ÙˆÙ„ Ø§Ù„Ø¨ÙŠØ§Ù†Ø§Øª ÙØ§Ø±Øº."

        matched_col = None
        for col in df.columns:
            if str(col).strip().lower() == column_name.strip().lower():
                matched_col = col
                break
        
        if matched_col is None:
            matched_col = df.columns[0]

        symbols = df[matched_col].dropna().astype(str).str.strip().tolist()
        symbols = [s for s in symbols if s and s.lower() != 'nan']

        return symbols, None

    except Exception as e:
        return [], f"Ø®Ø·Ø£ Ø£Ø«Ù†Ø§Ø¡ Ø¬Ù„Ø¨ Ø§Ù„Ø¨ÙŠØ§Ù†Ø§Øª: {str(e)}"
        
