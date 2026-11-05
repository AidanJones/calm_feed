"""The daily feed budget. The server's clock is the only one that counts.

Time is charged per user, not per client, so two open tabs burn one budget at
wall-clock speed. Each heartbeat can charge at most MAX_CHARGE_SECONDS, so
sending fewer heartbeats earns nothing and a closed laptop costs nothing.
"""
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, tzinfo

from .rules import Rules

HEARTBEAT_SECONDS = 15
MAX_CHARGE_SECONDS = 16  # one heartbeat interval, plus timer jitter


@dataclass(frozen=True)
class BudgetState:
    date: str
    seconds_allowed: float
    seconds_used: float
    reset_at: datetime

    @property
    def seconds_left(self) -> float:
        return max(0.0, self.seconds_allowed - self.seconds_used)

    @property
    def feed_available(self) -> bool:
        return self.seconds_left > 0


def budget_date(now: datetime, tz: tzinfo | None, reset_hour: int) -> date:
    """The day a moment belongs to. Before reset_hour it is still yesterday."""
    return (now.astimezone(tz) - timedelta(hours=reset_hour)).date()


def _reset_at(day: date, now: datetime, tz: tzinfo | None, reset_hour: int) -> datetime:
    zone = tz or now.astimezone().tzinfo
    return datetime.combine(day + timedelta(days=1), time(reset_hour), tzinfo=zone)


def current(conn: sqlite3.Connection, user_id: int, now: datetime,
            tz: tzinfo | None, rules: Rules) -> BudgetState:
    day = budget_date(now, tz, rules.reset_hour)
    allowed = rules.feed_minutes * 60.0
    conn.execute(
        "INSERT OR IGNORE INTO budgets (user_id, date, feed_seconds_allowed) VALUES (?, ?, ?)",
        (user_id, day.isoformat(), allowed),
    )
    # Stricter applies immediately. Looser waits for tomorrow's row.
    conn.execute(
        "UPDATE budgets SET feed_seconds_allowed = ? "
        "WHERE user_id = ? AND date = ? AND feed_seconds_allowed > ?",
        (allowed, user_id, day.isoformat(), allowed),
    )
    conn.commit()
    row = conn.execute(
        "SELECT feed_seconds_allowed, feed_seconds_used FROM budgets WHERE user_id = ? AND date = ?",
        (user_id, day.isoformat()),
    ).fetchone()
    return BudgetState(
        date=day.isoformat(),
        seconds_allowed=row["feed_seconds_allowed"],
        seconds_used=row["feed_seconds_used"],
        reset_at=_reset_at(day, now, tz, rules.reset_hour),
    )


def heartbeat(conn: sqlite3.Connection, user_id: int, origin: str, active: bool,
              now: datetime, tz: tzinfo | None, rules: Rules) -> BudgetState:
    state = current(conn, user_id, now, tz, rules)
    if origin != "feed" or not active or not state.feed_available:
        return state

    row = conn.execute(
        "SELECT last_heartbeat_at FROM budgets WHERE user_id = ? AND date = ?",
        (user_id, state.date),
    ).fetchone()
    ts = now.timestamp()
    last = row["last_heartbeat_at"]
    charge = 0.0 if last is None else min(max(ts - last, 0.0), MAX_CHARGE_SECONDS)
    used = min(state.seconds_used + charge, state.seconds_allowed)
    conn.execute(
        "UPDATE budgets SET feed_seconds_used = ?, last_heartbeat_at = ?, "
        "exhausted_at = CASE WHEN ? >= feed_seconds_allowed THEN ? ELSE exhausted_at END "
        "WHERE user_id = ? AND date = ?",
        (used, ts, used, ts, user_id, state.date),
    )
    conn.commit()
    return current(conn, user_id, now, tz, rules)
