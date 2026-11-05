"""Google OAuth, the YouTube Data API, and free per-channel RSS.

Quota use per daily digest: 1 unit per 50 subscriptions, 1 per 50 candidate
videos. Reading the videos themselves goes through RSS and costs nothing.
"""
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from urllib.parse import urlencode

import httpx

from . import config

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
API = "https://www.googleapis.com/youtube/v3"
RSS_URL = "https://www.youtube.com/feeds/videos.xml"
SCOPES = "openid email https://www.googleapis.com/auth/youtube.readonly"

NS = {
    "a": "http://www.w3.org/2005/Atom",
    "yt": "http://www.youtube.com/xml/schemas/2015",
    "media": "http://search.yahoo.com/mrss/",
}


class ReauthRequired(Exception):
    """Google no longer accepts our token, so the user has to sign in again."""


def authorize_url(state: str) -> str:
    return AUTH_URL + "?" + urlencode({
        "client_id": config.GOOGLE_CLIENT_ID,
        "redirect_uri": config.REDIRECT_URI,
        "response_type": "code",
        "scope": SCOPES,
        "state": state,
        "access_type": "offline",
        "prompt": "consent",  # always returns a refresh token
    })


async def exchange_code(client: httpx.AsyncClient, code: str) -> dict:
    resp = await client.post(TOKEN_URL, data={
        "code": code,
        "client_id": config.GOOGLE_CLIENT_ID,
        "client_secret": config.GOOGLE_CLIENT_SECRET,
        "redirect_uri": config.REDIRECT_URI,
        "grant_type": "authorization_code",
    })
    resp.raise_for_status()
    return resp.json()


async def fetch_userinfo(client: httpx.AsyncClient, access_token: str) -> dict:
    resp = await client.get(USERINFO_URL, headers=_bearer(access_token))
    resp.raise_for_status()
    return resp.json()


async def access_token_for(client: httpx.AsyncClient, conn, user) -> str:
    """A valid access token for this user, refreshing it if needed."""
    if user["access_token"] and (user["access_expires_at"] or 0) > time.time() + 60:
        return user["access_token"]
    if not user["refresh_token"]:
        raise ReauthRequired
    resp = await client.post(TOKEN_URL, data={
        "client_id": config.GOOGLE_CLIENT_ID,
        "client_secret": config.GOOGLE_CLIENT_SECRET,
        "refresh_token": user["refresh_token"],
        "grant_type": "refresh_token",
    })
    if resp.status_code in (400, 401):
        raise ReauthRequired
    resp.raise_for_status()
    token = resp.json()
    conn.execute(
        "UPDATE users SET access_token = ?, access_expires_at = ? WHERE id = ?",
        (token["access_token"], time.time() + token["expires_in"], user["id"]),
    )
    conn.commit()
    return token["access_token"]


async def list_subscriptions(client: httpx.AsyncClient, token: str) -> list[dict]:
    channels, page = [], None
    while True:
        params = {"part": "snippet", "mine": "true", "maxResults": 50}
        if page:
            params["pageToken"] = page
        data = await _api_get(client, token, "/subscriptions", params)
        for item in data.get("items", []):
            snippet = item["snippet"]
            channels.append({
                "channel_id": snippet["resourceId"]["channelId"],
                "title": snippet["title"],
            })
        page = data.get("nextPageToken")
        if not page:
            return channels


async def fetch_channel_videos(client: httpx.AsyncClient, channel: dict) -> list[dict]:
    resp = await client.get(RSS_URL, params={"channel_id": channel["channel_id"]})
    resp.raise_for_status()
    return parse_rss(resp.text, channel)


def parse_rss(xml_text: str, channel: dict) -> list[dict]:
    videos = []
    for entry in ET.fromstring(xml_text).findall("a:entry", NS):
        link = entry.find("a:link", NS)
        href = link.get("href", "") if link is not None else ""
        thumb = entry.find("media:group/media:thumbnail", NS)
        desc = entry.find("media:group/media:description", NS)
        videos.append({
            "video_id": entry.findtext("yt:videoId", "", NS),
            "title": entry.findtext("a:title", "", NS),
            "published": datetime.fromisoformat(entry.findtext("a:published", "", NS)),
            "channel_id": channel["channel_id"],
            "channel": channel["title"],
            "image_url": thumb.get("url", "") if thumb is not None else "",
            "text": (desc.text or "") if desc is not None else "",
            "is_short": "/shorts/" in href,
        })
    return videos


async def fetch_video_details(client: httpx.AsyncClient, token: str,
                              video_ids: list[str]) -> dict[str, dict]:
    details = {}
    for start in range(0, len(video_ids), 50):
        data = await _api_get(client, token, "/videos", {
            "part": "contentDetails,snippet",
            "id": ",".join(video_ids[start:start + 50]),
            "maxResults": 50,
        })
        for item in data.get("items", []):
            details[item["id"]] = {
                "seconds": parse_duration(item["contentDetails"].get("duration", "")),
                "live": item["snippet"].get("liveBroadcastContent", "none"),
            }
    return details


def parse_duration(value: str) -> int:
    """ISO 8601 durations as YouTube writes them, e.g. P1DT2H3M4S."""
    match = re.fullmatch(r"P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?", value)
    if not match:
        return 0
    days, hours, minutes, seconds = (int(g or 0) for g in match.groups())
    return ((days * 24 + hours) * 60 + minutes) * 60 + seconds


def _bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _api_get(client: httpx.AsyncClient, token: str, path: str, params: dict) -> dict:
    resp = await client.get(API + path, params=params, headers=_bearer(token))
    if resp.status_code == 401:
        raise ReauthRequired
    resp.raise_for_status()
    return resp.json()
