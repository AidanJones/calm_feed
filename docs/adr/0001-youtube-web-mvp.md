# ADR 0001: YouTube-only web MVP

Date: 2026-11-05 · Status: accepted

## Context

The spec builds in seven milestones, starting with a browser extension and a Flutter app. The first goal here is narrower: sign in to one platform and use it through its API, to find out whether a calm daily digest is good to live with.

## Decisions

| Spec | MVP | Why |
| --- | --- | --- |
| Flutter client, and the web app doesn't show feeds | Plain HTML and JS served by the backend, showing the feed | No build toolchain needed. The client holds no rules or budget clock, so Flutter can replace it against the same API |
| Overlay on every platform, API connector optional | API connector only, YouTube only | It's the part that needs a login and an API. Site adapters are a separate milestone |
| `network_buzz` ranking | Newest first, the spec's Following view | With one platform there are no shares by follows to count. Nothing is ranked by engagement |
| Sign-in with short-lived JWTs, Apple, magic link | Google OAuth with a signed session cookie | Google sign-in is needed anyway to read subscriptions |
| Google tokens held by reference (`api_token_ref`) | Stored unencrypted in local SQLite | Acceptable for a single-user install on your own machine. Must change before any shared or networked install |
| `items`, `feed_entries`, `sources` tables | One `digests` row per day, holding JSON | A digest is a fixed daily snapshot, so nothing queries individual entries yet |
| Budget table includes `per_platform_json`; `sessions` table | Omitted | One platform, and nothing reads them yet |
| `docker compose up` | `uvicorn` in a virtualenv | One process and a SQLite file don't need it yet |

## Left for later

Search, mutes, the guard classifier, suggestions, auto-grouping (every save goes to Inbox), Zotero and Obsidian export, sharing, the rules editor and rule diffs, and the audit log.

`rules.yaml` lists only the settings the MVP obeys, so the file never promises something the app doesn't do.

## Known limits

- The digest is built on first open each day, so videos published later that day appear in the next digest if they're still inside the window.
- `active` and `origin` in heartbeats are reported by the client. The server decides how much time that costs and whether the feed is open, but a modified client could under-report. The spec's model has the same limit.
- Returning to the digest after a break can cost up to one heartbeat interval (16 seconds), because the server can't tell a gap from a slow client without letting clients earn free time.
