"""HTTP API and static client. Run from server/: uvicorn calmfeed.main:app

Routes are all `async def` on purpose: they then run one at a time on the event
loop, so concurrent heartbeats can't race on the shared SQLite connection.
"""
import logging
import re
import secrets
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Literal

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.middleware.sessions import SessionMiddleware

from . import budget, config, db, digest, rules as rules_module, youtube

log = logging.getLogger(__name__)

WATCH_URL = re.compile(r"https://www\.youtube\.com/watch\?v=([\w-]{6,20})")


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.conn = db.connect(config.DB_PATH)
    app.state.http = httpx.AsyncClient(timeout=15)
    yield
    await app.state.http.aclose()
    app.state.conn.close()


app = FastAPI(title="Calm Feed", lifespan=lifespan)
app.add_middleware(
    SessionMiddleware,
    secret_key=config.session_secret(),
    session_cookie="calmfeed",
    same_site="lax",
    https_only=config.BASE_URL.startswith("https://"),
    max_age=60 * 60 * 24 * 30,
)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def load_rules() -> rules_module.Rules:
    return rules_module.load(config.RULES_PATH)


def conn_of(request: Request):
    return request.app.state.conn


async def current_user(request: Request):
    user_id = request.session.get("user_id")
    user = user_id and conn_of(request).execute(
        "SELECT * FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    if not user:
        raise HTTPException(401, "not_signed_in")
    return user


def state_payload(state: budget.BudgetState, rules: rules_module.Rules) -> dict:
    return {
        "feed_available": state.feed_available,
        "seconds_left": round(state.seconds_left),
        "seconds_allowed": round(state.seconds_allowed),
        "reset_at": state.reset_at.isoformat(),
        "rules_version": rules.version,
        "heartbeat_seconds": budget.HEARTBEAT_SECONDS,
    }


# --- Sign-in ---------------------------------------------------------------

@app.get("/auth/login")
async def login(request: Request):
    if not (config.GOOGLE_CLIENT_ID and config.GOOGLE_CLIENT_SECRET):
        return RedirectResponse("/?setup=1", status_code=303)
    state = secrets.token_urlsafe(24)
    request.session["oauth_state"] = state
    return RedirectResponse(youtube.authorize_url(state), status_code=303)


@app.get("/auth/callback")
async def callback(request: Request, state: str = "", code: str = "", error: str = ""):
    expected = request.session.pop("oauth_state", None)
    if not expected or not secrets.compare_digest(expected, state):
        raise HTTPException(400, "invalid_oauth_state")
    if error or not code:
        return RedirectResponse("/?signin=cancelled", status_code=303)

    http = request.app.state.http
    token = await youtube.exchange_code(http, code)
    info = await youtube.fetch_userinfo(http, token["access_token"])
    conn = conn_of(request)
    conn.execute(
        "INSERT INTO users (google_sub, email, refresh_token, access_token, access_expires_at) "
        "VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT (google_sub) DO UPDATE SET email = excluded.email, "
        "refresh_token = COALESCE(excluded.refresh_token, refresh_token), "
        "access_token = excluded.access_token, access_expires_at = excluded.access_expires_at",
        (info["sub"], info.get("email", ""), token.get("refresh_token"),
         token["access_token"], time.time() + token["expires_in"]),
    )
    conn.commit()
    row = conn.execute("SELECT id FROM users WHERE google_sub = ?", (info["sub"],)).fetchone()
    request.session["user_id"] = row["id"]
    return RedirectResponse("/", status_code=303)


@app.post("/auth/logout")
async def logout(request: Request):
    request.session.clear()
    return {"ok": True}


@app.exception_handler(youtube.ReauthRequired)
async def reauth_required(request: Request, exc: youtube.ReauthRequired):
    request.session.clear()
    return JSONResponse({"detail": "reauth_required"}, status_code=401)


# --- Budget ----------------------------------------------------------------

class Heartbeat(BaseModel):
    platform: Literal["youtube"] = "youtube"
    origin: Literal["feed", "search", "saved"]
    session_id: str = ""
    active: bool


@app.get("/v1/state")
async def get_state(request: Request, user=Depends(current_user)):
    rules = load_rules()
    state = budget.current(conn_of(request), user["id"], now_utc(), config.TIMEZONE, rules)
    return {**state_payload(state, rules), "email": user["email"]}


@app.post("/v1/heartbeat")
async def post_heartbeat(beat: Heartbeat, request: Request, user=Depends(current_user)):
    rules = load_rules()
    state = budget.heartbeat(conn_of(request), user["id"], beat.origin, beat.active,
                             now_utc(), config.TIMEZONE, rules)
    return state_payload(state, rules)


# --- Digest ----------------------------------------------------------------

@app.get("/v1/feed")
async def get_feed(request: Request, user=Depends(current_user)):
    rules = load_rules()
    now = now_utc()
    conn = conn_of(request)
    state = budget.current(conn, user["id"], now, config.TIMEZONE, rules)
    if not state.feed_available:
        return JSONResponse({"detail": "feed_exhausted"}, status_code=410)
    try:
        return await digest.get_or_build(request.app.state.http, conn, user, state.date, now, rules)
    except digest.SourcesUnavailable:
        raise HTTPException(502, "sources_unavailable")
    except httpx.HTTPStatusError as exc:
        log.warning("YouTube API error: %s %s", exc.response.status_code, exc.response.text[:500])
        raise HTTPException(502, "youtube_api_error")


# --- Saved library ---------------------------------------------------------

class Capture(BaseModel):
    platform: Literal["youtube"] = "youtube"
    url: str
    title: str
    text: str = ""
    author: str = ""
    image_url: str = ""
    saved_from: Literal["feed", "search"] = "feed"


def saved_payload(row) -> dict:
    item = dict(row)
    item.pop("user_id")
    saved = datetime.fromtimestamp(row["saved_at"], timezone.utc).astimezone(config.TIMEZONE)
    item["why"] = f"saved {saved.day} {saved:%b}"
    return item


@app.post("/v1/capture")
async def capture(item: Capture, request: Request, user=Depends(current_user)):
    match = WATCH_URL.fullmatch(item.url)
    if not match:
        raise HTTPException(422, "unsupported_url")
    conn = conn_of(request)
    conn.execute(
        "INSERT OR IGNORE INTO saved_items "
        "(user_id, platform, url, video_id, title, text, author, image_url, saved_from, saved_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (user["id"], item.platform, item.url, match.group(1), item.title, item.text,
         item.author, item.image_url, item.saved_from, time.time()),
    )
    conn.commit()
    row = conn.execute(
        "SELECT * FROM saved_items WHERE user_id = ? AND url = ?", (user["id"], item.url)
    ).fetchone()
    return {**saved_payload(row), "group": "Inbox"}


@app.get("/v1/saved")
async def list_saved(request: Request, q: str = "", user=Depends(current_user)):
    pattern = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    rows = conn_of(request).execute(
        "SELECT * FROM saved_items WHERE user_id = ? AND "
        "(title LIKE ? ESCAPE '\\' OR author LIKE ? ESCAPE '\\' OR text LIKE ? ESCAPE '\\') "
        "ORDER BY saved_at DESC",
        (user["id"], pattern, pattern, pattern),
    ).fetchall()
    return {"items": [saved_payload(r) for r in rows]}


@app.delete("/v1/saved/{item_id}")
async def delete_saved(item_id: int, request: Request, user=Depends(current_user)):
    conn = conn_of(request)
    cursor = conn.execute(
        "DELETE FROM saved_items WHERE id = ? AND user_id = ?", (item_id, user["id"])
    )
    conn.commit()
    if not cursor.rowcount:
        raise HTTPException(404, "not_found")
    return {"ok": True}


# --- Client ----------------------------------------------------------------

@app.get("/")
async def index():
    return FileResponse(config.STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=config.STATIC_DIR), name="static")
