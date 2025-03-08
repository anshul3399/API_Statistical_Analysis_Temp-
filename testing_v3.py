import time
import pandas as pd
import numpy as np
import tkinter as tk
from tkinter import messagebox
import logging
import json
import os
from datetime import datetime

# Conditionally import KiteConnect
try:
    from kiteconnect import KiteConnect
    KITE_AVAILABLE = True
except ImportError:
    KITE_AVAILABLE = False
    
# ---------------- Config Handling ----------------
def load_config():
    config_path = os.path.join(os.path.dirname(__file__), 'config.json')
    if os.path.exists(config_path):
        with open(config_path, 'r') as file:
            return json.load(file)
    else:
        # Create default config if not exists
        default_config = {
            "kite": {
                "api_key": "YOUR_KITE_API_KEY",
                "api_secret": "YOUR_KITE_API_SECRET",
                "access_token": "YOUR_ACCESS_TOKEN"
            },
            "instruments": {
                "NIFTY": "NIFTY50",
                "BANKNIFTY": "BANKNIFTY"
            },
            "analysis": {
                "rsi_period": 14,
                "interval": "5minute",
                "duration_days": 1
            },
            "simulation_mode": True
        }
        with open(config_path, 'w') as file:
            json.dump(default_config, file, indent=4)
        return default_config

# ---------------- Logging Setup ----------------
def setup_logging():
    log_dir = os.path.join(os.path.dirname(__file__), 'logs')
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    log_file = os.path.join(log_dir, f'trading_bot_{datetime.now().strftime("%Y%m%d")}.log')
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger('TradingBot')

# Global variables
CONFIG = load_config()
logger = setup_logging()

# Initialize KiteConnect if available
kite = None
if KITE_AVAILABLE and not CONFIG['simulation_mode']:
    try:
        kite = KiteConnect(api_key=CONFIG['kite']['api_key'])
        kite.set_access_token(CONFIG['kite']['access_token'])
        logger.info("KiteConnect initialized successfully")
    except Exception as e:
        logger.error(f"Error initializing KiteConnect: {e}")

# ---------------- Technical Analysis Functions ----------------

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).fillna(0)
    loss = (-delta.where(delta < 0, 0)).fillna(0)
    avg_gain = gain.rolling(window=period, min_periods=period).mean()
    avg_loss = loss.rolling(window=period, min_periods=period).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def fibonacci_levels(prices):
    max_price = max(prices)
    min_price = min(prices)
    diff = max_price - min_price
    levels = {
        "0.0%": max_price,
        "23.6%": max_price - 0.236 * diff,
        "38.2%": max_price - 0.382 * diff,
        "50.0%": max_price - 0.5 * diff,
        "61.8%": max_price - 0.618 * diff,
        "100.0%": min_price
    }
    return levels

# ---------------- Data Fetching Function ----------------

def fetch_historical_data(instrument_token, interval='5minute', duration=1):
    """
    Fetch historical data from Zerodha or use simulation data.
    """
    if not CONFIG['simulation_mode'] and kite is not None:
        # Set up date range
        from_date = (datetime.now() - pd.Timedelta(days=duration)).strftime('%Y-%m-%d')
        to_date = datetime.now().strftime('%Y-%m-%d')
        try:
            data = kite.historical_data(instrument_token, from_date, to_date, interval)
            return pd.DataFrame(data)
        except Exception as e:
            logger.error(f"Error fetching historical data: {e}")
            # Fall back to simulation if API fails
            logger.info("Falling back to simulation data")
    
    # Generate simulation data
    logger.info(f"Using simulated data for {instrument_token}")
    timestamps = pd.date_range(end=pd.Timestamp.now(), periods=100, freq='5T')
    
    # Make NIFTY and BANKNIFTY have different price ranges
    if 'NIFTY' in instrument_token and 'BANK' not in instrument_token:
        price_range = (15000, 16000)
    else:  # BANKNIFTY or others
        price_range = (35000, 36000)
        
    data = pd.DataFrame({
        'open': np.random.uniform(price_range[0], price_range[1], size=100),
        'high': np.random.uniform(price_range[0], price_range[1], size=100),
        'low': np.random.uniform(price_range[0], price_range[1], size=100),
        'close': np.random.uniform(price_range[0], price_range[1], size=100),
    }, index=timestamps)
    return data

