# -*- coding: utf-8 -*-
"""
REVERSAL AFTER CONSOLIDATION
Strategy: Downtrend → Consolidation → Upward Breakout
ZigZag Only — No indicators
"""
import pandas as pd
import numpy as np

CONFIG_RAC = {
    # ZigZag
    "ZIGZAG_DEPTH": 8,
    "ZIGZAG_BACKSTEP": 4,

    # Downtrend check
    "MIN_PIVOTS_FOR_TREND": 4,
    "MIN_LOWER_HIGHS": 2,
    "MIN_LOWER_LOWS": 2,

    # Consolidation
    "MIN_PIVOTS_CONSOL": 3,
    "MAX_CONSOL_RANGE_PCT": 0.30,  # 0.30%
    "CONSOL_LOOKBACK_BARS": 30,

    # Breakout
    "MIN_BREAKOUT_BODY_PCT": 0.15,  # Min body %
    "MIN_BREAKOUT_RANGE_PCT": 0.25,  # Min range %
    "BREAKOUT_BUFFER_PCT": 0.02,     # 0.02% buffer above high

    # SL/TP
    "SL_BUFFER_PCT": 0.05,      # 0.05% below consol low
    "TP_RR_MIN": 1.5,
    "TP_RR_MAX": 4.0,

    # Filters
    "MIN_BARS_BETWEEN": 5,
    "MAX_TIMEOUT_BARS": 200,
    "MIN_PRICE": 0.0001,
}


# ══════════════════════════════════════════════════════════════════════════════
# 🛠️ ZIGZAG — U isticmaal engine.py
# ══════════════════════════════════════════════════════════════════════════════
def get_zigzag_pivots(df):
    """Soo qaado ZigZag pivots — engine.py."""
    try:
        from engine import (calculate_indicators, calculate_zigzag,
                            get_chronological_pivots, CONFIG)
        df = df.copy()
        df = calculate_indicators(df)
        df = calculate_zigzag(df, CONFIG["ZIGZAG_DEPTH"], CONFIG["ZIGZAG_BACKSTEP"])
        pivots = get_chronological_pivots(df)
        return df, pivots
    except Exception as e:
        return df, []


def detect_downtrend(pivots, end_idx):
    """
    Hubi in 2-3 pivots ugu dambeeyay yihiin downtrend.

    Downtrend = Lower Highs + Lower Lows.
    """
    if len(pivots) < CONFIG_RAC["MIN_PIVOTS_FOR_TREND"]:
        return False, None

    # Soo qaado pivots ugu dambeeyay ee ka horreeya end_idx
    relevant = [p for p in pivots if p["pos"] <= end_idx]
    if len(relevant) < 4:
        return False, None

    last_pivots = relevant[-4:]

    # Kala saar highs iyo lows
    highs = [p for p in last_pivots if p["type"] == "H"]
    lows  = [p for p in last_pivots if p["type"] == "L"]

    if len(highs) < 2 or len(lows) < 2:
        return False, None

    # Hubi Lower Highs
    lower_highs = sum(
        1 for i in range(1, len(highs))
        if highs[i]["val"] < highs[i-1]["val"]
    )

    # Hubi Lower Lows
    lower_lows = sum(
        1 for i in range(1, len(lows))
        if lows[i]["val"] < lows[i-1]["val"]
    )

    is_downtrend = (
        lower_highs >= CONFIG_RAC["MIN_LOWER_HIGHS"] and
        lower_lows >= CONFIG_RAC["MIN_LOWER_LOWS"]
    )

    return is_downtrend, {
        "lower_highs": lower_highs,
        "lower_lows": lower_lows,
        "last_high": highs[-1]["val"],
        "last_low": lows[-1]["val"],
        "last_high_pos": highs[-1]["pos"],
        "last_low_pos": lows[-1]["pos"],
    }


