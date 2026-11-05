"""SQLite storage (the spec allows it for single-user installs)."""
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY,
  google_sub TEXT NOT NULL UNIQUE,
  email TEXT NOT NULL,
  refresh_token TEXT,
  access_token TEXT,
  access_expires_at REAL,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS budgets (
  user_id INTEGER NOT NULL REFERENCES users(id),
  date TEXT NOT NULL,
  feed_seconds_allowed REAL NOT NULL,
  feed_seconds_used REAL NOT NULL DEFAULT 0,
  last_heartbeat_at REAL,
  exhausted_at REAL,
  PRIMARY KEY (user_id, date)
);
CREATE TABLE IF NOT EXISTS digests (
  user_id INTEGER NOT NULL REFERENCES users(id),
  date TEXT NOT NULL,
  items_json TEXT NOT NULL,
  held_back_json TEXT NOT NULL,
  channels_total INTEGER NOT NULL,
  channels_failed INTEGER NOT NULL,
  PRIMARY KEY (user_id, date)
);
CREATE TABLE IF NOT EXISTS saved_items (
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id),
  platform TEXT NOT NULL,
  url TEXT NOT NULL,
  video_id TEXT NOT NULL,
  title TEXT NOT NULL,
  text TEXT NOT NULL DEFAULT '',
  author TEXT NOT NULL DEFAULT '',
  image_url TEXT NOT NULL DEFAULT '',
  saved_from TEXT NOT NULL,
  saved_at REAL NOT NULL,
  UNIQUE (user_id, url)
);
"""


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(SCHEMA)
    return conn
