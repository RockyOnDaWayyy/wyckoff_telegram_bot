import matplotlib
matplotlib.use('Agg')  # Non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd
from config import TEMP_DIR

def plot_wyckoff_chart(df, analysis, symbol):
    """
    Generate a high-quality candlestick and volume chart with Wyckoff markings.
    Saves the chart in the temporary directory and returns the file path.
    """
    # Select last 90 trading days for the chart to keep it clean and readable
    df_chart = df.tail(90).copy()
    if df_chart.empty:
        return None

    # Enable styles for a modern dark-theme feel
    plt.style.use('dark_background')
    
    # Create figure with 2 subplots (Ratio 3:1 for Price vs Volume)
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True, 
                                   gridspec_kw={'height_ratios': [3, 1]})
    fig.patch.set_facecolor('#131722')  # Premium dark background (TradingView style)
    ax1.set_facecolor('#131722')
    ax2.set_facecolor('#131722')
    
    # 1. Custom Candlestick Drawing
    # Green/Red candle colors
    color_up = '#26a69a'
    color_down = '#ef5350'
    
    df_chart['date_num'] = mdates.date2num(df_chart['Date'])
    
    # Draw wicks and bodies
    for idx, row in df_chart.iterrows():
        color = color_up if row['Close'] >= row['Open'] else color_down
        
        # Wick (Low to High line)
        ax1.plot([row['date_num'], row['date_num']], [row['Low'], row['High']], color=color, linewidth=1)
        
        # Body (Open to Close rectangle)
        open_val = row['Open']
        close_val = row['Close']
        body_height = abs(close_val - open_val)
        y_bottom = min(open_val, close_val)
        
        # In case Open == Close, make a tiny flat bar
        if body_height == 0:
            body_height = (row['High'] - row['Low']) * 0.05
            
        rect = plt.Rectangle((row['date_num'] - 0.35, y_bottom), 0.7, body_height, 
                             facecolor=color, edgecolor=color, alpha=0.9)
        ax1.add_patch(rect)

    # 2. Draw Moving Averages
    ax1.plot(df_chart['date_num'], df_chart['MA20'].tail(90), color='#2196f3', linewidth=1.2, label='MA20', alpha=0.7)
    ax1.plot(df_chart['date_num'], df_chart['MA50'].tail(90), color='#ff9800', linewidth=1.2, label='MA50', alpha=0.7)

    # 3. Draw Support and Resistance lines
    support = analysis.get("support")
    resistance = analysis.get("resistance")
    
    if support is not None:
        ax1.axhline(support, color='#e91e63', linestyle='--', linewidth=1.5, alpha=0.8, label=f'Support: {support:,.0f}')
    if resistance is not None:
        ax1.axhline(resistance, color='#4caf50', linestyle='--', linewidth=1.5, alpha=0.8, label=f'Resistance: {resistance:,.0f}')

    # 4. Annotate Wyckoff Signals (Filter signals within the chart window)
    min_date = df_chart['Date'].min()
    for sig in analysis.get("signals", []):
        sig_date = pd.to_datetime(sig['date'])
        if sig_date >= min_date:
            date_num = mdates.date2num(sig_date)
            price = sig['price']
            label = sig['label']
            
            # Position text offset based on signal type
            offset = 15 if "Spring" in label or label == "SCLX" or label == "ST" else -15
            color = '#26a69a' if "Spring" in label or label == "SOS" or label == "LPS" else '#ef5350'
            
            ax1.annotate(
                label,
                xy=(date_num, price),
                xytext=(0, offset),
                textcoords='offset points',
                arrowprops=dict(arrowstyle="->", color=color, lw=1.2),
                color='#ffffff',
                weight='bold',
                fontsize=9,
                bbox=dict(boxstyle="round,pad=0.3", fc=color, ec="none", alpha=0.75),
                ha='center'
            )

    # 5. Draw Volume Bar Chart
    for idx, row in df_chart.iterrows():
        color = color_up if row['Close'] >= row['Open'] else color_down
        ax2.bar(row['date_num'], row['Volume'], color=color, width=0.7, alpha=0.7)
    
    # Draw Vol MA20
    ax2.plot(df_chart['date_num'], df_chart['VolMA20'].tail(90), color='#ffeb3b', linewidth=1.0, alpha=0.6, label='VolMA20')

    # Formatting Charts
    ax1.set_title(symbol, fontsize=16, weight='bold', color='#ffffff', pad=15)
    ax1.legend(loc='upper left', framealpha=0.2, fontsize=9)
    ax2.legend(loc='upper left', framealpha=0.2, fontsize=9)
    
    # Configure grid lines
    ax1.grid(True, color='#2a2e39', linestyle=':', alpha=0.5)
    ax2.grid(True, color='#2a2e39', linestyle=':', alpha=0.5)
    
    # Format X-axis Dates
    ax2.xaxis.set_major_formatter(mdates.DateFormatter('%d/%m/%Y'))
    ax2.xaxis.set_major_locator(mdates.DayLocator(interval=15))
    fig.autofmt_xdate()
    
    # Remove labels from price axis, keep bottom axis ticks only
    ax1.tick_params(axis='x', which='both', bottom=False, labelbottom=False)
    ax1.tick_params(axis='y', colors='#848e9c', labelsize=9)
    ax2.tick_params(axis='x', colors='#848e9c', labelsize=9)
    ax2.tick_params(axis='y', colors='#848e9c', labelsize=9)
    
    # Adjust layout
    plt.tight_layout()
    
    # Save Image
    filepath = TEMP_DIR / f"{symbol}_wyckoff.png"
    plt.savefig(filepath, dpi=150, facecolor=fig.get_facecolor(), bbox_inches='tight')
    plt.close()
    
    return str(filepath)
