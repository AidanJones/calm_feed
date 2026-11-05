# Calm Feed

A short daily digest of the YouTube channels you follow. When your time is up, the feed is gone until tomorrow. Your saved videos stay available all day.

This is the YouTube-only MVP of [Spec.md](Spec.md). Sign in with Google and it reads your subscriptions, then shows you:

- **A fixed daily digest.** Newest videos from your subscriptions in the last 36 hours, at most 2 per channel and 40 in total. No Shorts. It's built once a day, so reloading never brings more.
- **A 30-minute budget, enforced on the server.** It's shared across tabs and devices, and it pauses when you're idle or in Saved.
- **A Save button on every video,** and a searchable Saved library.
- **The official YouTube player,** with no autoplay and our own end screen instead of a next video.
- **A reason on every card,** and a "Held back today" list of anything your rules filtered out.

Change the behaviour in [server/rules.yaml](server/rules.yaml). A stricter budget applies immediately and a looser one applies from the next reset.

## Setup

You need Python 3.12 and your own Google OAuth client. That's free and takes about five minutes.

### 1. Create the Google client

In the [Google Cloud Console](https://console.cloud.google.com/):

1. Create a project.
2. Under **APIs & Services > Library**, enable **YouTube Data API v3**.
3. Open **Google Auth Platform** and configure it with audience **External**. Under **Audience > Test users**, add your own Google address.
4. Under **Clients**, create a client of type **Web application** with this authorized redirect URI:

   ```
   http://localhost:8000/auth/callback
   ```

5. Copy the client ID and secret.

### 2. Install and configure

From the `server` folder:

```bash
python -m venv .venv
```

```bash
.venv/Scripts/python -m pip install -r requirements.txt
```

```bash
cp .env.example .env
```

Then put the client ID and secret in `server/.env`. On macOS or Linux, use `.venv/bin/python` instead.

### 3. Run

```bash
.venv/Scripts/python -m uvicorn calmfeed.main:app --port 8000
```

Open <http://localhost:8000>. Use `localhost`, not `127.0.0.1`, or Google will reject the redirect.

Google warns that the app isn't verified, because it's your own private client. Choose **Continue**.

## Good to know

- **Weekly sign-in.** While your Google client's publishing status is *Testing*, Google expires its tokens after 7 days, so you'll be asked to sign in again.
- **Quota.** A digest costs about 1 unit per 50 subscriptions plus 1 per 50 recent videos, out of a default 10,000 a day. Video listings come from free channel RSS.
- **Tokens.** Your Google tokens are stored unencrypted in `server/data/calmfeed.db`. The app only requests read-only access. Keep it on your own machine, and don't expose it to a network without adding HTTPS and encrypting them.
- **Timezone.** The reset uses this machine's timezone unless you set `CALM_TIMEZONE`.

## Tests

```bash
.venv/Scripts/python -m pytest
```

Where this differs from the spec, and why: [docs/adr/0001-youtube-web-mvp.md](docs/adr/0001-youtube-web-mvp.md).
