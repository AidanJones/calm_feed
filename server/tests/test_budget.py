from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from calmfeed import budget, db
from calmfeed.rules import Rules

UTC = timezone.utc
T0 = datetime(2026, 11, 5, 12, 0, tzinfo=UTC)
RULES = Rules(feed_minutes=1, reset_hour=4)


@pytest.fixture
def conn(tmp_path: Path):
    connection = db.connect(tmp_path / "t.db")
    connection.execute("INSERT INTO users (id, google_sub, email) VALUES (1, 's', 'e')")
    yield connection
    connection.close()


def beat(conn, at, origin="feed", active=True, rules=RULES):
    return budget.heartbeat(conn, 1, origin, active, at, UTC, rules)


def test_active_feed_time_is_charged(conn):
    beat(conn, T0)
    state = beat(conn, T0 + timedelta(seconds=15))
    assert state.seconds_used == 15


@pytest.mark.parametrize("origin,active", [("saved", True), ("search", True), ("feed", False)])
def test_saved_search_and_idle_time_are_free(conn, origin, active):
    beat(conn, T0, origin, active)
    state = beat(conn, T0 + timedelta(seconds=15), origin, active)
    assert state.seconds_used == 0


def test_long_gap_charges_one_interval_at_most(conn):
    beat(conn, T0)
    state = beat(conn, T0 + timedelta(hours=2))
    assert state.seconds_used == budget.MAX_CHARGE_SECONDS


def test_two_clients_share_one_budget_at_wall_clock_speed(conn):
    beat(conn, T0)
    beat(conn, T0 + timedelta(seconds=7))   # tab A
    state = beat(conn, T0 + timedelta(seconds=15))  # tab B
    assert state.seconds_used == 15


def test_feed_closes_at_zero_and_stays_closed(conn):
    at = T0
    beat(conn, at)
    for _ in range(4):
        at += timedelta(seconds=15)
        state = beat(conn, at)
    assert state.seconds_left == 0 and not state.feed_available
    assert not beat(conn, at + timedelta(seconds=15)).feed_available


def test_budget_resets_at_reset_hour_not_midnight(conn):
    late = datetime(2026, 11, 6, 3, 59, tzinfo=UTC)
    after = datetime(2026, 11, 6, 4, 0, tzinfo=UTC)
    assert budget.budget_date(late, UTC, 4).isoformat() == "2026-11-05"
    assert budget.budget_date(after, UTC, 4).isoformat() == "2026-11-06"

    beat(conn, late)
    beat(conn, late + timedelta(seconds=15))
    fresh = budget.current(conn, 1, after, UTC, RULES)
    assert fresh.seconds_used == 0
    assert fresh.date == "2026-11-06"


def test_stricter_applies_now_and_looser_waits_for_tomorrow(conn):
    normal = Rules(feed_minutes=30)
    assert budget.current(conn, 1, T0, UTC, normal).seconds_allowed == 1800

    stricter = Rules(feed_minutes=10)
    assert budget.current(conn, 1, T0, UTC, stricter).seconds_allowed == 600

    looser = Rules(feed_minutes=60)
    assert budget.current(conn, 1, T0, UTC, looser).seconds_allowed == 600
    tomorrow = T0 + timedelta(days=1)
    assert budget.current(conn, 1, tomorrow, UTC, looser).seconds_allowed == 3600
