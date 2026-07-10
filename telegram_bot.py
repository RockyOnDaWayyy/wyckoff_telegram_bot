import logging
import datetime
import asyncio
import json
import os
from pathlib import Path
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
import pandas as pd

import config
import data_fetcher
import wyckoff_analyzer
import chart_generator

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

CACHE_FILE = config.TEMP_DIR / "scan_cache.json"

is_scanning = False

def save_cache(data):
    try:
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logger.error(f"Error saving cache: {e}")

def load_cache():
    if not CACHE_FILE.exists():
        return None
    try:
        with open(CACHE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading cache: {e}")
        return None

async def safe_reply_text(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, parse_mode: str = 'HTML'):
    """Safe helper to send a text reply, falling back to direct send_message if the user's message is deleted."""
    try:
        if update.message:
            return await update.message.reply_text(text, parse_mode=parse_mode)
    except Exception as e:
        logger.warning(f"Failed to reply_text: {e}. Falling back to direct send_message.")
    return await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=text,
        parse_mode=parse_mode
    )

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for the /start command."""
    welcome_text = (
        "<b>Chào mừng bạn đến với Wyckoff Stock Bot!</b> 📈\n\n"
        "Tôi là Bot phân tích và khuyến nghị cổ phiếu chuyên sâu theo <b>Phương pháp Wyckoff</b> và <b>VSA (Volume Spread Analysis)</b>.\n\n"
        "<b>Các tính năng chính:</b>\n"
        "• Phân tích cấu trúc pha Wyckoff & tín hiệu VSA\n"
        "• Tính toán chỉ số định lượng nâng cao (VaR, MDD)\n"
        "• Vẽ biểu đồ nến chuyên nghiệp và gắn nhãn tự động\n"
        "• Quét thị trường lọc các cơ hội mua gom tốt nhất sàn HOSE\n\n"
        "<b>Danh sách lệnh:</b>\n"
        "👉 /analyze &lt;Mã_Cổ_Phiếu&gt; - Phân tích chi tiết một cổ phiếu (ví dụ: <code>/analyze HPG</code>)\n"
        "👉 /backtest &lt;Mã_Cổ_Phiếu&gt; - Chạy backtest mô phỏng 1 năm qua trên cổ phiếu (ví dụ: <code>/backtest HPG</code>)\n"
        "👉 /scan - Xem danh sách khuyến nghị mua mới nhất từ phiên giao dịch trước\n"
        "👉 /help - Hướng dẫn chi tiết cách đọc hiểu các tín hiệu\n\n"
        "<i>Bot được lập lịch tự động gửi 1-5 mã khuyến nghị tốt nhất vào 9h00 sáng mỗi ngày giao dịch (Thứ 2 - Thứ 6) qua kênh phân tích.</i>"
    )
    await safe_reply_text(update, context, welcome_text)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for the /help command to explain Wyckoff/VSA concepts."""
    help_text = (
        "<b>💡 HƯỚNG DẪN ĐỌC HIỂU TÍN HIỆU WYCKOFF & VSA</b>\n\n"
        "<b>1. Các Pha Wyckoff Chính:</b>\n"
        "• <b>Phase A:</b> Giai đoạn dừng xu hướng giảm trước đó. Xuất hiện SCLX (Bán hoảng loạn) và AR (Hồi phục tự nhiên).\n"
        "• <b>Phase B:</b> Giai đoạn Smart Money gom hàng trong biên độ. Giá đi ngang biến động trồi sụt.\n"
        "• <b>Phase C:</b> Giai đoạn kiểm thử cung/cầu. Xuất hiện <b>Spring (Rũ bỏ)</b> bẫy gấu để loại bỏ các nhà đầu tư yếu trước khi kéo giá.\n"
        "• <b>Phase D:</b> Giai đoạn bứt phá trong biên độ. Xuất hiện các nhịp tăng mạnh SOS và các nhịp chỉnh cạn cung LPS/BUEC.\n"
        "• <b>Phase E:</b> Giai đoạn đẩy giá chính thức (Uptrend/Markup) nằm ngoài biên tích lũy.\n\n"
        "<b>2. Các Thuật Ngữ VSA Thường Gặp:</b>\n"
        "• <b>Spring:</b> Rũ bỏ thành công. Giá giảm thủng hỗ trợ rồi hồi phục đóng cửa trên hỗ trợ.\n"
        "• <b>SOS (Sign of Strength):</b> Phiên tăng giá mạnh mẽ với khối lượng lớn thể hiện dòng tiền lớn quyết liệt.\n"
        "• <b>LPS (Last Point of Support):</b> Điểm điều chỉnh cạn cung với khối lượng thấp trên đường tăng.\n"
        "• <b>Stopping Volume:</b> Phiên giảm mạnh nhưng đóng cửa rút chân với khối lượng cực lớn, Smart Money gom hàng đỡ giá.\n"
        "• <b>No Demand:</b> Phiên tăng giá yếu với khối lượng thấp, cho thấy dòng tiền lớn chưa sẵn sàng kéo giá tiếp."
    )
    await safe_reply_text(update, context, help_text)

