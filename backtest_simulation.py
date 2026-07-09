import sys
import os
import pandas as pd
import numpy as np
import datetime

# Add current directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import data_fetcher
import wyckoff_analyzer

def run_portfolio_backtest():
    print("=" * 70)
    print("BẮT ĐẦU MÔ PHỎNG BACKTEST HỆ THỐNG - NAV 1 TỶ VND (1 YEAR)")
    print("=" * 70)
    
    # 1. Setup portfolio parameters
    initial_nav = 1000000000.0  # 1 Billion VND
    cash = initial_nav
    max_concurrent_trades = 5
    allocation_per_trade = initial_nav / max_concurrent_trades  # 200M per trade
    
    # Universe of major liquid HOSE stocks (representing different sectors)
    tickers = [
        "HPG", "SSI", "VCB", "FPT", "MWG", "VHM", "VIC", "VNM", "TCB", "CTG",
        "ACB", "MBB", "STB", "VND", "KBC", "HSG", "NKG", "DIG", "DXG", "NLG"
    ]
    
    print(f"Danh mục quét: {len(tickers)} cổ phiếu thanh khoản cao sàn HOSE.")
    print(f"Số lượng vị thế tối đa: {max_concurrent_trades} vị thế (200 triệu VND/vị thế).")
    
    # 2. Fetch historical data for all tickers
    print("\nĐang tải dữ liệu...")
    data_dict = {}
    for symbol in tickers:
        try:
            df = data_fetcher.get_historical_data(symbol)
            if not df.empty and len(df) > 100:
                df = wyckoff_analyzer.calculate_indicators(df)
                data_dict[symbol] = df
        except Exception as e:
            print(f"Lỗi tải {symbol}: {e}")
            
    # Load VNINDEX data for relative strength comparison
    vnindex_df = data_fetcher.get_historical_data("VNINDEX")
    if not vnindex_df.empty:
        vnindex_df = wyckoff_analyzer.calculate_indicators(vnindex_df)
    else:
        print("Cảnh báo: Không tải được dữ liệu VNINDEX. Tự động tạo dữ liệu chỉ số giả lập (flat) để tiếp tục backtest.")
        hpg_df = data_dict["HPG"]
        vnindex_df = pd.DataFrame({
            "Date": hpg_df["Date"],
            "Close": 1200.0,
            "Open": 1200.0,
            "High": 1200.0,
            "Low": 1200.0,
            "Volume": 1000000,
            "Return": 0.0
        })
        vnindex_df = wyckoff_analyzer.calculate_indicators(vnindex_df)

    # Find aligned dates for simulation (last 252 trading days)
    # We will simulate day-by-day for the past year
    # Get common dates from HPG (a reliable benchmark ticker)
    if "HPG" not in data_dict:
        print("Lỗi: Không tải được dữ liệu chuẩn HPG.")
        return
        
    simulation_dates = data_dict["HPG"].tail(252)['Date'].tolist()
    print(f"Khoảng thời gian mô phỏng: {len(simulation_dates)} phiên giao dịch (từ {simulation_dates[0].strftime('%Y-%m-%d')} đến {simulation_dates[-1].strftime('%Y-%m-%d')})")
    
    active_trades = [] # List of dicts: {symbol, entry_date, entry_index, entry_price, size_shares, sl_price, target_price, days_held, setup_type}
    closed_trades = [] # List of dicts: {symbol, entry_date, exit_date, entry_price, exit_price, pnl_pct, pnl_vnd, setup_type, exit_reason}
    
    # 3. Simulate day-by-day
    for day_idx, current_date in enumerate(simulation_dates):
        # A. Check and exit existing active trades
        retained_trades = []
        for trade in active_trades:
            symbol = trade['symbol']
            df_stock = data_dict[symbol]
            
            # Find current day row in stock data
            day_row = df_stock[df_stock['Date'] == current_date]
            if day_row.empty:
                # No trading on this day for this stock, keep trade active
                retained_trades.append(trade)
                continue
                
            row = day_row.iloc[0]
            current_close = row['Close']
            current_low = row['Low']
            
            trade['days_held'] += 1
            
            # Check Stop Loss
            if current_low <= trade['sl_price']:
                # Stopped out! Calculate exit at SL price or open if gap down
                exit_price = min(trade['sl_price'], row['Open'])
                pnl_pct = (exit_price - trade['entry_price']) / trade['entry_price'] * 100
                pnl_vnd = (exit_price - trade['entry_price']) * trade['size_shares']
                
                cash += trade['entry_price'] * trade['size_shares'] + pnl_vnd
                closed_trades.append({
                    "symbol": symbol,
                    "entry_date": trade['entry_date'],
                    "exit_date": current_date,
                    "entry_price": trade['entry_price'],
                    "exit_price": exit_price,
                    "pnl_pct": pnl_pct,
                    "pnl_vnd": pnl_vnd,
                    "setup_type": trade['setup_type'],
                    "exit_reason": "Stop Loss"
                })
                continue
                
            # Check 1-month time limit (21 trading days)
            if trade['days_held'] >= 21:
                # Time exit at close price
                exit_price = current_close
                pnl_pct = (exit_price - trade['entry_price']) / trade['entry_price'] * 100
                pnl_vnd = (exit_price - trade['entry_price']) * trade['size_shares']
                
                cash += trade['entry_price'] * trade['size_shares'] + pnl_vnd
                closed_trades.append({
                    "symbol": symbol,
                    "entry_date": trade['entry_date'],
                    "exit_date": current_date,
                    "entry_price": trade['entry_price'],
                    "exit_price": exit_price,
                    "pnl_pct": pnl_pct,
                    "pnl_vnd": pnl_vnd,
                    "setup_type": trade['setup_type'],
                    "exit_reason": "Time Exit (1M)"
                })
                continue
                
            # Keep trade active
            retained_trades.append(trade)
            
        active_trades = retained_trades
        
        # B. Check and enter new trades if we have cash / slots
        available_slots = max_concurrent_trades - len(active_trades)
        if available_slots > 0 and cash >= allocation_per_trade:
            # Look for signals on this day
            signals_today = []
            
            for symbol in tickers:
                # Check if we are already holding this symbol
                if any(t['symbol'] == symbol for t in active_trades):
                    continue
                    
                df_stock = data_dict[symbol]
                # We need historical data up to this day to run analysis without lookahead bias
                historical_subset = df_stock[df_stock['Date'] <= current_date]
                if len(historical_subset) < 40:
                    continue
                    
                last_row = historical_subset.iloc[-1]
                
                # Run Wyckoff structural analysis
                # (For speed, we compute support/resistance of past 40 days)
                ref_df = historical_subset.tail(40).iloc[:-5]
                if ref_df.empty:
                    ref_df = historical_subset
                support = float(ref_df['Low'].min())
                resistance = float(ref_df['High'].max())
                
                close = last_row['Close']
                
                # Check latest VSA patterns
                prev_row = historical_subset.iloc[-2]
                prev_row2 = historical_subset.iloc[-3]
                vsa_pat, _ = wyckoff_analyzer.detect_vsa_bar(last_row, prev_row, prev_row2)
                
                # Trigger criteria
                trigger_type = None
                
                # Setup 1: Spring (Price dips below support in last 2 days and closes back above it)
                if last_row['Low'] < support and close > support:
                    trigger_type = "Spring"
                # Setup 2: SOS Breakout (Price breaks resistance on high volume)
                elif close > resistance and last_row['Volume'] > last_row['VolMA20']:
                    trigger_type = "SOS Breakout"
                # Setup 3: LPS Pullback (Pullback to MA20 on low volume in uptrend)
                elif close > last_row['MA20'] and last_row['Volume'] < last_row['VolMA20'] and abs(last_row['Low'] - last_row['MA20'])/last_row['MA20'] < 0.02:
                    if last_row['MA20'] > last_row['MA50']:
                        trigger_type = "LPS Pullback"
                        
                if trigger_type:
                    signals_today.append({
                        "symbol": symbol,
                        "price": close,
                        "setup_type": trigger_type,
                        "support": support,
                        "resistance": resistance
                    })
            
            # Sort signals: Prioritize Spring, then SOS, then LPS
            setup_priority = {"Spring": 0, "SOS Breakout": 1, "LPS Pullback": 2}
            signals_today = sorted(signals_today, key=lambda x: setup_priority[x['setup_type']])
            
            # Enter trades
            for sig in signals_today[:available_slots]:
                if cash < allocation_per_trade:
                    break
                    
                symbol = sig['symbol']
                entry_price = sig['price']
                setup_type = sig['setup_type']
                
                # Calculate stop loss
                if setup_type == "Spring":
                    sl_price = sig['support'] * 0.96  # 4% below support
                elif setup_type == "SOS Breakout":
                    sl_price = entry_price * 0.95    # 5% below breakout entry
                else: # LPS Pullback
                    sl_price = entry_price * 0.95    # 5% below entry
                    
                size_shares = int(allocation_per_trade / entry_price)
                
                if size_shares > 0:
                    cash -= size_shares * entry_price
                    active_trades.append({
                        "symbol": symbol,
                        "entry_date": current_date,
                        "entry_price": entry_price,
                        "size_shares": size_shares,
                        "sl_price": sl_price,
                        "days_held": 0,
                        "setup_type": setup_type
                    })
                    # logger.info(f"Entered trade: {symbol} via {setup_type} at {entry_price:,.0f} VND")

    # 4. Final portfolio calculation
    final_equity = cash
    for trade in active_trades:
        symbol = trade['symbol']
        df_stock = data_dict[symbol]
        last_close = df_stock.iloc[-1]['Close']
        final_equity += last_close * trade['size_shares']
        
    net_profit = final_equity - initial_nav
    total_roi = (final_equity - initial_nav) / initial_nav * 100
    
    print("\n" + "=" * 40)
    print("KẾT QUẢ BACKTEST HỆ THỐNG DANH MỤC")
    print("=" * 40)
    print(f"NAV ban đầu: {initial_nav:,.0f} VND (1 Tỷ)")
    print(f"NAV cuối kỳ: {final_equity:,.0f} VND")
    print(f"Lợi nhuận ròng: {net_profit:+,.0f} VND")
    print(f"Tỷ suất lợi nhuận (ROI): <b>{total_roi:+.2f}%</b>")
    print(f"Vị thế còn đang nắm giữ: {len(active_trades)} vị thế")
    print(f"Số lượng lệnh đã đóng: {len(closed_trades)} lệnh")
    
    # 5. Calculate statistics by setup type
    if closed_trades:
        df_trades = pd.DataFrame(closed_trades)
        win_trades = df_trades[df_trades['pnl_pct'] > 0]
        loss_trades = df_trades[df_trades['pnl_pct'] <= 0]
        
        global_win_rate = len(win_trades) / len(df_trades) * 100
        print(f"Tỉ lệ thắng toàn cục (Win Rate): {global_win_rate:.1f}%")
        print(f"Số lệnh thắng: {len(win_trades)} | Số lệnh thua: {len(loss_trades)}")
        
        avg_win_pct = win_trades['pnl_pct'].mean() if not win_trades.empty else 0.0
        avg_loss_pct = loss_trades['pnl_pct'].mean() if not loss_trades.empty else 0.0
        rr_ratio = avg_win_pct / abs(avg_loss_pct) if avg_loss_pct != 0 else 2.0
        print(f"Lợi nhuận TB lệnh thắng: {avg_win_pct:+.2f}%")
        print(f"Thua lỗ TB lệnh thua: {avg_loss_pct:+.2f}%")
        print(f"Tỷ lệ Risk/Reward thực tế (Lãi TB / Lỗ TB): {rr_ratio:.2f}:1")
        
        print("\nThống kê hiệu quả theo từng dạng thiết lập (Setup):")
        for setup in df_trades['setup_type'].unique():
            df_setup = df_trades[df_trades['setup_type'] == setup]
            setup_wins = df_setup[df_setup['pnl_pct'] > 0]
            setup_win_rate = len(setup_wins) / len(df_setup) * 100
            setup_avg_ret = df_setup['pnl_pct'].mean()
            print(f" • <b>{setup}</b>: {len(df_setup)} lệnh | Tỉ lệ thắng: {setup_win_rate:.1f}% | ROI trung bình: {setup_avg_ret:+.2f}%")
    else:
        print("Không có lệnh nào được thực hiện trong thời gian mô phỏng.")
        
    print("=" * 70)

if __name__ == "__main__":
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    run_portfolio_backtest()
