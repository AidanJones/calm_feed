"""Builds the daily YouTube digest.

With one platform there are no cross-platform shares to count, so this is the
spec's Following view: newest first from channels you follow. Nothing here reads
views, likes or any other engagement figure.

A digest is built once per budget day and then fixed, so reloading can't turn
it into a feed that refills.
"""
import asyncio
import json
import logging
import re
import sqlite3
from datetime import datetime, timedelta

import httpx

from . import youtube
from .rules import Rules

log = logging.getLogger(__name__)

SHORTS_MAX_SECONDS = 60
RSS_CONCURRENCY = 10

_build_lock = asyncio.Lock()


class SourcesUnavailable(Exception):
    """Every channel feed failed, so there is nothing honest to show."""


def _keyword_hit(title: str, keywords: tuple[str, ...]) -> str | None:
    for keyword in keywords:
        if re.search(rf"\b{re.escape(keyword)}\b", title, re.IGNORECASE):
            return keyword
    return None


def in_window(videos: list[dict], rules: Rules, now: datetime) -> list[dict]:
    cutoff = now - timedelta(hours=rules.window_hours)
    return [v for v in videos if v["published"] >= cutoff]


def rank(videos: list[dict], details: dict[str, dict], rules: Rules) -> tuple[list[dict], list[dict]]:
    """Returns (digest items, held-back items). Every item carries its reason."""
    held_back, kept = [], []
    for video in sorted(videos, key=lambda v: v["published"], reverse=True):
        info = details.get(video["video_id"], {})
        if info.get("live") == "upcoming":
            continue  # nothing to watch yet
        seconds = info.get("seconds", 0)
        if rules.hide_shorts and (video["is_short"] or 0 < seconds <= SHORTS_MAX_SECONDS):
            continue
        keyword = _keyword_hit(video["title"], rules.exclude_keywords)
        if keyword:
            held_back.append({
                "title": video["title"],
                "channel": video["channel"],
                "why": f"excluded keyword: {keyword}",
            })
            continue
        kept.append((video, seconds))

    items, per_source = [], {}
    for video, seconds in kept:
        count = per_source.get(video["channel_id"], 0)
        if count >= rules.max_per_source or len(items) >= rules.digest_max_items:
            continue
        per_source[video["channel_id"]] = count + 1
        items.append({
            "platform": "youtube",
            "video_id": video["video_id"],
            "url": f"https://www.youtube.com/watch?v={video['video_id']}",
            "title": video["title"],
            "text": video["text"],
            "author": video["channel"],
            "image_url": video["image_url"],
            "published": video["published"].isoformat(),
            "seconds": seconds,
            "why": f"followed: {video['channel']}",
        })
    return items, held_back


async def get_or_build(client: httpx.AsyncClient, conn: sqlite3.Connection, user,
                       day: str, now: datetime, rules: Rules) -> dict:
    async with _build_lock:
        row = conn.execute(
            "SELECT * FROM digests WHERE user_id = ? AND date = ?", (user["id"], day)
        ).fetchone()
        if row is None:
            digest = await _build(client, conn, user, now, rules)
            conn.execute(
                "INSERT INTO digests VALUES (?, ?, ?, ?, ?, ?)",
                (user["id"], day, json.dumps(digest["items"]), json.dumps(digest["held_back"]),
                 digest["channels_total"], digest["channels_failed"]),
            )
            conn.commit()
            return digest
    return {
        "items": json.loads(row["items_json"]),
        "held_back": json.loads(row["held_back_json"]),
        "channels_total": row["channels_total"],
        "channels_failed": row["channels_failed"],
    }


async def _build(client: httpx.AsyncClient, conn: sqlite3.Connection, user,
                 now: datetime, rules: Rules) -> dict:
    token = await youtube.access_token_for(client, conn, user)
    channels = await youtube.list_subscriptions(client, token)

    limit = asyncio.Semaphore(RSS_CONCURRENCY)

    async def fetch(channel: dict) -> list[dict] | None:
        async with limit:
            try:
                return await youtube.fetch_channel_videos(client, channel)
            except Exception as exc:  # one bad feed must not sink the digest
                log.warning("RSS failed for %s: %s", channel["channel_id"], exc)
                return None

    results = await asyncio.gather(*(fetch(c) for c in channels))
    failed = sum(r is None for r in results)
    if channels and failed == len(channels):
        raise SourcesUnavailable

    recent = in_window([v for r in results if r for v in r], rules, now)
    details = await youtube.fetch_video_details(client, token, [v["video_id"] for v in recent])
    items, held_back = rank(recent, details, rules)
    return {
        "items": items,
        "held_back": held_back,
        "channels_total": len(channels),
        "channels_failed": failed,
    }