async def analyze_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /analyze <ticker>."""
    if not context.args:
        await safe_reply_text(update, context, "Vui lòng nhập mã cổ phiếu cần phân tích. Ví dụ: <code>/analyze HPG</code>")
        return

    symbol = context.args[0].upper().strip()
    status_msg = await safe_reply_text(update, context, f"🔄 Đang tải dữ liệu và phân tích mã <b>{symbol}</b>. Vui lòng đợi...")

    try:
        # Fetch stock data
        stock_df = data_fetcher.get_historical_data(symbol)
        if stock_df.empty:
            await status_msg.edit_text(f"❌ Không tìm thấy dữ liệu lịch sử cho mã <b>{symbol}</b>. Vui lòng kiểm tra lại mã niêm yết trên HOSE.", parse_mode='HTML')
            return

        # Fetch VNINDEX data for relative strength comparison
        vnindex_df = data_fetcher.get_historical_data("VNINDEX")

        # Process Indicators
        stock_df = wyckoff_analyzer.calculate_indicators(stock_df)
        if not vnindex_df.empty:
            vnindex_df = wyckoff_analyzer.calculate_indicators(vnindex_df)

        # Run Wyckoff Analysis
        analysis = wyckoff_analyzer.detect_wyckoff_structure(stock_df)
        
        # VSA classification for the latest candle
        latest_pattern = None
        latest_desc = "Không phát hiện mẫu hình VSA đặc biệt nào trong phiên gần nhất."
        if len(stock_df) >= 3:
            row = stock_df.iloc[-1]
            prev_row = stock_df.iloc[-2]
            prev_row2 = stock_df.iloc[-3]
            pat, desc = wyckoff_analyzer.detect_vsa_bar(row, prev_row, prev_row2)
            if pat:
                latest_pattern = pat
                latest_desc = desc

        # Relative Strength
        rs_info = wyckoff_analyzer.analyze_relative_strength(stock_df, vnindex_df)

        # Quantitative metrics
        quant = wyckoff_analyzer.calculate_quant_metrics(stock_df)

        # Generate Chart
        chart_path = chart_generator.plot_wyckoff_chart(stock_df, analysis, symbol)

        # Format Text Report
        last_row = stock_df.iloc[-1]
        close_price = last_row['Close']
        pct_change = last_row['Return'] * 100
        
        report = (
            f"📊 <b>{symbol}</b>\n"
            f"📅 Ngày giao dịch gần nhất: {last_row['Date'].strftime('%d/%m/%Y')}\n"
            f"💵 Giá đóng cửa: <b>{close_price:,.0f} VND</b> ({pct_change:+.2f}%)\n\n"
            f"🔹 <b>Trạng thái & Pha Wyckoff:</b>\n"
            f"→ <b>{analysis['phase']}</b>\n"
            f"<i>{analysis['phase_desc']}</i>\n\n"
            f"🔹 <b>Biên độ dao động (Trading Range):</b>\n"
            f"• Kháng cự: <b>{analysis['resistance']:,.0f} VND</b>\n"
            f"• Hỗ trợ: <b>{analysis['support']:,.0f} VND</b>\n\n"
            f"🔹 <b>Tín hiệu VSA phiên gần nhất:</b>\n"
            f"→ <b>{latest_pattern if latest_pattern else 'Bình thường'}</b>\n"
            f"<i>{latest_desc}</i>\n\n"
            f"🔹 <b>Sức mạnh tương đối (vs VN-Index):</b>\n"
            f"→ <b>{rs_info['status']}</b>\n"
            f"<i>{rs_info['desc']}</i>\n\n"
            f"🔹 <b>Chỉ số định lượng (Quant - Mô phỏng 1 tháng):</b>\n"
            f"• Tỉ lệ thắng (Win Rate): <b>{quant['win_rate']:.1f}%</b>\n"
            f"• Hiệu suất %ROI trung bình: <b>{quant['avg_roi']:+.1f}%</b>\n"
            f"• Tỷ lệ Risk/Reward thực tế: <b>{quant['rr_ratio']:.1f}:1</b>\n"
            f"• Rủi ro VaR 95% (1 tháng): <b>{quant['var_95']:.1f}%</b>\n"
            f"• Sụt giảm tối đa 1 năm (MDD): <b>{quant['mdd']:.1f}%</b>\n\n"
        )

        # Generate detailed Wyckoff recommendations
        report += wyckoff_analyzer.generate_wyckoff_recommendations(stock_df, analysis, latest_pattern)

        # Send photo and caption
        if chart_path and os.path.exists(chart_path):
            # Send the chart photo with a short caption
            await context.bot.send_photo(
                chat_id=update.effective_chat.id,
                photo=open(chart_path, 'rb'),
                caption=f"<b>Biểu đồ phân tích {symbol}</b>",
                parse_mode='HTML'
            )
            # Send the detailed report as a text message
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=report,
                parse_mode='HTML'
            )
            # Remove temp file
            try:
                os.remove(chart_path)
            except Exception:
                pass
        else:
            await safe_reply_text(update, context, report)

        await status_msg.delete()

    except Exception as e:
        logger.error(f"Error analyzing symbol {symbol}: {e}", exc_info=True)
        await status_msg.edit_text(f"❌ Có lỗi xảy ra trong quá trình phân tích mã <b>{symbol}</b>. Lỗi: {str(e)}", parse_mode='HTML')

async def execute_market_scan_and_notify(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    """Run a full market scan in the background and notify the chat when completed."""
    global is_scanning
    if is_scanning:
        logger.info("Scan already running. Skip.")
        return
        
    is_scanning = True
    try:
        # Run the full market scan (all HOSE stocks)
        cache = await execute_market_scan()
        if cache:
            date_str = cache.get("date", "")
            recs = cache.get("recommendations", [])
            
            if not recs:
                msg = (
                    f"🔍 <b>KẾT QUẢ QUÉT THỊ TRƯỜNG HOSE ({date_str})</b>\n\n"
                    "Không tìm thấy cổ phiếu nào đạt tiêu chuẩn mua Wyckoff (Pha C/D khỏe, nến test cung cạn kiệt)."
                )
            else:
                msg = f"🔍 <b>KẾT QUẢ QUÉT THỊ TRƯỜNG HOSE ({date_str})</b>\n"
                msg += f"<i>(Dữ liệu phân tích lúc 15h00 phiên giao dịch trước đó)</i>\n\n"
                msg += f"Dưới đây là <b>{len(recs)} mã cổ phiếu đạt tiêu chuẩn mua tốt nhất</b>:\n\n"
                
                for i, rec in enumerate(recs, 1):
                    msg += (
                        f"<b>{i}. Cổ phiếu {rec['symbol']}</b>\n"
                        f"• Giá đóng cửa: <b>{rec['price']:,.0f} VND</b>\n"
                        f"• Giai đoạn Wyckoff: <b>{rec['phase']}</b>\n"
                        f"• Sức mạnh tương đối: <b>{rec['rs_status']}</b>\n"
                        f"• Tín hiệu: <i>{rec['desc']}</i>\n"
                        f"🔍 Chi tiết: <code>/analyze {rec['symbol']}</code>\n\n"
                    )
                msg += "💡 <i>Lưu ý: Bạn nên sử dụng lệnh /analyze chi tiết trên từng mã để xem biểu đồ kỹ thuật và các chỉ số định lượng VaR/MDD trước khi giao dịch.</i>"
                
            await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode='HTML')
            
            # If this notification was sent to the daily alert channel, update last_alert_sent
            if str(chat_id) == str(config.TELEGRAM_CHAT_ID):
                today_str = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=7))).strftime("%Y-%m-%d")
                cache["last_alert_sent"] = today_str
                save_cache(cache)
        else:
            await context.bot.send_message(chat_id=chat_id, text="❌ Có lỗi xảy ra trong quá trình quét toàn bộ thị trường sàn HOSE.")
    except Exception as e:
        logger.error(f"Error in execute_market_scan_and_notify: {e}")
    finally:
        is_scanning = False

async def scan_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for the /scan command to display the latest cached recommendations."""
    global is_scanning
    cache = load_cache()
    if not cache:
        if is_scanning:
            await safe_reply_text(
                update, context,
                "🔄 Tiến trình quét toàn bộ sàn HOSE hiện đang được chạy trong nền. Kết quả sẽ tự động gửi vào nhóm ngay khi hoàn thành (khoảng 2-3 phút)."
            )
            return
            
        await safe_reply_text(
            update, context, 
            "🔄 Chưa có dữ liệu quét trong bộ nhớ đệm (do máy chủ vừa khởi động lại).\n"
            "Đang kích hoạt quét toàn bộ sàn HOSE (400+ mã) trong nền. Quá trình này mất khoảng 2-3 phút. Kết quả sẽ tự động gửi vào nhóm ngay khi hoàn tất!"
        )
        # Start background scan task
        asyncio.create_task(execute_market_scan_and_notify(update.effective_chat.id, context))
        return
        
    date_str = cache.get("date", "")
    recs = cache.get("recommendations", [])
    
    if not recs:
        await update.message.reply_text(
            f"🔍 <b>KẾT QUẢ QUÉT THỊ TRƯỜNG HOSE ({date_str})</b>\n\n"
            "Không tìm thấy cổ phiếu nào đạt tiêu chuẩn mua (Pha C/D khỏe, nến test cung cạn kiệt).",
            parse_mode='HTML'
        )
        return
        
    msg = f"🔍 <b>KẾT QUẢ QUÉT THỊ TRƯỜNG HOSE ({date_str})</b>\n"
    msg += f"<i>(Dữ liệu phân tích lúc 15h00 phiên giao dịch trước đó)</i>\n\n"
    msg += f"Dưới đây là <b>{len(recs)} mã cổ phiếu đạt tiêu chuẩn mua tốt nhất</b>:\n\n"
    
    for i, rec in enumerate(recs, 1):
        msg += (
            f"<b>{i}. Cổ phiếu {rec['symbol']}</b>\n"
            f"• Giá đóng cửa: <b>{rec['price']:,.0f} VND</b>\n"
            f"• Giai đoạn: <b>{rec['phase']}</b>\n"
            f"• Sức mạnh tương đối: <b>{rec['rs_status']}</b>\n"
            f"• Tín hiệu: <i>{rec['desc']}</i>\n"
            f"🔍 Chi tiết: <code>/analyze {rec['symbol']}</code>\n\n"
        )
        
    msg += "💡 <i>Lưu ý: Bạn nên sử dụng lệnh /analyze chi tiết trên từng mã để xem biểu đồ kỹ thuật và các chỉ số định lượng VaR/MDD trước khi giao dịch.</i>"
    await safe_reply_text(update, context, msg)

