import os

# === Strategy Parameters ===
SURGE_THRESHOLD = 0.10          # 10c minimum move to trigger entry
DETECTION_WINDOW_MIN = 30       # seconds — surge must happen within this window
DETECTION_WINDOW_MAX = 60       # seconds — upper bound of detection window
TRAILING_STOP = 0.10            # 10c reversal from peak triggers exit
TAKE_PROFIT = 0.90              # hard exit at 90c
SURGE_COOLDOWN = 60             # seconds — don't fire same direction on same token

# === Entry Bounds ===
MAX_ENTRY_PRICE_YES = 0.40      # don't buy YES above 40c
MIN_ENTRY_PRICE_NO = 0.60       # don't buy NO below 60c (i.e., YES above 60c)
MIN_ENTRY_PRICE = 0.10          # below this, no liquidity

# === Position / Risk Limits ===
POSITION_SIZE = 25.0            # $25 per trade
STARTING_BALANCE = 5000.0       # $5,000 paper balance
MAX_CONCURRENT_POSITIONS = 10
MAX_POSITIONS_PER_MARKET = 3    # scaling in
MAX_DAILY_TRADES = 100
DAILY_LOSS_LIMIT = 500.0        # $500 — pause trading if hit

# === Fees (paper trading worst-case) ===
TAKER_FEE_RATE = 0.02           # 2% both entry and exit

# === Market Filtering ===
MIN_VOLUME_24H = 10_000         # $10K minimum 24h volume

# === URLs ===
WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
GAMMA_API_URL = "https://gamma-api.polymarket.com/markets"
CLOB_API_URL = "https://clob.polymarket.com"

# === API / Services (from env) ===
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
API_PORT = int(os.getenv("API_PORT", "8099"))
API_AUTH_TOKEN = os.getenv("API_AUTH_TOKEN", "")

# === Reconnect ===
RECONNECT_INITIAL_DELAY = 1.0   # seconds
RECONNECT_MAX_DELAY = 60.0      # seconds
RECONNECT_MULTIPLIER = 2.0

# === Data ===
DB_PATH = os.getenv("DB_PATH", "scalper.db")
MARKET_REFRESH_INTERVAL = 300   # 5 minutes
PRICE_WINDOW_MAX_AGE = 120      # seconds — prune rolling window entries older than this
STALE_THRESHOLD = 60            # seconds — mark token stale if no update

# === Logging ===
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
