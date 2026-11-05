"""End-to-end through the HTTP API, with Google and YouTube replaced by httpx mocks."""
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from fastapi.testclient import TestClient

from calmfeed import config, main


def rss(channel_id: str) -> str:
    published = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    return f"""<?xml version="1.0"?>
<feed xmlns:yt="http://www.youtube.com/xml/schemas/2015"
      xmlns:media="http://search.yahoo.com/mrss/" xmlns="http://www.w3.org/2005/Atom">
 <entry>
  <yt:videoId>{channel_id}vid00</yt:videoId>
  <title>Video from {channel_id}</title>
  <link rel="alternate" href="https://www.youtube.com/watch?v={channel_id}vid00"/>
  <published>{published}</published>
 </entry>
</feed>"""


class FakeGoogle:
    def __init__(self):
        self.rss_status = 200
        self.calls = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        self.calls.append(path)
        if path == "/token":
            return httpx.Response(200, json={
                "access_token": "access", "refresh_token": "refresh", "expires_in": 3600,
            })
        if path == "/v1/userinfo":
            return httpx.Response(200, json={"sub": "google-1", "email": "me@example.com"})
        if path.endswith("/subscriptions"):
            assert request.headers["authorization"] == "Bearer access"
            return httpx.Response(200, json={"items": [
                {"snippet": {"title": "One", "resourceId": {"channelId": "UCone"}}},
                {"snippet": {"title": "Two", "resourceId": {"channelId": "UCtwo"}}},
            ]})
        if path.endswith("/videos"):
            return httpx.Response(200, json={"items": [
                {"id": vid, "contentDetails": {"duration": "PT10M"},
                 "snippet": {"liveBroadcastContent": "none"}}
                for vid in request.url.params["id"].split(",")
            ]})
        if path == "/feeds/videos.xml":
            if self.rss_status != 200:
                return httpx.Response(self.rss_status)
            return httpx.Response(200, text=rss(request.url.params["channel_id"]))
        raise AssertionError(f"unexpected request: {request.url}")


@pytest.fixture
def google():
    return FakeGoogle()


@pytest.fixture
def client(google, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "api.db")
    rules = tmp_path / "rules.yaml"
    rules.write_text("budget: {feed_minutes: 30}\n")
    monkeypatch.setattr(config, "RULES_PATH", rules)
    with TestClient(main.app, base_url="http://localhost:8000") as test_client:
        main.app.state.http = httpx.AsyncClient(transport=httpx.MockTransport(google))
        yield test_client


def sign_in(client: TestClient) -> None:
    redirect = client.get("/auth/login", follow_redirects=False)
    assert redirect.status_code == 303
    query = parse_qs(urlparse(redirect.headers["location"]).query)
    assert "youtube.readonly" in query["scope"][0]
    done = client.get("/auth/callback", params={"state": query["state"][0], "code": "c"},
                      follow_redirects=False)
    assert done.status_code == 303


def test_everything_needs_sign_in(client):
    for path in ("/v1/state", "/v1/feed", "/v1/saved"):
        assert client.get(path).status_code == 401


def test_callback_rejects_a_forged_state(client):
    client.get("/auth/login", follow_redirects=False)
    response = client.get("/auth/callback", params={"state": "forged", "code": "c"})
    assert response.status_code == 400


def test_sign_in_then_digest(client):
    sign_in(client)
    assert client.get("/v1/state").json()["email"] == "me@example.com"

    feed = client.get("/v1/feed").json()
    assert [i["author"] for i in feed["items"]] == ["One", "Two"] or \
           [i["author"] for i in feed["items"]] == ["Two", "One"]
    assert all(i["why"].startswith("followed: ") for i in feed["items"])


def test_digest_is_built_once_a_day(client, google):
    sign_in(client)
    first = client.get("/v1/feed").json()
    calls = len(google.calls)
    assert client.get("/v1/feed").json() == first
    assert len(google.calls) == calls


def test_feed_returns_410_when_budget_is_gone(client):
    sign_in(client)
    config.RULES_PATH.write_text("budget: {feed_minutes: 0}\n")
    assert client.get("/v1/state").json()["feed_available"] is False
    response = client.get("/v1/feed")
    assert response.status_code == 410
    assert response.json() == {"detail": "feed_exhausted"}


def test_saved_works_after_budget_is_gone(client):
    sign_in(client)
    config.RULES_PATH.write_text("budget: {feed_minutes: 0}\n")
    saved = client.post("/v1/capture", json={
        "url": "https://www.youtube.com/watch?v=abc123def45", "title": "Barre chords",
    })
    assert saved.status_code == 200
    assert saved.json()["group"] == "Inbox"
    assert saved.json()["why"].startswith("saved ")
    assert len(client.get("/v1/saved").json()["items"]) == 1


def test_failed_build_is_not_kept(client, google):
    sign_in(client)
    google.rss_status = 500
    assert client.get("/v1/feed").status_code == 502
    google.rss_status = 200
    assert len(client.get("/v1/feed").json()["items"]) == 2


def test_capture_is_idempotent_and_searchable_and_deletable(client):
    sign_in(client)
    body = {"url": "https://www.youtube.com/watch?v=abc123def45", "title": "100% barre_chords"}
    first = client.post("/v1/capture", json=body).json()
    assert client.post("/v1/capture", json=body).json()["id"] == first["id"]

    assert len(client.get("/v1/saved", params={"q": "barre_"}).json()["items"]) == 1
    assert len(client.get("/v1/saved", params={"q": "0%"}).json()["items"]) == 1
    assert client.get("/v1/saved", params={"q": "b_rre"}).json()["items"] == []

    assert client.delete(f"/v1/saved/{first['id']}").status_code == 200
    assert client.delete(f"/v1/saved/{first['id']}").status_code == 404


@pytest.mark.parametrize("url", [
    "javascript:alert(1)",
    "https://evil.example/watch?v=abc123def45",
    "https://www.youtube.com/watch?v=abc123def45&list=x",
])
def test_capture_rejects_anything_but_a_watch_url(client, url):
    sign_in(client)
    assert client.post("/v1/capture", json={"url": url, "title": "t"}).status_code == 422


def test_heartbeat_payload_never_lets_the_client_set_time(client):
    sign_in(client)
    response = client.post("/v1/heartbeat", json={
        "origin": "feed", "active": True, "seconds_left": 99999,
    })
    assert response.json()["seconds_left"] == 1800


def test_expired_google_access_asks_for_sign_in_again(client, google, monkeypatch):
    sign_in(client)
    main.app.state.conn.execute("UPDATE users SET access_expires_at = 0")
    original = google.__call__

    def refuse_refresh(request):
        if request.url.path == "/token":
            return httpx.Response(400, json={"error": "invalid_grant"})
        return original(request)

    main.app.state.http = httpx.AsyncClient(transport=httpx.MockTransport(refuse_refresh))
    response = client.get("/v1/feed")
    assert response.status_code == 401
    assert response.json() == {"detail": "reauth_required"}
    assert client.get("/v1/state").status_code == 401