async def execute_market_scan(tickers_list=None):
    """
    Helper function to run a market scan over a list of tickers.
    If tickers_list is None, loads all HOSE tickers.
    """
    logger.info("Starting market scan execution...")
    try:
        if tickers_list is None:
            tickers = data_fetcher.get_hose_tickers()
        else:
            tickers = tickers_list
            
        logger.info(f"Loaded {len(tickers)} tickers for scanning.")
        
        # Get VNINDEX for comparison
        vnindex_df = data_fetcher.get_historical_data("VNINDEX")
        if not vnindex_df.empty:
            vnindex_df = wyckoff_analyzer.calculate_indicators(vnindex_df)
            
        candidates = []
        
        # Get scan date from last trading date of HPG
        ref_df = data_fetcher.get_historical_data("HPG")
        if not ref_df.empty:
            scan_date = ref_df.iloc[-1]['Date'].strftime("%d/%m/%Y")
        else:
            scan_date = datetime.date.today().strftime("%d/%m/%Y")
            
        # Scan each ticker
        count = 0
        for symbol in tickers:
            count += 1
            if count % 20 == 0:
                logger.info(f"Scanning progress: {count}/{len(tickers)}...")
                
            await asyncio.sleep(0.05)
            
            try:
                df = data_fetcher.get_historical_data(symbol)
                if df.empty or len(df) < 50:
                    continue
                    
                # Exclude penny stocks
                vol_ma = df['Volume'].rolling(20).mean().iloc[-1] if 'Volume' in df.columns else 0
                if vol_ma < 20000:
                    continue
                    
                df = wyckoff_analyzer.calculate_indicators(df)
                analysis = wyckoff_analyzer.detect_wyckoff_structure(df)
                
                phase = analysis["phase"]
                signals = analysis["signals"]
                
                latest_vsa = None
                if len(df) >= 3:
                    latest_vsa, _ = wyckoff_analyzer.detect_vsa_bar(df.iloc[-1], df.iloc[-2], df.iloc[-3])
                
                # Check for buy signals in last 5 days
                has_recent_buy_signal = False
                recent_desc = ""
                for sig in reversed(signals):
                    sig_date = pd.to_datetime(sig['date'])
                    days_diff = (pd.to_datetime(df.iloc[-1]['Date']) - sig_date).days
                    if days_diff <= 7:
                        if "Spring" in sig['label'] or sig['label'] in ["SOS", "LPS / BUEC"]:
                            has_recent_buy_signal = True
                            recent_desc = sig['desc']
                            break
                            
                rs_info = wyckoff_analyzer.analyze_relative_strength(df, vnindex_df)
                
                if "Downtrend" in phase:
                    continue
                    
                is_candidate = False
                reason = ""
                
                if has_recent_buy_signal:
                    is_candidate = True
                    reason = recent_desc
                elif "Tạo đáy" in phase or "Phase D" in phase:
                    is_candidate = True
                    reason = f"Cổ phiếu đang tích lũy tốt ở {phase} và giữ được sức mạnh."
                elif latest_vsa in ["Test", "Lack of Offer", "Stopping Volume"]:
                    is_candidate = True
                    reason = f"Xuất hiện tín hiệu VSA tích cực: {latest_vsa} (Kiểm thử cạn cung/Cầu đỡ)."
                    
                if is_candidate and rs_info["status"] in ["Stronger", "Neutral"]:
                    score = 0
                    if rs_info["status"] == "Stronger":
                        score += 3
                    if "Spring" in reason or "rũ bỏ" in reason.lower():
                        score += 5
                    if "SOS" in reason or "bứt phá" in reason.lower():
                        score += 4
                    if latest_vsa == "Test":
                        score += 2
                        
                    candidates.append({
                        "symbol": symbol,
                        "price": float(df.iloc[-1]['Close']),
                        "phase": phase,
                        "rs_status": rs_info["status"],
                        "desc": reason,
                        "score": score
                    })
            except Exception as e:
                logger.error(f"Error scanning {symbol} during scan: {e}")
                
        # Sort candidates and keep top 5
        candidates = sorted(candidates, key=lambda x: x['score'], reverse=True)
        top_recs = candidates[:5]
        
        # Save to cache
        cache_data = {
            "date": scan_date,
            "recommendations": top_recs
        }
        save_cache(cache_data)
        logger.info(f"Market scan completed successfully. Saved {len(top_recs)} recommendations.")
        return cache_data
        
    except Exception as e:
        logger.error(f"Error in execute_market_scan: {e}", exc_info=True)
        return None

