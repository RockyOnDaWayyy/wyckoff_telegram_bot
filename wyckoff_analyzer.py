import numpy as np
import pandas as pd
from config import MIN_SWING_WINDOW, RelativeStrengthWindow, VaR_ALPHA, VaR_DAYS

def calculate_indicators(df):
    """
    Calculate basic technical columns needed for Wyckoff & VSA analysis.
    """
    if df.empty or len(df) < 20:
        return df
        
    df = df.copy()
    
    # Moving Averages
    df['MA20'] = df['Close'].rolling(20).mean()
    df['MA50'] = df['Close'].rolling(50).mean()
    df['MA200'] = df['Close'].rolling(200).mean()
    
    # Volume averages and std
    df['VolMA20'] = df['Volume'].rolling(20).mean()
    df['VolStd20'] = df['Volume'].rolling(20).std()
    
    # Spread (biên độ giá)
    df['Spread'] = df['High'] - df['Low']
    df['SpreadMA20'] = df['Spread'].rolling(20).mean()
    df['SpreadStd20'] = df['Spread'].rolling(20).std()
    
    # Close Position (vị trí đóng cửa trong thanh nến)
    # 0 = Low, 1 = High. Middle is 0.5. Upper third is > 0.66, lower third is < 0.33
    df['ClosePos'] = (df['Close'] - df['Low']) / (df['High'] - df['Low'] + 1e-6)
    
    # Daily returns
    df['Return'] = df['Close'].pct_change()
    
    return df

def detect_vsa_bar(row, prev_row, prev_row2):
    """
    Classify a single candle bar into VSA (Volume Spread Analysis) patterns.
    Returns pattern name or None, and a brief description.
    """
    if pd.isna(row['VolMA20']) or pd.isna(row['VolStd20']):
        return None, ""
        
    vol = row['Volume']
    vol_ma = row['VolMA20']
    vol_std = row['VolStd20']
    spread = row['Spread']
    spread_ma = row['SpreadMA20']
    close_pos = row['ClosePos']
    is_up = row['Close'] > prev_row['Close']
    is_down = row['Close'] < prev_row['Close']
    
    # Volume categories
    is_high_vol = vol > vol_ma + 1.0 * vol_std
    is_very_high_vol = vol > vol_ma + 2.0 * vol_std
    is_low_vol = vol < vol_ma - 0.5 * vol_std
    
    # Spread categories
    is_wide_spread = spread > spread_ma + 0.5 * row['SpreadStd20']
    is_narrow_spread = spread < spread_ma - 0.5 * row['SpreadStd20']
    
    # 1. Up-thrust (UT)
    # - Up or down bar, updates local high, wide spread, closes in the lower third, high volume
    if is_high_vol and is_wide_spread and close_pos < 0.33 and row['High'] > prev_row['High']:
        return "Up-thrust", "Bẫy tăng giá (Bull Trap) với khối lượng lớn. Lực bán mạnh từ Smart Money."
        
    # 2. Pseudo Up-thrust
    # - Same as UT but low volume
    if is_low_vol and is_wide_spread and close_pos < 0.33 and row['High'] > prev_row['High']:
        return "Pseudo Up-thrust", "Bẫy tăng giá yếu với khối lượng thấp. Cần xác nhận thêm từ nến tiếp theo."
        
    # 3. Stopping Volume
    # - Down bar, very high volume, closes in the upper third (absorption of selling)
    if is_down and is_very_high_vol and close_pos > 0.66:
        return "Stopping Volume", "Lực cầu hấp thụ cực mạnh ở vùng giá thấp. Smart Money đang gom hàng chặn đà giảm."
        
    # 4. No Demand
    # - Up bar, narrow spread, closes in lower/middle third, low volume (lower than prev 2 bars)
    if is_up and is_narrow_spread and close_pos < 0.5 and vol < prev_row['Volume'] and vol < prev_row2['Volume']:
        return "No Demand", "Tăng giá yếu với biên độ hẹp và khối lượng thấp. Thiếu lực cầu từ Smart Money."
        
    # 5. Test (Spring Test)
    # - Down bar, low volume, closes in upper half (test of remaining supply)
    if is_down and is_low_vol and close_pos > 0.5:
        return "Test", "Test cung thành công với khối lượng thấp. Lượng cung cạn kiệt, chuẩn bị tăng giá."
        
    # 6. Lack of Offer
    # - Down bar, narrow spread, low volume, closes in lower third
    if is_down and is_narrow_spread and is_low_vol and close_pos < 0.33:
        return "Lack of Offer", "Lực bán cạn kiệt ở vùng đáy. Smart Money ngừng ép giá, giá dễ hồi phục."
        
    # 7. Power A (Strength)
    # - Up bar, average/wide spread, high volume, closes in upper third
    if is_up and (not is_narrow_spread) and is_high_vol and close_pos > 0.66:
        return "Power A", "Nến tăng giá mạnh mẽ với khối lượng lớn. Dòng tiền lớn tham gia đẩy giá quyết liệt."
        
    # 8. Force B (Strength absorption)
    # - Down bar, narrow spread, high volume, closes in upper third
    if is_down and is_narrow_spread and is_high_vol and close_pos > 0.66:
        return "Force B", "Nến giảm biên độ hẹp nhưng khối lượng lớn. Lực cầu đang âm thầm hấp thụ hết lực bán."

    return None, ""