# ---------------- Signal Generation ----------------

def analyze_and_generate_signal(instrument_token):
    data = fetch_historical_data(
        instrument_token, 
        interval=CONFIG['analysis']['interval'],
        duration=CONFIG['analysis']['duration_days']
    )
    
    data['RSI'] = calculate_rsi(data['close'], period=CONFIG['analysis']['rsi_period'])
    fib_levels = fibonacci_levels(data['close'])

    latest_rsi = data['RSI'].iloc[-1]
    latest_price = data['close'].iloc[-1]

    # Simple signal logic:
    # Buy if RSI < 30 and price near Fibonacci support
    # Sell if RSI > 70 and price near Fibonacci resistance
    buy_signal = False
    sell_signal = False
    '''
    if latest_rsi < 30 and abs(latest_price - fib_levels["100.0%"]) / fib_levels["100.0%"] < 0.01:
        buy_signal = True
    elif latest_rsi > 70 and abs(latest_price - fib_levels["0.0%"]) / fib_levels["0.0%"] < 0.01:
        sell_signal = True
'''
    logger.info(f"buy calc value = {abs(latest_price - fib_levels['100.0%']) / fib_levels['100.0%']}")
    logger.info(f"sell calc value = {abs(latest_price - fib_levels['0.0%']) / fib_levels['0.0%']}")

    if latest_rsi < 50 and abs(latest_price - fib_levels["100.0%"]) / fib_levels["100.0%"] < 0.01:
        buy_signal = True
    elif latest_rsi > 55 and abs(latest_price - fib_levels["0.0%"]) / fib_levels["0.0%"] < 0.01:
        sell_signal = True


    signal = None
    if buy_signal:
        signal = "BUY"
    elif sell_signal:
        signal = "SELL"
        
    return signal, latest_price, latest_rsi, fib_levels

# ---------------- Order Execution ----------------

def execute_order(tradingsymbol, transaction_type, quantity=1):
    """
    Execute a market order via Zerodha Kite.
    transaction_type: "BUY" or "SELL"
    """
    if CONFIG['simulation_mode'] or kite is None:
        logger.info(f"SIMULATION: Order executed - {transaction_type} {quantity} {tradingsymbol}")
        return f"sim_order_{int(time.time())}"
    
    try:
        if transaction_type == "BUY":
            kite_transaction_type = kite.TRANSACTION_TYPE_BUY
        else:
            kite_transaction_type = kite.TRANSACTION_TYPE_SELL
            
        order_id = kite.place_order(
            variety=kite.VARIETY_REGULAR,
            exchange="NSE",
            tradingsymbol=tradingsymbol,
            transaction_type=kite_transaction_type,
            quantity=quantity,
            product=kite.PRODUCT_MIS,
            order_type=kite.ORDER_TYPE_MARKET
        )
        logger.info(f"Order executed: {transaction_type} {quantity} {tradingsymbol}, Order ID: {order_id}")
        return order_id
    except Exception as e:
        logger.error(f"Order execution failed: {e}")
        return None

# ---------------- Desktop GUI using Tkinter ----------------

class TradingBotGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Trading Bot Dashboard")
        self.geometry("800x600")
        
        # Status frame
        status_frame = tk.Frame(self)
        status_frame.pack(fill=tk.X, pady=10)
        
        self.status_label = tk.Label(status_frame, text="Status: Idle", font=("Arial", 12))
        self.status_label.pack(side=tk.LEFT, padx=20)
        
        self.mode_label = tk.Label(
            status_frame, 
            text=f"Mode: {'Simulation' if CONFIG['simulation_mode'] else 'Live Trading'}", 
            font=("Arial", 12),
            fg="blue" if CONFIG['simulation_mode'] else "red"
        )
        self.mode_label.pack(side=tk.RIGHT, padx=20)
        
        # Signal frame
        signal_frame = tk.Frame(self)
        signal_frame.pack(fill=tk.X, pady=10)
        
        self.signal_label = tk.Label(signal_frame, text="Latest Signals:", font=("Arial", 12))
        self.signal_label.pack(pady=10)
        
        # Buttons frame
        button_frame = tk.Frame(self)
        button_frame.pack(fill=tk.X, pady=10)
        
        self.run_button = tk.Button(button_frame, text="Run Analysis", 
                                   command=self.run_analysis, font=("Arial", 12))
        self.run_button.pack(side=tk.LEFT, padx=20, pady=10)
        
        self.clear_log_button = tk.Button(button_frame, text="Clear Log", 
                                         command=self.clear_log, font=("Arial", 12))
        self.clear_log_button.pack(side=tk.RIGHT, padx=20, pady=10)

        # Log box
        log_frame = tk.Frame(self)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        self.log_box = tk.Text(log_frame, height=15, width=80)
        self.log_box.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        scrollbar = tk.Scrollbar(log_frame, command=self.log_box.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_box.config(yscrollcommand=scrollbar.set)
        
        self.log("Trading Bot Initialized.")
        self.log(f"Mode: {'Simulation' if CONFIG['simulation_mode'] else 'Live Trading'}")
        self.log(f"Kite API Available: {KITE_AVAILABLE}")

    def log(self, message):
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        self.log_box.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_box.see(tk.END)
        # Also log to file
        logger.info(message)

    def show_alert(self, title, message):
        messagebox.showinfo(title, message)
        self.log(f"ALERT: {title} - {message}")

    def clear_log(self):
        self.log_box.delete(1.0, tk.END)
        self.log("Log cleared.")

    def run_analysis(self):
        self.status_label.config(text="Status: Running analysis...")
        self.log("Starting analysis for NIFTY and BANKNIFTY.")

        # Analyze for NIFTY
        nifty_token = CONFIG['instruments']['NIFTY']
        signal_nifty, price_nifty, rsi_nifty, fib_nifty = analyze_and_generate_signal(nifty_token)
        
        # Analyze for BANKNIFTY
        banknifty_token = CONFIG['instruments']['BANKNIFTY']
        signal_banknifty, price_banknifty, rsi_banknifty, fib_banknifty = analyze_and_generate_signal(banknifty_token)

        # Display results
        result = (f"NIFTY - Signal: {signal_nifty}, Price: {price_nifty:.2f}, RSI: {rsi_nifty:.2f}\n"
                  f"BANKNIFTY - Signal: {signal_banknifty}, Price: {price_banknifty:.2f}, RSI: {rsi_banknifty:.2f}")
        self.log(f"NIFTY - Signal: {signal_nifty}, Price: {price_nifty:.2f}, RSI: {rsi_nifty:.2f}, Fib: {fib_nifty}\n"
                  f"BANKNIFTY - Signal: {signal_banknifty}, Price: {price_banknifty:.2f}, RSI: {rsi_banknifty:.2f}, Fib: {fib_banknifty}")
        self.signal_label.config(text="Latest Signals:\n" + result)
        self.log("Analysis complete.")

        # Show UI alerts if signals are generated
        if signal_nifty:
            msg = f"NIFTY signal: {signal_nifty} at Price {price_nifty:.2f}, RSI {rsi_nifty:.2f}"
            self.show_alert("NIFTY Signal", msg)
            
        if signal_banknifty:
            msg = f"BANKNIFTY signal: {signal_banknifty} at Price {price_banknifty:.2f}, RSI {rsi_banknifty:.2f}"
            self.show_alert("BANKNIFTY Signal", msg)

        # Example order execution (uncomment and customize when ready to trade)
        # if signal_nifty == "BUY":
        #     order_id = execute_order(tradingsymbol=nifty_token, transaction_type="BUY")
        #     self.log(f"Executed BUY order for NIFTY. Order ID: {order_id}")
        # elif signal_nifty == "SELL":
        #     order_id = execute_order(tradingsymbol=nifty_token, transaction_type="SELL")
        #     self.log(f"Executed SELL order for NIFTY. Order ID: {order_id}")

        self.status_label.config(text="Status: Idle")

if __name__ == "__main__":
    app = TradingBotGUI()
    app.mainloop()