# ══════════════════════════════════════════════════════════════════════════════
# 🛠️ CONSOLIDATION DETECTION
# ══════════════════════════════════════════════════════════════════════════════
def detect_consolidation(df, start_idx, end_idx):
    """
    Hubi in bars-ka u dhexeeya start_idx iyo end_idx ay yihiin consolidation.

    Shuruudaha:
    1. Range (High - Low) < MAX_CONSOL_RANGE_PCT
    2. Bars badan (>= 5)
    3. Ma jiro impulse weyn
    """
    if end_idx - start_idx < 5:
        return False, None

    segment = df.iloc[start_idx:end_idx + 1]
    if len(segment) < 5:
        return False, None

    consol_high = float(segment["High"].max())
    consol_low  = float(segment["Low"].min())

    if consol_low <= 0:
        return False, None

    range_pct = (consol_high - consol_low) / consol_low * 100

    if range_pct > CONFIG_RAC["MAX_CONSOL_RANGE_PCT"]:
        return False, None

    # Hubi bars-ka
    num_bars = len(segment)
    if num_bars < 5:
        return False, None

    return True, {
        "high": consol_high,
        "low": consol_low,
        "range_pct": round(range_pct, 3),
        "bars": num_bars,
        "start_idx": start_idx,
        "end_idx": end_idx,
        "mid": (consol_high + consol_low) / 2,
    }


def find_consolidation_after_downtrend(df, pivots, downtrend_info):
    """
    Soo hel consolidation ka dib downtrend.

    Fikradda:
    - Downtrend wuxuu dhammaaday marka pivot low ugu dambeeyay
    - Consolidation wuxuu bilaabmaa ka dib
    - Range yar ilaa breakout
    """
    if not downtrend_info:
        return None

    last_low_pos = downtrend_info["last_low_pos"]

    # Bilow ka dib last_low_pos
    start_search = last_low_pos + 1

    if start_search >= len(df) - 5:
        return None

    # Raadi consolidation inta u dhexeeya last_low_pos iyo dhamaadka
    best_consol = None

    for end_idx in range(start_search + 5, min(start_search + 60, len(df))):
        is_consol, consol_info = detect_consolidation(df, start_search, end_idx)
        if is_consol:
            if best_consol is None or consol_info["bars"] > best_consol["bars"]:
                best_consol = consol_info

    return best_consol


# ══════════════════════════════════════════════════════════════════════════════
# 🛠️ BREAKOUT DETECTION
# ══════════════════════════════════════════════════════════════════════════════
def detect_bullish_breakout(df, consol_info, check_idx):
    """
    Hubi in breakout bullish uu dhaco ka dib consolidation.

    Shuruudaha:
    1. Candle close > consol_high + buffer
    2. Candle body weyn (>= MIN_BREAKOUT_BODY_PCT)
    3. Range weyn (>= MIN_BREAKOUT_RANGE_PCT)
    """
    if consol_info is None:
        return False, None

    if check_idx < 1 or check_idx >= len(df):
        return False, None

    candle = df.iloc[check_idx]
    prev = df.iloc[check_idx - 1]

    consol_high = consol_info["high"]
    consol_low  = consol_info["low"]

    # Shuruud 1: Close > high + buffer
    buffer = consol_high * (CONFIG_RAC["BREAKOUT_BUFFER_PCT"] / 100)
    if candle["Close"] <= consol_high + buffer:
        return False, None

    # Shuruud 2: Body weyn
    body = abs(candle["Close"] - candle["Open"])
    body_pct = (body / consol_low * 100) if consol_low > 0 else 0

    if body_pct < CONFIG_RAC["MIN_BREAKOUT_BODY_PCT"]:
        return False, None

    # Shuruud 3: Range weyn
    candle_range = candle["High"] - candle["Low"]
    range_pct = (candle_range / consol_low * 100) if consol_low > 0 else 0

    if range_pct < CONFIG_RAC["MIN_BREAKOUT_RANGE_PCT"]:
        return False, None

    # Shuruud 4: Candle bullish
    if candle["Close"] <= candle["Open"]:
        return False, None

    return True, {
        "breakout_idx": check_idx,
        "breakout_price": float(candle["Close"]),
        "consol_high": consol_high,
        "consol_low": consol_low,
        "body_pct": round(body_pct, 3),
        "range_pct": round(range_pct, 3),
        "buffer_pct": round(CONFIG_RAC["BREAKOUT_BUFFER_PCT"], 3),
    }