async def run_market_scan_job(context: ContextTypes.DEFAULT_TYPE):
    """
    Background job scheduled at 15:00.
    Scans all HOSE stocks and keeps the top 1-5 recommendations.
    """
    logger.info("Starting background market scan job...")
    await execute_market_scan()

async def send_daily_alert_job(context: ContextTypes.DEFAULT_TYPE):
    """
    Background job scheduled at 09:00 (Monday to Friday).
    Reads the cached recommendations and sends them to the configured Telegram Chat ID.
    """
    logger.info("Running daily alert sending job...")
    global is_scanning
    cache = load_cache()
    chat_id = config.TELEGRAM_CHAT_ID
    
    if not cache:
        if is_scanning:
            logger.info("Scan is already running. The alert will be sent by the scan task.")
            return
            
        logger.warning("No market scan cache found. Running full scan in background for daily alert...")
        await context.bot.send_message(
            chat_id=chat_id, 
            text="🔔 <b>THÔNG BÁO KHUYẾN NGHỊ PHIÊN SÁNG</b>\n\n"
                 "Bộ nhớ đệm bị trống (do máy chủ vừa khởi động lại). Bot đang tiến hành quét toàn bộ sàn HOSE trong nền. Kết quả sẽ được gửi sau 2-3 phút..."
        )
        asyncio.create_task(execute_market_scan_and_notify(chat_id, context))
        return
        
    date_str = cache.get("date", "")
    recs = cache.get("recommendations", [])
    chat_id = config.TELEGRAM_CHAT_ID
    
    if not recs:
        alert_text = (
            f"🔔 <b>THÔNG BÁO KHUYẾN NGHỊ PHIÊN SÁNG ({date_str})</b>\n\n"
            "Hệ thống quét sàn HOSE phiên chiều hôm qua không phát hiện mã nào đạt chuẩn mua an toàn theo Wyckoff & VSA.\n"
            "Ưu tiên giữ tỷ trọng an toàn và theo dõi thị trường chung."
        )
        await context.bot.send_message(chat_id=chat_id, text=alert_text, parse_mode='HTML')
        return
        
    alert_text = (
        f"🔔 <b>KHUYẾN NGHỊ CỔ PHIẾU ({date_str})</b>\n"
        f"<i>(Dữ liệu quét thị trường tự động lúc 15h00 phiên giao dịch hôm qua)</i>\n\n"
        f"Dưới đây là <b>{len(recs)} mã cổ phiếu tiềm năng mua gom tốt nhất</b>:\n\n"
    )
    
    for i, rec in enumerate(recs, 1):
        alert_text += (
            f"<b>{i}. Cổ phiếu {rec['symbol']}</b>\n"
            f"• Giá đóng cửa: <b>{rec['price']:,.0f} VND</b>\n"
            f"• Trạng thái Wyckoff: <b>{rec['phase']}</b>\n"
            f"• Sức mạnh tương đối: <b>{rec['rs_status']}</b>\n"
            f"• Tín hiệu: <i>{rec['desc']}</i>\n"
            f"🔍 Chi tiết: /analyze_{rec['symbol']}\n\n"
        )
        
    alert_text += (
        "💡 <i>Gợi ý: Quý nhà đầu tư có thể gõ lệnh /analyze &lt;Mã_Cổ_Phiếu&gt; trực tiếp trên bot để xem biểu đồ kỹ thuật và tính toán chỉ số rủi ro VaR/MDD chi tiết.</i>"
    )
    
    try:
        await context.bot.send_message(chat_id=chat_id, text=alert_text, parse_mode='HTML')
        logger.info("Daily alert sent successfully.")
        
        # Update last_alert_sent in cache
        today_str = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=7))).strftime("%Y-%m-%d")
        cache = load_cache()
        if cache:
            cache["last_alert_sent"] = today_str
            save_cache(cache)
    except Exception as e:
        logger.error(f"Error sending daily alert to chat {chat_id}: {e}")

