"""
Configuration for the Course Training Agent system.
"""
import os
import json
from pathlib import Path

# Directories
BASE_DIR = Path(__file__).parent
REPORTS_DIR = BASE_DIR / "reports"
REPORTS_DIR.mkdir(exist_ok=True)

# Anthropic API key - set via environment variable or config file
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# Config file path
CONFIG_FILE = BASE_DIR / "settings.json"

def load_config():
    """Load settings from settings.json if it exists."""
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    return {}

def save_config(config: dict):
    """Save settings to settings.json."""
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)

def get_api_key():
    """Get the Anthropic API key from env or config file."""
    key = ANTHROPIC_API_KEY
    if not key:
        cfg = load_config()
        key = cfg.get("anthropic_api_key", "")
    return key

# Browser settings
BROWSER_CONNECT_TIMEOUT = 30000  # ms
PAGE_LOAD_TIMEOUT = 60000  # ms
SCROLL_PAUSE_TIME = 2  # seconds between scrolls
MAX_SCROLL_ATTEMPTS = 50  # max page scrolls for content extraction

# AI settings
AI_MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 8192

# Execution settings
COMMAND_TIMEOUT = 300  # seconds per command
SAFE_MODE = True  # when True, asks before destructive commands