def calculate_quant_metrics(df):
    """
    Calculate quantitative metrics for a 1-month holding period (21 trading days)
    simulated over the past 252 trading days to prevent overfitting.
    """
    metrics = {
        "var_95": 0.0, 
        "mdd": 0.0, 
        "win_rate": 0.0, 
        "avg_roi": 0.0, 
        "rr_ratio": 0.0
    }
    
    if df.empty or len(df) < 50:
        return metrics
        
    # Get recent data including the extra days needed for forward shift
    df_recent = df.tail(252 + 21).copy()
    if len(df_recent) < 21:
        return metrics
        
    # Calculate 1-month (21 trading days) forward return
    df_recent['Forward_Return'] = (df_recent['Close'].shift(-21) - df_recent['Close']) / df_recent['Close'] * 100
    
    # Select the active 252 trading days (where we know the outcome)
    df_active = df_recent.iloc[:252].dropna(subset=['Forward_Return'])
    
    returns = df_active['Forward_Return'].values
    if len(returns) > 0:
        wins = returns[returns > 0]
        losses = returns[returns <= 0]
        
        # 1. Win Rate %
        metrics["win_rate"] = len(wins) / len(returns) * 100
        
        # 2. Average ROI %
        metrics["avg_roi"] = returns.mean()
        
        # 3. Risk/Reward Ratio (Average Win / Average Loss)
        avg_win = wins.mean() if len(wins) > 0 else 0.0
        avg_loss = abs(losses.mean()) if len(losses) > 0 else 0.0
        metrics["rr_ratio"] = avg_win / avg_loss if avg_loss > 0 else (2.0 if avg_win > 0 else 0.0)
        
        # 4. VaR 95% (21-day historical)
        var_pct = np.percentile(returns, 5)
        metrics["var_95"] = -var_pct if var_pct < 0 else 0.0
        
    # 5. Maximum Drawdown (MDD) of the stock over the past 252 trading days
    df_1y = df.tail(252).copy()
    if not df_1y.empty:
        cum_max = df_1y['Close'].cummax()
        drawdown = (df_1y['Close'] - cum_max) / cum_max
        metrics["mdd"] = drawdown.min() * 100
        
    return metrics

