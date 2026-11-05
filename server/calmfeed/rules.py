"""Loads rules.yaml. Read on every use, so edits need no restart."""
from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class Rules:
    version: int = 1
    feed_minutes: int = 30
    reset_hour: int = 4
    window_hours: int = 36
    digest_max_items: int = 40
    max_per_source: int = 2
    hide_shorts: bool = True
    exclude_keywords: tuple[str, ...] = ()


def load(path: Path) -> Rules:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    budget, feed = raw.get("budget") or {}, raw.get("feed") or {}
    d = Rules()
    rules = Rules(
        version=int(raw.get("version", d.version)),
        feed_minutes=int(budget.get("feed_minutes", d.feed_minutes)),
        reset_hour=int(budget.get("reset_hour", d.reset_hour)),
        window_hours=int(feed.get("window_hours", d.window_hours)),
        digest_max_items=int(feed.get("digest_max_items", d.digest_max_items)),
        max_per_source=int(feed.get("max_per_source", d.max_per_source)),
        hide_shorts=bool(feed.get("hide_shorts", d.hide_shorts)),
        exclude_keywords=tuple(str(k) for k in feed.get("exclude_keywords") or ()),
    )
    if rules.feed_minutes < 0 or not 0 <= rules.reset_hour <= 23:
        raise ValueError("rules.yaml: feed_minutes must be >= 0 and reset_hour 0-23")
    return rules