# ══════════════════════════════════════════════════════════════════════════════
# 🎯 CALCULATE SL/TP
# ══════════════════════════════════════════════════════════════════════════════
def calculate_sl_tp(entry, consol_info, downtrend_info):
    """
    Xisaabi SL iyo TP.

    SL = consol_low - buffer (0.05%)
    TP = entry + measured_move (impulse from prev high)
    """
    consol_low  = consol_info["low"]
    consol_high = consol_info["high"]

    # SL = consol_low - 0.05%
    sl_buffer = consol_low * (CONFIG_RAC["SL_BUFFER_PCT"] / 100)
    sl = consol_low - sl_buffer

    # Measured move: impulse = consol_high - consol_low
    impulse_size = consol_high - consol_low

    # TP = entry + impulse_size
    tp = entry + impulse_size

    # Risk iyo Reward
    risk = entry - sl
    reward = tp - entry

    if risk <= 0:
        return None

    rr = reward / risk

    # Hubi R:R
    if rr < CONFIG_RAC["TP_RR_MIN"]:
        # Kordhi TP si R:R uu gaaro minimum
        tp = entry + CONFIG_RAC["TP_RR_MIN"] * risk
        reward = tp - entry
        rr = CONFIG_RAC["TP_RR_MIN"]

    if rr > CONFIG_RAC["TP_RR_MAX"]:
        # Yaree TP
        tp = entry + CONFIG_RAC["TP_RR_MAX"] * risk
        reward = tp - entry
        rr = CONFIG_RAC["TP_RR_MAX"]

    return {
        "sl": round(sl, 5),
        "tp": round(tp, 5),
        "risk": round(risk, 5),
        "reward": round(reward, 5),
        "rr": round(rr, 2),
        "impulse_size": round(impulse_size, 5),
        "sl_buffer": round(sl_buffer, 5),
    }


# ══════════════════════════════════════════════════════════════════════════════
# 🎯 MAIN STRATEGY — Soo hel dhammaan signals
# ══════════════════════════════════════════════════════════════════════════════
def detect_reversal_signals(df, symbol=None, interval="1h"):
    """
    Soo hel signals-ka "Downtrend → Consolidation → Bullish Breakout".
    """
    if df is None or df.empty or len(df) < 50:
        return []

    df = df.copy()
    for col in ["Open", "High", "Low", "Close"]:
        if col not in df.columns:
            return []
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["Open", "High", "Low", "Close"])

    if len(df) < 50:
        return []

    # Soo qaado ZigZag
    df_zz, pivots = get_zigzag_pivots(df)
    if not pivots:
        return []

    signals = []
    last_signal_idx = -999

    # Baar bars kasta oo ka bilaabma 50
    for idx in range(50, len(df)):
        # Hubi bars u dhexeeya signal-ka hore
        if (idx - last_signal_idx) < CONFIG_RAC["MIN_BARS_BETWEEN"]:
            continue

        # 1. Downtrend check
        is_downtrend, downtrend_info = detect_downtrend(pivots, idx)
        if not is_downtrend:
            continue

        # 2. Consolidation check (ka dib downtrend)
        consol_info = find_consolidation_after_downtrend(df, pivots, downtrend_info)
        if not consol_info:
            continue

        # 3. Breakout check
        is_breakout, breakout_info = detect_bullish_breakout(df, consol_info, idx)
        if not is_breakout:
            continue

        # 4. Xisaabi SL/TP
        entry = breakout_info["breakout_price"]
        sl_tp = calculate_sl_tp(entry, consol_info, downtrend_info)
        if not sl_tp:
            continue

        # 5. Diiwaangeli signal
        signals.append({
            "symbol": symbol or "N/A",
            "strategy": "ReversalAfterConsol",
            "pattern": f"Down→Consol→Breakout",
            "bias": "Bullish",
            "direction": "BUY",
            "entry": round(entry, 5),
            "sl": sl_tp["sl"],
            "tp": sl_tp["tp"],
            "rr": sl_tp["rr"],
            "entry_idx": df.index[idx],
            "entry_pos": idx,
            "consol_high": round(consol_info["high"], 5),
            "consol_low": round(consol_info["low"], 5),
            "consol_bars": consol_info["bars"],
            "consol_range_pct": consol_info["range_pct"],
            "downtrend_lower_highs": downtrend_info["lower_highs"],
            "downtrend_lower_lows": downtrend_info["lower_lows"],
            "breakout_body_pct": breakout_info["body_pct"],
            "breakout_range_pct": breakout_info["range_pct"],
            "impulse_size": sl_tp["impulse_size"],
            "risk": sl_tp["risk"],
            "reward": sl_tp["reward"],
        })

        last_signal_idx = idx

    return signals