def detect_wyckoff_structure(df):
    """
    Analyze the daily price series to identify Wyckoff support, resistance,
    phases, and specific signals like SCLX, AR, ST, Spring, SOS, LPS.
    """
    result = {
        "support": None,
        "resistance": None,
        "signals": [],  # List of dicts: {"date": date, "label": label, "price": price, "desc": desc}
        "phase": "Sideway",  # Default if not clearly determined
        "phase_desc": "Thị trường đang vận động tích lũy đi ngang tích lũy/phân phối chưa rõ xu hướng.",
        "relative_strength": "Neutral",
        "rs_desc": ""
    }
    
    if df.empty or len(df) < 60:
        return result
        
    # Step 1: Detect SCLX (Selling Climax) and AR (Automatic Rally) in the past 120 days
    # We look for a sharp decline on high volume followed by a rebound
    df_last_120 = df.tail(120).copy().reset_index(drop=True)
    
    sclx_idx = None
    max_vol_dev = 0
    
    for i in range(20, len(df_last_120) - 10):
        row = df_last_120.iloc[i]
        # Look for Down day with extremely high volume (Volume standard deviation > 1.5)
        if row['Close'] < df_last_120.iloc[i-1]['Close'] and row['Volume'] > row['VolMA20'] + 1.5 * row['VolStd20']:
            # The close should be off the low (showing buying pressure)
            if row['ClosePos'] > 0.35:
                vol_dev = (row['Volume'] - row['VolMA20']) / row['VolStd20']
                if vol_dev > max_vol_dev:
                    max_vol_dev = vol_dev
                    sclx_idx = i
                    
    # If SCLX found, determine support and find AR (Automatic Rally)
    if sclx_idx is not None:
        sclx_row = df_last_120.iloc[sclx_idx]
        support_price = sclx_row['Low']
        result["support"] = support_price
        result["signals"].append({
            "date": sclx_row['Date'],
            "label": "SCLX",
            "price": support_price,
            "desc": "Selling Climax: Điểm quá bán với khối lượng lớn, đánh dấu dòng tiền thông minh bắt đầu gom hàng chặn đà rơi."
        })
        
        # AR is the highest peak in the 20 days after SCLX
        ar_window = df_last_120.iloc[sclx_idx+1 : min(sclx_idx+25, len(df_last_120))]
        if not ar_window.empty:
            ar_idx = ar_window['High'].idxmax()
            ar_row = df_last_120.iloc[ar_idx]
            resistance_price = ar_row['High']
            result["resistance"] = resistance_price
            result["signals"].append({
                "date": ar_row['Date'],
                "label": "AR",
                "price": resistance_price,
                "desc": "Automatic Rally: Sự hồi phục tự nhiên sau Selling Climax, đỉnh của AR thiết lập đường kháng cự của biên giao dịch."
            })
            
            # Secondary Test (ST): Look for a test of the support after AR
            st_window = df_last_120.iloc[ar_idx+1 : min(ar_idx+30, len(df_last_120))]
            if not st_window.empty:
                # Find the lowest point in the ST window
                st_idx = st_window['Low'].idxmin()
                st_row = df_last_120.iloc[st_idx]
                # If low is near support (within 3% or slightly below)
                if abs(st_row['Low'] - support_price) / support_price < 0.04:
                    result["signals"].append({
                        "date": st_row['Date'],
                        "label": "ST",
                        "price": st_row['Low'],
                        "desc": "Secondary Test: Giá điều chỉnh về gần đáy cũ với khối lượng giảm dần, xác nhận lực bán đã suy yếu."
                    })
    
    # Calculate short-term support and resistance (30-day reference window)
    # To allow breakout detection, we base the range on days -40 to -5.
    ref_df = df.tail(40).iloc[:-5] if len(df) >= 40 else df.iloc[:-2]
    if ref_df.empty:
        ref_df = df
        
    short_support = float(ref_df['Low'].min())
    short_resistance = float(ref_df['High'].max())
    
    # Adapt to current close so they are always below and above it respectively
    current_close = float(df.iloc[-1]['Close'])
    if short_support > current_close:
        short_support = float(df['Low'].tail(15).min())
    if short_resistance < current_close:
        short_resistance = float(df['High'].tail(15).max())
        
    result["support"] = short_support
    result["resistance"] = short_resistance
    support_price = short_support
    resistance_price = short_resistance
    
    # Step 2: Detect Spring (Phase C)
    # A Spring is when price dips below support but recovers within 5 days
    for i in range(len(df) - 15, len(df)):
        if i < 0:
            continue
        row = df.iloc[i]
        # Price broke below support
        if row['Low'] < support_price:
            # Check if it recovered (close is back above support, or within next 3 bars it closes above)
            recovered = False
            recovery_idx = None
            for j in range(i, min(i+5, len(df))):
                if df.iloc[j]['Close'] > support_price:
                    recovered = True
                    recovery_idx = j
                    break
            if recovered:
                spring_row = df.iloc[i]
                rec_row = df.iloc[recovery_idx]
                
                # Check volume on breakout
                vol_dev = (spring_row['Volume'] - spring_row['VolMA20']) / (spring_row['VolStd20'] + 1e-6)
                if vol_dev < 0.5:
                    label = "Spring (Type 3)"
                    desc = "Spring Loại 3: Rũ bỏ cạn kiệt cung với khối lượng cực thấp. Điểm mua sớm cực kỳ an toàn."
                else:
                    label = "Spring (Type 2)"
                    desc = "Spring/Shakeout Loại 2: Rũ bỏ với khối lượng trung bình. Cần một phiên test lại thành công trước khi mua."
                    
                result["signals"].append({
                    "date": spring_row['Date'],
                    "label": label,
                    "price": spring_row['Low'],
                    "desc": desc
                })
                break # Only register the latest spring

    # Step 3: Detect SOS (Sign of Strength - Phase D)
    # Price breaks above resistance on high volume
    for i in range(len(df) - 15, len(df)):
        if i < 0:
            continue
        row = df.iloc[i]
        if row['Close'] > resistance_price and row['Volume'] > row['VolMA20'] + 0.5 * row['VolStd20']:
            result["signals"].append({
                "date": row['Date'],
                "label": "SOS",
                "price": row['Close'],
                "desc": "Sign of Strength (JAC): Giá bứt phá vượt kháng cự với biên độ rộng và khối lượng lớn, xác nhận xu hướng tăng bắt đầu."
            })
            break

    # Step 4: Detect LPS (Last Point of Support / BUEC)
    # A pullback near or on the resistance (now support) on low volume after an SOS
    has_sos = any(s['label'] == "SOS" for s in result["signals"])
    if has_sos:
        sos_date = next(s['date'] for s in result["signals"] if s['label'] == "SOS")
        post_sos_df = df[df['Date'] > sos_date].tail(10)
        if not post_sos_df.empty:
            # Look for local low in post_sos
            lps_idx = post_sos_df['Low'].idxmin()
            lps_row = post_sos_df.loc[lps_idx]
            # Check if volume is low and price sits near resistance
            if lps_row['Volume'] < lps_row['VolMA20'] and abs(lps_row['Low'] - resistance_price) / resistance_price < 0.05:
                result["signals"].append({
                    "date": lps_row['Date'],
                    "label": "LPS / BUEC",
                    "price": lps_row['Low'],
                    "desc": "Last Point of Support / BUEC: Phiên test lại kháng cự cũ (nay là hỗ trợ) với khối lượng cạn kiệt. Điểm gia tăng tỷ trọng lý tưởng."
                })

    # Step 5: Detect UTAD (Upthrust After Distribution - Phase C in Distribution)
    # Price breaks resistance but fails and closes back inside the range
    for i in range(len(df) - 15, len(df)):
        if i < 0:
            continue
        row = df.iloc[i]
        if row['High'] > resistance_price and row['Close'] < resistance_price:
            # Check if it stayed below in subsequent days
            is_utad = True
            for j in range(i+1, min(i+5, len(df))):
                if df.iloc[j]['Close'] > resistance_price:
                    is_utad = False
                    break
            if is_utad and row['Volume'] > row['VolMA20']:
                result["signals"].append({
                    "date": row['Date'],
                    "label": "UTAD",
                    "price": row['High'],
                    "desc": "Upthrust After Distribution: Bẫy tăng giá nguy hiểm ở vùng đỉnh phân phối. Smart Money lừa nhỏ lẻ mua vào để thoát hàng."
                })
                break

    # Determine Phase
    last_row = df.iloc[-1]
    close = last_row['Close']
    
    # 1. Markup / Phase E: Price is well above resistance and in a clear uptrend (MA20 > MA50 > MA200)
    if close > resistance_price * 1.03 and last_row['MA20'] > last_row['MA50']:
        result["phase"] = "Uptrend (Markup) / Phase E"
        result["phase_desc"] = "Cổ phiếu đã chính thức bứt phá khỏi vùng tích lũy và bước vào giai đoạn đẩy giá mạnh mẽ. Ưu tiên nắm giữ hoặc mua gia tăng tại các nhịp chỉnh."
    # 2. Downtrend / Phase E in Distribution: Price is below support and in a clear downtrend (MA20 < MA50 < MA200)
    elif close < support_price * 0.97 and last_row['MA20'] < last_row['MA50']:
        result["phase"] = "Downtrend (Markdown) / Phase E"
        result["phase_desc"] = "Cổ phiếu đã phá vỡ đường hỗ trợ và đi vào xu hướng đè giá giảm mạnh. Tuyệt đối không bắt đáy, ưu tiên hạ tỷ trọng và đứng ngoài quan sát."
    # 3. Phase D (LPS/BUEC stage): SOS recently detected, price consolidating above or near resistance
    elif any(s['label'] == "SOS" for s in result["signals"]) and close >= resistance_price * 0.97:
        result["phase"] = "Tích lũy lại / Phase D"
        result["phase_desc"] = "Cổ phiếu đang ở giai đoạn hấp thụ lực bán cuối cùng ngay sau phiên bứt phá (SOS). Đây là vùng đệm gom hàng để chuẩn bị cho nhịp tăng chính thức."
    # 4. Phase C (Spring / Testing stage): Spring detected recently
    elif any("Spring" in s['label'] for s in result["signals"]) and close > support_price:
        result["phase"] = "Tạo đáy rũ bỏ / Phase C"
        result["phase_desc"] = "Cổ phiếu vừa trải qua giai đoạn rũ bỏ (Spring/Shakeout) thành công. Lượng cung cạn kiệt, tỷ lệ tạo đáy và bật tăng từ vùng này là rất cao."
    # 5. Phase B (Accumulation): Long sideways range
    else:
        # Check if MA20 and MA50 are flat/intertwined
        result["phase"] = "Tích lũy đi ngang / Phase B"
        result["phase_desc"] = "Cổ phiếu đang trong giai đoạn gom hàng quy mô lớn của Smart Money. Giá biến động trồi sụt quanh biên độ hỗ trợ và kháng cự để rũ bỏ sự kiên nhẫn của nhà đầu tư nhỏ lẻ."

    # Filter out duplicate signals on the same date and sort by date
    unique_signals = {}
    for s in result["signals"]:
        unique_signals[s['date']] = s
    result["signals"] = sorted(list(unique_signals.values()), key=lambda x: x['date'])

    return result

