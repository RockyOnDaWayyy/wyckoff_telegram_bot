import datetime
import logging
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters

import config
import telegram_bot

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def main():
    """Start the telegram bot."""
    token = config.TELEGRAM_BOT_TOKEN
    if not token or ":" not in token:
        logger.error("Invalid TELEGRAM_BOT_TOKEN in configuration. Please check your .env file.")
        return
        
    logger.info("Initializing Wyckoff Telegram Bot...")
    
    # Build Telegram Bot application
    application = ApplicationBuilder().token(token).build()
    
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
    
    # Configure JobQueue scheduling (Monday to Friday, VN Time UTC+7)
    jq = application.job_queue
    if jq:
        VN_TZ = datetime.timezone(datetime.timedelta(hours=7))
        
        # 1. Market Scan at 15:00 VN time (Mon-Fri)
        scan_time = datetime.time(hour=15, minute=0, second=0, tzinfo=VN_TZ)
        jq.run_daily(
            telegram_bot.run_market_scan_job, 
            time=scan_time, 
            days=(0, 1, 2, 3, 4),
            name="market_scan_job"
        )
        logger.info(f"Scheduled Market Scan Job at 15:00 VN Time (Mon-Fri)")
        
        # 2. Daily Notification at 09:00 VN time (Mon-Fri)
        alert_time = datetime.time(hour=9, minute=0, second=0, tzinfo=VN_TZ)
        jq.run_daily(
            telegram_bot.send_daily_alert_job, 
            time=alert_time, 
            days=(0, 1, 2, 3, 4),
            name="daily_alert_job"
        )
        logger.info(f"Scheduled Daily Alert Job at 09:00 VN Time (Mon-Fri)")
    else:
        logger.warning("JobQueue is not enabled! Scheduling features will not work.")
        
    logger.info("Wyckoff Bot is now running. Polling for messages...")
    application.run_polling()

if __name__ == '__main__':
    main()