async def run_startup_alert_check(application):
    """
    On startup, checks if it is after 09:00 VN time on a weekday,
    and if the daily alert for today hasn't been sent yet.
    If so, sends the alert immediately.
    """
    await asyncio.sleep(5)  # Wait 5 seconds for bot to initialize fully
    
    # Get current time in VN timezone (UTC+7)
    vn_tz = datetime.timezone(datetime.timedelta(hours=7))
    now = datetime.datetime.now(vn_tz)
    
    # Check if weekday (0=Monday, ..., 4=Friday)
    if now.weekday() > 4:
        logger.info("Startup check: Today is weekend. No alert needed.")
        return
        
    # Check if it is after 9:00 AM VN Time
    if now.hour < 9:
        logger.info(f"Startup check: It is currently {now.strftime('%H:%M')} VN Time (before 09:00). Waiting for scheduled job.")
        return
        
    # Check if already sent today
    cache = load_cache()
    today_str = now.strftime("%Y-%m-%d")
    
    if cache and cache.get("last_alert_sent") == today_str:
        logger.info("Startup check: Alert has already been sent today.")
        return
        
    logger.info("Startup check: Daily alert has not been sent today. Sending now...")
    
    # Create a mock Context to pass to send_daily_alert_job
    class MockContext:
        def __init__(self, bot):
            self.bot = bot
            
    context = MockContext(application.bot)
    await send_daily_alert_job(context)