def analyze_relative_strength(stock_df, vnindex_df):
    """
    Analyze relative strength of the stock against VN-Index over the last 20 days.
    Checks if stock is stronger, equal, or weaker.
    """
    rs_info = {"status": "Neutral", "desc": ""}
    
    if stock_df.empty or vnindex_df.empty:
        return rs_info
        
    # Align dates
    merged = pd.merge(stock_df[['Date', 'Close']], vnindex_df[['Date', 'Close']], on='Date', suffixes=('_stock', '_index'))
    if len(merged) < RelativeStrengthWindow:
        return rs_info
        
    recent = merged.tail(RelativeStrengthWindow).copy()
    
    # Calculate returns over past 20 days
    stock_start = recent.iloc[0]['Close_stock']
    stock_end = recent.iloc[-1]['Close_stock']
    stock_ret = (stock_end - stock_start) / stock_start * 100
    
    index_start = recent.iloc[0]['Close_index']
    index_end = recent.iloc[-1]['Close_index']
    index_ret = (index_end - index_start) / index_start * 100
    
    # Ratio analysis (Stock Close / Index Close)
    recent['Ratio'] = recent['Close_stock'] / recent['Close_index']
    ratio_trend = (recent.iloc[-1]['Ratio'] - recent.iloc[0]['Ratio']) / recent.iloc[0]['Ratio'] * 100
    
    if ratio_trend > 1.5:  # Stock outperforming Index by > 1.5%
        rs_info["status"] = "Stronger"
        rs_info["desc"] = f"Mạnh hơn VN-Index. Trong 20 phiên qua, cổ phiếu biến động {stock_ret:+.1f}% trong khi chỉ số chung biến động {index_ret:+.1f}%. Cổ phiếu có xu hướng dẫn dắt dòng tiền."
    elif ratio_trend < -1.5:  # Stock underperforming Index by > 1.5%
        rs_info["status"] = "Weaker"
        rs_info["desc"] = f"Yếu hơn VN-Index. Trong 20 phiên qua, cổ phiếu biến động {stock_ret:+.1f}% trong khi chỉ số chung biến động {index_ret:+.1f}%. Cần thận trọng vì cổ phiếu đang bị rút dòng tiền."
    else:
        rs_info["status"] = "Neutral"
        rs_info["desc"] = f"Đồng pha với VN-Index. Cổ phiếu biến động sát chỉ số chung (cổ phiếu {stock_ret:+.1f}% vs index {index_ret:+.1f}%)."
        
    return rs_info

