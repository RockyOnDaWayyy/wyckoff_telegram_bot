import os
from pathlib import Path
from dotenv import load_dotenv

# Load env variables
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
TEMP_DIR = BASE_DIR / "chart_temp"
TEMP_DIR.mkdir(exist_ok=True)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8800735097:AAG0qjIfhMmYvbf4lxRltSwqUwfG6a1wRrk")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "-5578729176")

# Wyckoff Analysis parameters
HISTORY_DAYS_DEFAULT = 730  # Fetch 2 years of data by default
MIN_SWING_WINDOW = 5        # Rolling window to detect swing highs/lows
RelativeStrengthWindow = 20 # Window for rolling returns

# Quantitative parameters
VaR_ALPHA = 0.95            # Value at Risk confidence level (95%)
VaR_DAYS = 252              # 1 trading year for VaR calculations
