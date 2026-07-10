import datetime
import logging
import os
import http.server
import socketserver
import threading
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters

import config
import telegram_bot

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class HealthCheckHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"OK")
        
    def log_message(self, format, *args):
        pass

def run_dummy_server():
    port = int(os.environ.get("PORT", 8080))
    try:
        with socketserver.TCPServer(("", port), HealthCheckHandler) as httpd:
            logger.info(f"Starting dummy health check server on port {port}")
            httpd.serve_forever()
    except Exception as e:
        logger.error(f"Error starting health check server: {e}")

def main():
    """Start the telegram bot."""
    # Start the dummy HTTP server in a daemon thread to bind to PORT for Render health check
    threading.Thread(target=run_dummy_server, daemon=True).start()
    
    token = config.TELEGRAM_BOT_TOKEN
    if not token or ":" not in token:
        logger.error("Invalid TELEGRAM_BOT_TOKEN in configuration. Please check your .env file.")
        return
        
    logger.info("Initializing Wyckoff Telegram Bot...")
    
    # Build Telegram Bot application with post_init hook
    application = ApplicationBuilder().token(token).post_init(telegram_bot.post_init_hook).build()
    
    # Register command handlers
    application.add_handler(CommandHandler("start", telegram_bot.start_command))
    application.add_handler(CommandHandler("help", telegram_bot.help_command))
    application.add_handler(CommandHandler("analyze", telegram_bot.analyze_command))
    application.add_handler(CommandHandler("scan", telegram_bot.scan_command))
    application.add_handler(CommandHandler("backtest", telegram_bot.backtest_command))
    
    # Register regex handler for shortcut links (like /analyze_HPG)
    application.add_handler(MessageHandler(
        filters.Regex(r'^/analyze_[a-zA-Z0-9]+$'), 
        telegram_bot.analyze_shortcut_handler
    ))
    # Register regex handler for backtest shortcut links (like /backtest_HPG)
    application.add_handler(MessageHandler(
        filters.Regex(r'^/backtest_[a-zA-Z0-9]+$'), 
        telegram_bot.backtest_shortcut_handler
    ))
    
    # Configure JobQueue scheduling (Monday to Friday, VN Time UTC+7 -> scheduled in UTC)
    jq = application.job_queue
    if jq:
        # Convert VN Time to UTC to prevent JobQueue timezone conversion bugs on Render:
        # 15:00 VN Time = 08:00 UTC
        # 09:00 VN Time = 02:00 UTC
        scan_time = datetime.time(hour=8, minute=0, second=0, tzinfo=datetime.timezone.utc)
        jq.run_daily(
            telegram_bot.run_market_scan_job, 
            time=scan_time, 
            days=(0, 1, 2, 3, 4),
            name="market_scan_job"
        )
        logger.info("Scheduled Market Scan Job at 08:00 UTC (15:00 VN Time) (Mon-Fri)")
        
        alert_time = datetime.time(hour=2, minute=0, second=0, tzinfo=datetime.timezone.utc)
        jq.run_daily(
            telegram_bot.send_daily_alert_job, 
            time=alert_time, 
            days=(0, 1, 2, 3, 4),
            name="daily_alert_job"
        )
        logger.info("Scheduled Daily Alert Job at 02:00 UTC (09:00 VN Time) (Mon-Fri)")
    else:
        logger.warning("JobQueue is not enabled! Scheduling features will not work.")
        
    
    
    logger.info("Wyckoff Bot is now running. Polling for messages...")
    application.run_polling()

if __name__ == '__main__':
    main()