def generate_wyckoff_recommendations(df, analysis, latest_pattern):
    """
    Generate short-term recommendations for a 1-month holding period based on Wyckoff/VSA.
    Includes entry range, target, SL, R/R ratio, and capital allocation.
    """
    last_row = df.iloc[-1]
    close = float(last_row['Close'])
    support = float(analysis['support'])
    resistance = float(analysis['resistance'])
    phase = analysis['phase']
    
    # Calculate Entry Range and Action based on optimized short-term rules
    if "Downtrend" in phase:
        action = "❌ <b>ĐỨNG NGOÀI (NO TRADE)</b>"
        entry_range = "N/A"
        sl = "N/A"
        target = "N/A"
        rr_ratio = "N/A"
        alloc = "0% (Không phân bổ)"
        desc = "Cổ phiếu trong xu hướng giảm (Markdown). Tuyệt đối không mua ngắn hạn để bảo toàn vốn."
    elif "Uptrend" in phase:
        if latest_pattern in ["Up-thrust", "Pseudo Up-thrust"]:
            action = "⚠️ <b>CHỐT LỜI / GIẢM TỶ TRỌNG</b>"
            entry_range = "N/A"
            sl = "N/A"
            target = "N/A"
            rr_ratio = "N/A"
            alloc = "Canh chốt lời 70-100% vị thế"
            desc = "Xuất hiện bẫy tăng giá Upthrust khi đang trong vùng giá cao. Áp lực bán lớn xuất hiện."
        else:
            action = "⏸️ <b>NẮM GIỮ (HOLD)</b>"
            entry_range = "N/A (Không mua đuổi vùng giá cao)"
            sl = f"{last_row['MA50']:,.0f} VND (Chặn dưới MA50)"
            target = f"{close * 1.10:,.0f} VND"
            rr_ratio = "N/A"
            alloc = "0% mua mới (Nắm giữ vị thế có sẵn)"
            desc = "Cổ phiếu đang đẩy giá mạnh (Phase E). Đã qua điểm mua an toàn, ưu tiên tiếp tục nắm giữ vị thế cũ."
    elif "Tạo đáy" in phase or "Phase C" in phase:
        # Check if Spring is Type 3 (low volume)
        has_type3_spring = any("Type 3" in s['label'] for s in analysis.get('signals', []))
        if has_type3_spring:
            action = "✅ <b>MUA GOM (BUY SPRING TYPE 3)</b>"
            entry_range = f"{support:,.0f} - {support*1.02:,.0f} VND (Sát đường hỗ trợ)"
            sl = f"{support*0.96:,.0f} VND (Dưới đáy Spring 4%)"
            target = f"{resistance:,.0f} VND (Biên trên hộp tích lũy)"
            
            sl_val = support*0.96
            target_val = resistance
            risk = close - sl_val
            reward = target_val - close
            rr_val = reward / risk if risk > 0 else 2.0
            rr_ratio = f"{rr_val:.1f}:1"
            
            alloc = "Mua gom 30% tại hỗ trợ. Chỉ gia tăng khi giá bắt đầu có lãi."
            desc = "Phát hiện tín hiệu Spring Loại 3 (rũ bỏ cạn cung với khối lượng thấp). Xác suất tạo đáy cực cao."
        else:
            action = "⏸️ <b>THEO DÕI TEST SPRING (WATCHLIST)</b>"
            entry_range = "N/A (Chờ phiên test cung cạn kiệt)"
            sl = "N/A"
            target = "N/A"
            rr_ratio = "N/A"
            alloc = "0% (Chờ điểm mua)"
            desc = "Phát hiện rũ bỏ Spring nhưng khối lượng còn lớn. Cần chờ phiên test cung (Secondary Test) cạn kiệt."
    elif "Tích lũy lại" in phase or "Phase D" in phase:
        action = "✅ <b>MUA GIA TĂNG (BUY SOS/LPS)</b>"
        entry_range = f"{resistance:,.0f} - {resistance*1.02:,.0f} VND (Test lại kháng cự cũ)"
        sl = f"{resistance*0.96:,.0f} VND"
        target = f"{resistance*1.15:,.0f} VND (+15% sau breakout)"
        
        sl_val = resistance*0.96
        target_val = resistance*1.15
        risk = close - sl_val
        reward = target_val - close
        rr_val = reward / risk if risk > 0 else 2.0
        rr_ratio = f"{rr_val:.1f}:1"
        
        alloc = "Gom trước 30% tại điểm test. Gia tăng 30% tiếp theo khi giá bứt phá có lãi."
        desc = "Cổ phiếu xác nhận dòng tiền lớn bứt phá kháng cự (SOS). Canh mua gom tại điểm test lại BUEC/LPS."
    else: # Phase B / Sideway
        action = "⏸️ <b>THEO DÕI (WATCHLIST)</b>"
        entry_range = "N/A"
        sl = "N/A"
        target = "N/A"
        rr_ratio = "N/A"
        alloc = "0% (Đứng ngoài)"
        desc = "Cổ phiếu đang dao động tích lũy đi ngang (Phase B) chưa có rũ bỏ Spring hay breakout SOS. Đứng ngoài quan sát."

    rec_text = (
        f"💡 <b>KHUYẾN NGHỊ GIAO DỊCH NGẮN HẠN (DỰ KIẾN NẮM GIỮ: 1 THÁNG)</b>\n\n"
        f"🎯 <b>Hành động:</b> {action}\n"
        f"📝 <b>Đánh giá:</b> <i>{desc}</i>\n\n"
        f"• <b>Vùng giá vào:</b> <code>{entry_range}</code>\n"
        f"• <b>Mục tiêu chốt lời (1 tháng):</b> <code>{target}</code>\n"
        f"• <b>Điểm dừng lỗ (SL):</b> <code>{sl}</code>\n"
        f"• <b>Tỷ lệ Risk/Reward kỳ vọng:</b> <b>{rr_ratio}</b>\n"
        f"• <b>Phân bổ vốn (Wyckoff Scaled):</b> <b>{alloc}</b>\n"
    )
    return rec_text