# ══════════════════════════════════════════════════════════════════════════════
# 🧪 SIMULATE TRADE
# ══════════════════════════════════════════════════════════════════════════════
def simulate_trade(signal, df):
    """Simulate trade — WIN/LOSS/TIMEOUT."""
    entry_pos = signal["entry_pos"]
    if entry_pos >= len(df) - 1:
        return None

    entry = signal["entry"]
    sl = signal["sl"]
    tp = signal["tp"]
    direction = signal["direction"]

    max_bars = CONFIG_RAC["MAX_TIMEOUT_BARS"]
    end_pos = min(entry_pos + max_bars, len(df) - 1)

    post_df = df.iloc[entry_pos + 1:end_pos + 1]

    max_reach_pct = 0.0
    max_adverse_pct = 0.0

    total_tp = abs(tp - entry)
    total_sl = abs(sl - entry)

    for i, (idx, row) in enumerate(post_df.iterrows(), start=1):
        high = float(row["High"])
        low = float(row["Low"])

        if direction == "BUY":
            favorable = max(0.0, high - entry)
            adverse = max(0.0, entry - low)
        else:
            favorable = max(0.0, entry - low)
            adverse = max(0.0, high - entry)

        if total_tp > 0:
            max_reach_pct = max(max_reach_pct, favorable / total_tp * 100)
        if total_sl > 0:
            max_adverse_pct = max(max_adverse_pct, adverse / total_sl * 100)

        # Hubi SL/TP
        if direction == "BUY":
            if low <= sl:
                return {
                    "Result": "LOSS",
                    "exit_price": sl,
                    "candles_to_exit": i,
                    "Exit Date": str(idx),
                    "Max Reach %": round(max_reach_pct, 1),
                    "SL Safety %": round(100 - max_adverse_pct, 1),
                }
            if high >= tp:
                return {
                    "Result": "WIN",
                    "exit_price": tp,
                    "candles_to_exit": i,
                    "Exit Date": str(idx),
                    "Max Reach %": 100.0,
                    "SL Safety %": round(100 - max_adverse_pct, 1),
                }
        else:  # SELL
            if high >= sl:
                return {
                    "Result": "LOSS",
                    "exit_price": sl,
                    "candles_to_exit": i,
                    "Exit Date": str(idx),
                    "Max Reach %": round(max_reach_pct, 1),
                    "SL Safety %": round(100 - max_adverse_pct, 1),
                }
            if low <= tp:
                return {
                    "Result": "WIN",
                    "exit_price": tp,
                    "candles_to_exit": i,
                    "Exit Date": str(idx),
                    "Max Reach %": 100.0,
                    "SL Safety %": round(100 - max_adverse_pct, 1),
                }

    # Timeout
    if len(post_df) > 0:
        last = post_df.iloc[-1]
        return {
            "Result": "TIMEOUT",
            "exit_price": float(last["Close"]),
            "candles_to_exit": len(post_df),
            "Exit Date": str(post_df.index[-1]),
            "Max Reach %": round(max_reach_pct, 1),
            "SL Safety %": round(100 - max_adverse_pct, 1),
        }

    return {
        "Result": "OPEN",
        "exit_price": entry,
        "candles_to_exit": 0,
        "Exit Date": None,
        "Max Reach %": 0,
        "SL Safety %": 100,
    }


# ══════════════════════════════════════════════════════════════════════════════
# 🎯 BACKTEST FUNCTION
# ══════════════════════════════════════════════════════════════════════════════
def backtest_reversal_strategy(df, symbol=None, interval="1h"):
    """
    Backtest istiraatijiyada oo dhan.
    """
    signals = detect_reversal_signals(df, symbol=symbol, interval=interval)

    trades = []
    for sig in signals:
        sim = simulate_trade(sig, df)
        if sim:
            trade = {**sig, **sim}
            trade["Entry Date"] = str(sig["entry_idx"])
            trades.append(trade)

    return trades


# ══════════════════════════════════════════════════════════════════════════════
# 📊 BATCH SCAN — 48 symbols
# ══════════════════════════════════════════════════════════════════════════════
def scan_multiple_symbols(symbols, interval="1h", period="3mo",
                          start_date=None, end_date=None,
                          fetch_func=None):
    """
    Baar dhammaan symbols-ka.

    Args:
        symbols: List of symbols
        fetch_func: Function soo qaadaya xogta (fetch_data)
    """
    all_trades = []

    if fetch_func is None:
        return all_trades

    for sym in symbols:
        try:
            if start_date and end_date:
                df = fetch_func(sym, interval=interval,
                                start_date=start_date, end_date=end_date,
                                cache_hours=1)
            else:
                df = fetch_func(sym, interval=interval, period=period,
                                cache_hours=1)

            if df is None or df.empty or len(df) < 50:
                continue

            trades = backtest_reversal_strategy(df, symbol=sym, interval=interval)
            all_trades.extend(trades)

        except Exception as e:
            continue

    return all_trades
