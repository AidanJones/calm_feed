"""Environment-level settings. Behaviour settings live in rules.yaml."""
import os
import secrets
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

SERVER_DIR = Path(__file__).resolve().parents[1]
load_dotenv(SERVER_DIR / ".env")

DATA_DIR = Path(os.getenv("CALM_DATA_DIR", SERVER_DIR / "data"))
DB_PATH = DATA_DIR / "calmfeed.db"
RULES_PATH = Path(os.getenv("CALM_RULES", SERVER_DIR / "rules.yaml"))
STATIC_DIR = SERVER_DIR / "static"

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
BASE_URL = os.getenv("CALM_BASE_URL", "http://localhost:8000").rstrip("/")
REDIRECT_URI = f"{BASE_URL}/auth/callback"

_tz_name = os.getenv("CALM_TIMEZONE", "").strip()
TIMEZONE = ZoneInfo(_tz_name) if _tz_name else None  # None = system local


def session_secret() -> str:
    """Generated once and kept beside the database, so setup has one less step."""
    path = DATA_DIR / "session_secret"
    if not path.exists():
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(secrets.token_urlsafe(48))
    return path.read_text().strip()