async def post_init_hook(application) -> None:
    """
    Post-initialization hook called after the event loop starts.
    """
    asyncio.create_task(run_startup_alert_check(application))

async def analyze_shortcut_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for shortcut command links like /analyze_HPG."""
    text = update.message.text
    if text.startswith('/analyze_'):
        symbol = text.replace('/analyze_', '').upper().strip()
        context.args = [symbol]
        await analyze_command(update, context)

async def backtest_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for the /backtest <ticker> command."""
    if not context.args:
        await safe_reply_text(update, context, "Vui lòng nhập mã cổ phiếu để backtest. Ví dụ: <code>/backtest HPG</code>")
        return
        
    symbol = context.args[0].upper().strip()
    status_msg = await safe_reply_text(update, context, f"🔄 Đang tải dữ liệu lịch sử và chạy backtest cho mã <b>{symbol}</b> (252 phiên)...")
    
    try:
        # Fetch stock data
        stock_df = data_fetcher.get_historical_data(symbol)
        if stock_df.empty or len(stock_df) < 50:
            await status_msg.edit_text(f"❌ Không đủ dữ liệu lịch sử để backtest mã <b>{symbol}</b>. Yêu cầu tối thiểu 50 phiên.", parse_mode='HTML')
            return
            
        # Process Indicators
        stock_df = wyckoff_analyzer.calculate_indicators(stock_df)
        
        # Keep only the last 252 trading days for backtesting (1 year)
        # But we need some buffer before that for indicator calculations (total e.g. 300 rows)
        test_df = stock_df.tail(292) # 252 days + 40 days buffer
        
        # Run Backtest
        res = wyckoff_analyzer.run_single_stock_backtest(test_df, symbol)
        if not res:
            await status_msg.edit_text(f"❌ Có lỗi xảy ra trong quá trình backtest mã <b>{symbol}</b>.", parse_mode='HTML')
            return
            
        trades = res["trades"]
        win_trades = [t for t in trades if t["pnl_pct"] > 0]
        loss_trades = [t for t in trades if t["pnl_pct"] <= 0]
        
        win_rate = len(win_trades) / len(trades) * 100 if trades else 0.0
        avg_win_pct = sum(t["pnl_pct"] for t in win_trades) / len(win_trades) if win_trades else 0.0
        avg_loss_pct = sum(t["pnl_pct"] for t in loss_trades) / len(loss_trades) if loss_trades else 0.0
        rr_ratio = avg_win_pct / abs(avg_loss_pct) if avg_loss_pct != 0 else 2.0
        
        # Format Report
        report = (
            f"📊 <b>KẾT QUẢ BACKTEST WYCKOFF - MÃ {symbol}</b>\n"
            f"<i>(Mô phỏng 1 năm gần nhất, nắm giữ tối đa 1 tháng)</i>\n\n"
            f"💰 <b>Vốn giả định ban đầu</b>: <code>100,000,000 VND</code>\n"
            f"💰 <b>Vốn cuối kỳ</b>: <b>{res['final_capital']:,.0f} VND</b>\n"
            f"📈 <b>Lợi nhuận ròng</b>: <b>{res['net_profit']:+,.0f} VND</b>\n"
            f"🚀 <b>Tỷ suất lợi nhuận (ROI)</b>: <b>{res['roi']:+.2f}%</b>\n\n"
            f"🔹 <b>Thông số chi tiết</b>:\n"
            f"• Tổng số lệnh giao dịch: <b>{len(trades)} lệnh</b>\n"
            f"• Số lệnh thắng/thua: <b>{len(win_trades)} thắng / {len(loss_trades)} thua</b>\n"
            f"• Tỉ lệ thắng (Win Rate): <b>{win_rate:.1f}%</b>\n"
            f"• Lãi TB lệnh thắng: <b>{avg_win_pct:+.2f}%</b>\n"
            f"• Lỗ TB lệnh thua: <b>{avg_loss_pct:+.2f}%</b>\n"
            f"• Tỷ lệ Risk/Reward thực tế: <b>{rr_ratio:.2f}:1</b>\n\n"
        )
        
        # Add summary of trades by setup type
        if trades:
            report += "🔹 <b>Hiệu quả theo thiết lập (Setup)</b>:\n"
            setups = {}
            for t in trades:
                s = t["setup_type"]
                setups[s] = setups.get(s, []) + [t["pnl_pct"]]
                
            for s, pnls in setups.items():
                s_wins = [p for p in pnls if p > 0]
                s_win_rate = len(s_wins) / len(pnls) * 100
                s_avg = sum(pnls) / len(pnls)
                report += f"• <b>{s}</b>: {len(pnls)} lệnh | Thắng: {s_win_rate:.1f}% | ROI TB: {s_avg:+.2f}%\n"
                
            report += "\n📝 <i>Lưu ý: Kết quả backtest dựa trên dữ liệu quá khứ và không đảm bảo lợi nhuận trong tương lai.</i>"
        else:
            report += "❌ Không phát hiện điểm mua nào đạt tiêu chuẩn Wyckoff trong 1 năm qua."
            
        await status_msg.edit_text(report, parse_mode='HTML')
        
    except Exception as e:
        logger.error(f"Error in backtest command for {symbol}: {e}", exc_info=True)
        await status_msg.edit_text(f"❌ Có lỗi xảy ra khi chạy backtest mã <b>{symbol}</b>. Lỗi: {e}", parse_mode='HTML')

async def backtest_shortcut_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for shortcut command links like /backtest_HPG."""
    text = update.message.text
    if text.startswith('/backtest_'):
        symbol = text.replace('/backtest_', '').upper().strip()
        context.args = [symbol]
        await backtest_command(update, context)
