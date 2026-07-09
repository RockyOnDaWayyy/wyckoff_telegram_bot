import sys
import os
import pandas as pd
import numpy as np
import datetime

# Add current directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import data_fetcher
import wyckoff_analyzer

def run_optimized_portfolio_backtest():
    print("=" * 70)
    print("MÔ PHỎNG BACKTEST HỆ THỐNG WYCKOFF TỐI ƯU (NAV 1 TỶ VND)")
    print("=" * 70)
    
    # 1. Setup portfolio parameters
    initial_nav = 1000000000.0  # 1 Billion VND
    cash = initial_nav
    max_concurrent_trades = 5
    allocation_per_trade = initial_nav / max_concurrent_trades  # 200M per trade
    
    # Universe of major liquid HOSE stocks
    tickers = [
        "HPG", "SSI", "VCB", "FPT", "MWG", "VHM", "VIC", "VNM", "TCB", "CTG",
        "ACB", "MBB", "STB", "VND", "KBC", "HSG", "NKG", "DIG", "DXG", "NLG"
    ]
    
    print(f"Danh mục quét: {len(tickers)} cổ phiếu thanh khoản cao sàn HOSE.")
    print(f"Số lượng vị thế tối đa: {max_concurrent_trades} vị thế (200 triệu VND/vị thế).")
    print(f"Chiến lược tối ưu: Chỉ mua Spring Type 3 (Cạn cung) và SOS Breakout. Không mua LPS Pullback.")
    
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
            
    if "HPG" not in data_dict:
        print("Lỗi: Không tải được dữ liệu chuẩn HPG.")
        return
        
    simulation_dates = data_dict["HPG"].tail(252)['Date'].tolist()
    print(f"Khoảng thời gian mô phỏng: {len(simulation_dates)} phiên giao dịch (từ {simulation_dates[0].strftime('%Y-%m-%d')} đến {simulation_dates[-1].strftime('%Y-%m-%d')})")
    
    active_trades = [] # List of dicts
    closed_trades = [] # List of dicts
    
    # 3. Simulate day-by-day
    for day_idx, current_date in enumerate(simulation_dates):
        # A. Check and exit existing active trades
        retained_trades = []
        for trade in active_trades:
            symbol = trade['symbol']
            df_stock = data_dict[symbol]
            
            day_row = df_stock[df_stock['Date'] == current_date]
            if day_row.empty:
                retained_trades.append(trade)
                continue
                
            row = day_row.iloc[0]
            current_close = row['Close']
            current_low = row['Low']
            
            trade['days_held'] += 1
            
            # Check Stop Loss
            if current_low <= trade['sl_price']:
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
                
            retained_trades.append(trade)
            
        active_trades = retained_trades
        
        # B. Check and enter new trades
        available_slots = max_concurrent_trades - len(active_trades)
        if available_slots > 0 and cash >= allocation_per_trade:
            signals_today = []
            
            for symbol in tickers:
                if any(t['symbol'] == symbol for t in active_trades):
                    continue
                    
                df_stock = data_dict[symbol]
                historical_subset = df_stock[df_stock['Date'] <= current_date]
                if len(historical_subset) < 40:
                    continue
                    
                last_row = historical_subset.iloc[-1]
                
                ref_df = historical_subset.tail(40).iloc[:-5]
                if ref_df.empty:
                    ref_df = historical_subset
                support = float(ref_df['Low'].min())
                resistance = float(ref_df['High'].max())
                
                close = last_row['Close']
                
                trigger_type = None
                
                # Setup 1: Spring Type 3 (Price dips below support, closes back above, AND volume is LOW)
                if last_row['Low'] < support and close > support and last_row['Volume'] < last_row['VolMA20']:
                    trigger_type = "Spring Type 3"
                # Setup 2: SOS Breakout (Price breaks resistance on high volume)
                elif close > resistance and last_row['Volume'] > last_row['VolMA20'] * 1.2:
                    trigger_type = "SOS Breakout"
                        
                if trigger_type:
                    signals_today.append({
                        "symbol": symbol,
                        "price": close,
                        "setup_type": trigger_type,
                        "support": support,
                        "resistance": resistance
                    })
            
            # Sort signals: Prioritize Spring Type 3, then SOS Breakout
            setup_priority = {"Spring Type 3": 0, "SOS Breakout": 1}
            signals_today = sorted(signals_today, key=lambda x: setup_priority.get(x['setup_type'], 2))
            
            for sig in signals_today[:available_slots]:
                if cash < allocation_per_trade:
                    break
                    
                symbol = sig['symbol']
                entry_price = sig['price']
                setup_type = sig['setup_type']
                
                # Calculate stop loss
                if "Spring" in setup_type:
                    sl_price = sig['support'] * 0.96  # 4% below support
                else: # SOS Breakout
                    sl_price = entry_price * 0.95    # 5% below breakout entry
                    
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
    print("KẾT QUẢ BACKTEST HỆ THỐNG WYCKOFF TỐI ƯU")
    print("=" * 40)
    print(f"NAV ban đầu: {initial_nav:,.0f} VND (1 Tỷ)")
    print(f"NAV cuối kỳ: {final_equity:,.0f} VND")
    print(f"Lợi nhuận ròng: {net_profit:+,.0f} VND")
    print(f"Tỷ suất lợi nhuận (ROI): {total_roi:+.2f}%")
    print(f"Vị thế còn đang nắm giữ: {len(active_trades)} vị thế")
    print(f"Số lượng lệnh đã đóng: {len(closed_trades)} lệnh")
    
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
            print(f" • {setup}: {len(df_setup)} lệnh | Tỉ lệ thắng: {setup_win_rate:.1f}% | ROI trung bình: {setup_avg_ret:+.2f}%")
    else:
        print("Không có lệnh nào được thực hiện trong thời gian mô phỏng.")
    print("=" * 70)

if __name__ == "__main__":
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    run_optimized_portfolio_backtest()
