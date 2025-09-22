# config.py
# Add these to your config.py
LID_CLOSE_TIMEOUT_SEC = 30  # 30 seconds timeout for lid closing
MOTOR_START_TIMEOUT_SEC = 30  # 30 seconds timeout for motor starting
# --- Timeout settings ---
ITEM_ADD_TIMEOUT_SEC = 180
MOTOR_START_TIMEOUT_SEC = 60

# --- Gateway connection settings ---
GATEWAY_HOST = "127.0.0.1"
GATEWAY_PORT = 5020

# --- HMI connection settings ---
HMI_HOST = "127.0.0.1"
HMI_PORT = 6000

# --- Log file path ---
LOG_FILE = "logs/kneader.log"
