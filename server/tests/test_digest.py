from datetime import datetime, timedelta, timezone

from calmfeed import digest, youtube
from calmfeed.rules import Rules

NOW = datetime(2026, 11, 5, 12, 0, tzinfo=timezone.utc)


def video(n, channel="c1", hours_old=1, title=None, is_short=False):
    return {
        "video_id": f"video{n:06d}",
        "title": title or f"Video {n}",
        "published": NOW - timedelta(hours=hours_old),
        "channel_id": channel,
        "channel": f"Channel {channel}",
        "image_url": "",
        "text": "",
        "is_short": is_short,
    }


def test_every_item_and_held_back_entry_has_a_reason():
    videos = [video(1), video(2, "c2"), video(3, "c3", title="Big drama today")]
    items, held_back = digest.rank(videos, {}, Rules(exclude_keywords=("drama",)))
    assert items and held_back
    assert all(entry["why"].strip() for entry in items + held_back)


def test_newest_first_and_capped_per_source():
    videos = [video(i, "c1", hours_old=i) for i in range(1, 5)] + [video(9, "c2", hours_old=2.5)]
    items, _ = digest.rank(videos, {}, Rules(max_per_source=2))
    assert [i["video_id"] for i in items] == ["video000001", "video000002", "video000009"]


def test_digest_max_items():
    videos = [video(i, f"c{i}") for i in range(10)]
    items, _ = digest.rank(videos, {}, Rules(digest_max_items=4))
    assert len(items) == 4


def test_shorts_are_removed_by_rss_link_and_by_duration():
    videos = [video(1, is_short=True), video(2), video(3, "c2")]
    details = {"video000002": {"seconds": 45, "live": "none"},
               "video000003": {"seconds": 600, "live": "none"}}
    items, held_back = digest.rank(videos, details, Rules())
    assert [i["video_id"] for i in items] == ["video000003"]
    assert held_back == []


def test_shorts_stay_when_rule_is_off():
    items, _ = digest.rank([video(1, is_short=True)], {}, Rules(hide_shorts=False))
    assert len(items) == 1


def test_upcoming_premieres_are_skipped():
    details = {"video000001": {"seconds": 0, "live": "upcoming"}}
    assert digest.rank([video(1)], details, Rules()) == ([], [])


def test_keywords_match_whole_words_case_insensitively():
    videos = [video(1, title="Pranks for days"), video(2, "c2", title="The PRANK that failed")]
    items, held_back = digest.rank(videos, {}, Rules(exclude_keywords=("prank",)))
    assert [i["title"] for i in items] == ["Pranks for days"]
    assert held_back[0]["why"] == "excluded keyword: prank"


def test_window_drops_old_videos():
    videos = [video(1, hours_old=35), video(2, hours_old=37)]
    assert [v["video_id"] for v in digest.in_window(videos, Rules(window_hours=36), NOW)] == ["video000001"]


RSS = """<?xml version="1.0"?>
<feed xmlns:yt="http://www.youtube.com/xml/schemas/2015"
      xmlns:media="http://search.yahoo.com/mrss/" xmlns="http://www.w3.org/2005/Atom">
 <entry>
  <yt:videoId>abc123def45</yt:videoId>
  <title>A real video</title>
  <link rel="alternate" href="https://www.youtube.com/watch?v=abc123def45"/>
  <published>2026-11-05T10:00:00+00:00</published>
  <media:group>
   <media:thumbnail url="https://i1.ytimg.com/vi/abc123def45/hqdefault.jpg"/>
   <media:description>Hello</media:description>
  </media:group>
 </entry>
 <entry>
  <yt:videoId>short000001</yt:videoId>
  <title>A short</title>
  <link rel="alternate" href="https://www.youtube.com/shorts/short000001"/>
  <published>2026-11-05T09:00:00+00:00</published>
 </entry>
</feed>"""


def test_parse_rss():
    first, second = youtube.parse_rss(RSS, {"channel_id": "c1", "title": "Channel"})
    assert first["video_id"] == "abc123def45"
    assert first["published"].tzinfo is not None
    assert first["image_url"].endswith("hqdefault.jpg")
    assert first["text"] == "Hello"
    assert not first["is_short"]
    assert second["is_short"]


def test_parse_duration():
    assert youtube.parse_duration("PT1H2M3S") == 3723
    assert youtube.parse_duration("PT45S") == 45
    assert youtube.parse_duration("P1DT1S") == 86401
    assert youtube.parse_duration("P0D") == 0
    assert youtube.parse_duration("") == 0