def run_single_stock_backtest(df, symbol):
    """
    Run a single-stock backtest over the history provided in df (typically past 252 trading days)
    using the optimized Wyckoff strategy rules.
    """
    if len(df) < 50:
        return None
        
    initial_capital = 100000000.0  # 100M VND
    capital = initial_capital
    position = 0  # 0 or 1
    entry_price = 0.0
    size_shares = 0
    sl_price = 0.0
    days_held = 0
    setup_type = ""
    entry_date = None
    
    trades = [] # List of closed trades
    
    # Simulate day-by-day. i starting from 40 to have enough history for indicators
    for i in range(40, len(df)):
        row = df.iloc[i]
        current_date = row['Date']
        close = row['Close']
        low = row['Low']
        
        # Check active position
        if position == 1:
            days_held += 1
            
            # Check Stop Loss
            if low <= sl_price:
                exit_price = min(sl_price, row['Open'])
                pnl_pct = (exit_price - entry_price) / entry_price * 100
                pnl_vnd = (exit_price - entry_price) * size_shares
                capital += entry_price * size_shares + pnl_vnd
                
                trades.append({
                    "entry_date": entry_date,
                    "exit_date": current_date,
                    "entry_price": entry_price,
                    "exit_price": exit_price,
                    "pnl_pct": pnl_pct,
                    "setup_type": setup_type,
                    "exit_reason": "Stop Loss"
                })
                position = 0
                size_shares = 0
                continue
                
            # Check 1-month time exit (21 trading days)
            if days_held >= 21:
                exit_price = close
                pnl_pct = (exit_price - entry_price) / entry_price * 100
                pnl_vnd = (exit_price - entry_price) * size_shares
                capital += entry_price * size_shares + pnl_vnd
                
                trades.append({
                    "entry_date": entry_date,
                    "exit_date": current_date,
                    "entry_price": entry_price,
                    "exit_price": exit_price,
                    "pnl_pct": pnl_pct,
                    "setup_type": setup_type,
                    "exit_reason": "Time Exit (1M)"
                })
                position = 0
                size_shares = 0
                continue
                
        # Look for entry if no active position
        if position == 0:
            subset = df.iloc[:i+1]
            last_row = subset.iloc[-1]
            
            # Calculate support and resistance based on rolling bounds
            ref_df = subset.tail(40).iloc[:-5]
            if ref_df.empty:
                ref_df = subset
            support = float(ref_df['Low'].min())
            resistance = float(ref_df['High'].max())
            
            trigger_type = None
            
            # Setup 1: Spring Type 3 (Price dips below support, closes back above, AND volume is LOW)
            if last_row['Low'] < support and close > support and last_row['Volume'] < last_row['VolMA20']:
                trigger_type = "Spring Type 3"
            # Setup 2: SOS Breakout (Price breaks resistance on high volume)
            elif close > resistance and last_row['Volume'] > last_row['VolMA20'] * 1.2:
                trigger_type = "SOS Breakout"
                
            if trigger_type:
                entry_price = close
                setup_type = trigger_type
                entry_date = current_date
                
                if "Spring" in setup_type:
                    sl_price = support * 0.96
                else: # SOS Breakout
                    sl_price = entry_price * 0.95
                    
                size_shares = int(capital / entry_price)
                if size_shares > 0:
                    capital -= size_shares * entry_price
                    position = 1
                    days_held = 0
                    
    # Close open position at final date
    if position == 1:
        last_row = df.iloc[-1]
        exit_price = last_row['Close']
        pnl_pct = (exit_price - entry_price) / entry_price * 100
        pnl_vnd = (exit_price - entry_price) * size_shares
        capital += entry_price * size_shares + pnl_vnd
        trades.append({
            "entry_date": entry_date,
            "exit_date": last_row['Date'],
            "entry_price": entry_price,
            "exit_price": exit_price,
            "pnl_pct": pnl_pct,
            "setup_type": setup_type,
            "exit_reason": "Still Open"
        })
        
    net_profit = capital - initial_capital
    roi = (capital - initial_capital) / initial_capital * 100
    
    return {
        "initial_capital": initial_capital,
        "final_capital": capital,
        "net_profit": net_profit,
        "roi": roi,
        "trades": trades
    }
