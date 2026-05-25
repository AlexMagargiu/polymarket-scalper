import os

# === Strategy Parameters ===
SURGE_THRESHOLD = 0.10          # 10c move to count as internal surge signal
DETECTION_WINDOW_MIN = 30       # seconds — surge detection window
DETECTION_WINDOW_MAX = 60       # seconds — upper bound of detection window
TAKE_PROFIT = 0.90              # hard exit at 90c

# === Trend Detection ===
TREND_WINDOW = 900              # 15 minutes — how far back to look for surge history
TREND_MIN_SURGES = 3            # minimum ascending surges to confirm a trend
TREND_COOLDOWN = 300            # 5 minutes — don't re-enter same token after trend fires
TRAILING_STOP_PCT = 0.10        # 10% reversal from peak triggers exit
MAX_ENTRY_PRICE = 0.80          # refuse entries above 80c (no upside to 90c TP)
STALE_POSITION_TIMEOUT = 7200   # 2 hours — close positions with no price updates
TRAILING_STOP_GRACE = 30        # seconds — don't check trailing stop for first 30s after entry
SURGE_COOLDOWN = 30             # seconds between surges on same token
RESOLVING_BID = 0.02            # bid below this = resolving/resolved
RESOLVING_ASK = 0.98            # ask above this = resolving/resolved
MAX_ENTRY_SPREAD = 0.15         # reject entries with spread wider than this
TREND_MIN_MAGNITUDE = 0.15      # 15c minimum move from first surge to current price
DATA_RETENTION_DAYS = 60        # purge price_history, surges, trends older than this

# === Position / Risk Limits ===
POSITION_SIZE = 25.0            # $25 per trade
STARTING_BALANCE = 5000.0       # $5,000 paper balance
MAX_CONCURRENT_POSITIONS = 10
MAX_POSITIONS_PER_MARKET = 3    # scaling in
MAX_ENTRIES_PER_MARKET_PER_DAY = 1  # one shot per market per day
MAX_DAILY_TRADES = 100
DAILY_LOSS_LIMIT = 500.0        # $500 — pause trading if hit

# === Fees (paper trading worst-case) ===
TAKER_FEE_RATE = 0.02           # 2% both entry and exit

# === Market Filtering ===
MIN_VOLUME_24H = 10_000         # $10K minimum 24h volume

# === URLs ===
WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
GAMMA_API_URL = "https://gamma-api.polymarket.com/markets"

# === API / Services (from env) ===
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
API_PORT = int(os.getenv("API_PORT", "8099"))
API_AUTH_TOKEN = os.getenv("API_AUTH_TOKEN", "")

# === WebSocket Pool ===
WS_MAX_TOKENS_PER_CONNECTION = 200  # Polymarket practical limit ~500, NautilusTrader defaults to 200

# === Reconnect ===
RECONNECT_INITIAL_DELAY = 1.0   # seconds
RECONNECT_MAX_DELAY = 60.0      # seconds
RECONNECT_MULTIPLIER = 2.0

# === Data ===
DB_PATH = os.getenv("DB_PATH", "scalper.db")
MARKET_REFRESH_INTERVAL = 300   # 5 minutes
PRICE_WINDOW_MAX_AGE = 120      # seconds — prune rolling window entries older than this
# === Logging ===
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
