import pandas as pd
import datetime
import yfinance as yf
from config import HISTORY_DAYS_DEFAULT

# Attempt to import new vnstock API functions
try:
    from vnstock.api.quote import Quote
    from vnstock.api.listing import Listing
    has_vnstock_api = True
except ImportError:
    has_vnstock_api = False

def get_hose_tickers():
    """
    Get a list of all tickers listed on HOSE.
    """
    tickers = []
    
    # Method 1: vnstock.api.listing.Listing
    if has_vnstock_api:
        try:
            l = Listing()
            df = l.symbols_by_exchange('HOSE')
            if df is not None and not df.empty:
                col = 'symbol' if 'symbol' in df.columns else df.columns[0]
                raw_tickers = df[col].tolist()
                tickers = [t for t in raw_tickers if len(str(t).strip()) == 3]
                print(f"Successfully fetched {len(tickers)} HOSE tickers from vnstock.api")
        except Exception as e:
            print(f"Error fetching HOSE tickers via vnstock.api: {e}")

    # Method 2: Fallback list of major HOSE stocks (VN30 + others) if APIs fail
    if not tickers:
        print("Using fallback list of HOSE tickers")
        tickers = [
            "ACB", "BCM", "BID", "BVH", "CTG", "FPT", "GAS", "GVR", "HDB", "HPG", 
            "MBB", "MSN", "MWG", "PLX", "POW", "SAB", "SHB", "SSB", "SSI", "STB", 
            "TCB", "TPB", "VCB", "VJC", "VHM", "VIC", "VNM", "VPB", "VRE", "VND",
            "KBC", "DIG", "DXG", "NLG", "PDR", "HSG", "NKG", "VCI", "HCM"
        ]
    
    # Standardize: make unique and uppercase
    tickers = sorted(list(set([str(t).upper().strip() for t in tickers if t])))
    return tickers

def get_historical_data(symbol, start_date=None, end_date=None, force_yfinance=False):
    """
    Get daily historical OHLCV data for a ticker or index.
    Sources tried: vnstock.api.quote (VCI or KBS), yfinance (fallback).
    """
    symbol = symbol.upper().strip()
    
    # Calculate dates if not provided
    if not end_date:
        # Add 1 day because yfinance 'end' parameter is exclusive
        end_dt = datetime.datetime.now() + datetime.timedelta(days=1)
        end_date = end_dt.strftime("%Y-%m-%d")
    if not start_date:
        start_dt = datetime.datetime.now() - datetime.timedelta(days=HISTORY_DAYS_DEFAULT)
        start_date = start_dt.strftime("%Y-%m-%d")

    df = None
    
    # 1. Try vnstock.api.quote (VCI or KBS)
    if has_vnstock_api and not force_yfinance:
        if symbol != "VNINDEX":
            for source in ['VCI', 'KBS']:
                try:
                    q = Quote(symbol=symbol, source=source)
                    df = q.history(start=start_date, end=end_date)
                    if df is not None and not df.empty:
                        # Multiply price columns by 1000 because domestic broker APIs return prices in thousands of VND
                        price_cols = ['open', 'high', 'low', 'close']
                        for col in price_cols:
                            if col in df.columns:
                                df[col] = df[col] * 1000
                                
                        df = _standardize_columns(df)
                        if not df.empty:
                            print(f"Successfully fetched {symbol} from vnstock.api.quote ({source})")
                            return df
                except Exception as e:
                    print(f"Failed to fetch {symbol} via vnstock.api.quote ({source}): {e}")
        
    # 2. Try yfinance fallback (also used for VNINDEX)
    if df is None or df.empty:
        try:
            yf_symbol = "^VNINDEX.VN" if symbol == "VNINDEX" else f"{symbol}.VN"
            print(f"Trying yfinance for {yf_symbol}...")
            ticker_data = yf.Ticker(yf_symbol)
            df_yf = ticker_data.history(start=start_date, end=end_date)
            if df_yf is not None and not df_yf.empty:
                df_yf = df_yf.reset_index()
                df = _standardize_columns(df_yf)
                if not df.empty:
                    # Drop any rows with NaN in critical columns (Close, Volume)
                    df = df.dropna(subset=['Close', 'Volume'])
                    if not df.empty:
                        print(f"Successfully fetched {symbol} from yfinance")
                        return df
        except Exception as e:
            print(f"Failed to fetch {symbol} via yfinance: {e}")

    return pd.DataFrame()

def _standardize_columns(df):
    """
    Standardizes dataframe columns to: Date, Open, High, Low, Close, Volume.
    Ensures Date is a datetime object and sorted.
    """
    if df is None or df.empty:
        return pd.DataFrame()
        
    df_new = df.copy()
    
    # Lowercase column names for easier matching
    df_new.columns = [c.lower() for c in df_new.columns]
    
    col_mapping = {}
    
    # Map Date
    for possible_date in ['date', 'time', 'datetime', 'timestamp']:
        if possible_date in df_new.columns:
            col_mapping[possible_date] = 'Date'
            break
    if 'Date' not in col_mapping and 'index' in df_new.columns:
        col_mapping['index'] = 'Date'
        
    # Map OHLCV
    for possible_open in ['open', 'mo_cua', 'open_price']:
        if possible_open in df_new.columns:
            col_mapping[possible_open] = 'Open'
            break
            
    for possible_high in ['high', 'cao_nhat', 'high_price']:
        if possible_high in df_new.columns:
            col_mapping[possible_high] = 'High'
            break
            
    for possible_low in ['low', 'thap_nhat', 'low_price']:
        if possible_low in df_new.columns:
            col_mapping[possible_low] = 'Low'
            break
            
    for possible_close in ['close', 'dong_cua', 'close_price']:
        if possible_close in df_new.columns:
            col_mapping[possible_close] = 'Close'
            break
            
    for possible_volume in ['volume', 'volume_traded', 'khoi_luong', 'match_volume', 'total_volume']:
        if possible_volume in df_new.columns:
            col_mapping[possible_volume] = 'Volume'
            break

    # If yfinance Index became 'date' or was named 'date'
    if 'Date' not in col_mapping:
        # Check index name
        if df.index.name and df.index.name.lower() in ['date', 'time', 'datetime']:
            df_new = df_new.reset_index()
            df_new.columns = [c.lower() for c in df_new.columns]
            col_mapping['date'] = 'Date'

    # Rename
    df_new = df_new.rename(columns=col_mapping)
    
    # Select only required columns if they exist
    required = ['Date', 'Open', 'High', 'Low', 'Close', 'Volume']
    available = [c for c in required if c in df_new.columns]
    
    df_res = df_new[available].copy()
    
    if 'Date' in df_res.columns:
        df_res['Date'] = pd.to_datetime(df_res['Date'])
        # Strip timezone if exists (like in yfinance)
        if df_res['Date'].dt.tz is not None:
            df_res['Date'] = df_res['Date'].dt.tz_localize(None)
        df_res = df_res.sort_values('Date').reset_index(drop=True)
    
    # Convert price and volume columns to numeric
    for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
        if col in df_res.columns:
            df_res[col] = pd.to_numeric(df_res[col], errors='coerce')
            
    # Drop rows with NaN in Date or Close
    df_res = df_res.dropna(subset=['Date', 'Close'])
    
    return df_res
