# Calm Feed — Architecture & Build Spec

Nov 1, 2026 · @Aidan Jones

## Overview

Calm Feed (working name) is an open-source, self-hostable app that sits over your existing YouTube, Instagram, Facebook, X and Feedly. You can open it as often as you like. The feed is a short daily digest of what the people you follow are talking about most. Once its time is up, the feed simply isn't there. Search and your saved library stay available all day, with nothing pushed at you. Anything you save, from any platform, lands in one library that groups itself by topic. It's built in Flutter, with one codebase for web, iOS and Android, plus a small backend.

**Principles**

- **You own the algorithm.** Ranking and filtering rules are a plain-text file the user can read, edit and share. Nothing is ranked by engagement.
- **Transparent by default.** Every item shows a one-line reason it is on screen, traced to a rule.
- **Budgeted, not banned.** Browsing is allowed, within a daily limit that the app enforces server-side, so it can't be dodged by reinstalling or switching devices.
- **Purpose over engagement.** Once feed time is spent, the app becomes a tool: you search or open your saved list, you watch, it ends. No autoplay, no suggestions, no infinite scroll anywhere, ever.
- **Shareable.** Follow lists, rule packs and saved collections can be shared, so friends get a good starting setup without building it themselves.

**Non-goals for v1**

- Building a new social network. You keep your existing accounts, friends and follows.
- Posting, commenting or messaging in v1. The overlay leaves those parts of each site as they are.
- Downloading videos or stripping ads (that breaks platform terms).

## Core modes

The app is always available. The feed is a 30-minute daily digest of what people you follow are talking about most. When the time is up, or the digest runs out, you only see your saved library until the next reset. Nobody can see everything, and the design accepts that on purpose, to stop burnout.

| Area | Available | What you see | Never shown |
| --- | --- | --- | --- |
| Daily digest | Until 30 min is used (one budget across all platforms) or the digest runs out | The most-discussed posts, links and videos among people you follow, across platforms, ranked by how many of them shared or talked about each. Where that can't be computed (Instagram, Facebook), the Following view, inside the same budget | Reels, Shorts, For You, Explore, suggested posts, trending, anything from strangers |
| Saved library | Always | Everything you saved from any platform, grouped by topic automatically | Anything you didn't save |
| Save button | Always, on every post and video | One tap, including in the last second of digest time | n/a |
| Search | Off after the budget by default; turn on with `after_budget: saved_and_search` | Each platform's search for a specific need (e.g. a DIY fix), with no recommendations around it | Related videos, autoplay |
| After the digest | Until the next reset | "That's today's digest" + your saved library | Any feed |

**How the digest is ranked** (all of it shown to the user, and set in `rules.yaml`)

1. Collect posts, links and videos from people you follow over the last \~36 hours.
2. Merge the same thing across platforms by canonical URL or video ID, so a video shared on X, Bluesky and Feedly counts as one item.
3. Score = how many *distinct* people you follow posted, reposted, quoted or replied about it, with a recency decay. You can optionally weight close friends higher. Likes from strangers, global popularity and watch-time are never used.
4. Diversity: at most 2 items per source, and no topic group can fill more than a quarter of the digest.
5. Cap the digest at 40 items. It ends with "That's what's worth seeing today", not more content.
6. Every card shows its reason, e.g. "Shared by 5 people you follow: Sam, Priya, +3".

**Where the signal comes from:** API-connected sources (YouTube, Feedly, Bluesky, Mastodon, and X if you pay for its API) give full shares-by-follows data. On Instagram and Facebook there's no API, so buzz is only counted from what the overlay sees in your Following feed. Those platforms show as their own Following section in the digest, within the same 30 minutes.

**Follow suggestions (you stay in control)**

- Suggestions come only from your network, never from global popularity. For example: "4 people you follow shared this creator's videos this week".
- At most 3 a day, shown together at the end of the digest, never mixed into it. They can be switched off entirely.
- Each one shows the reason, which of your follows shared them, three recent posts, and their guard scores (below).
- Choices: **Follow** (you tap it yourself on that platform; Calm Feed never follows anyone for you), **Try for 7 days** (on Bluesky/Mastodon/Feedly it unfollows automatically unless you keep it; elsewhere you get a reminder), **Not now**, **Never suggest**.
- Every follow, unfollow and dismissal is logged, so you can see how your follow list changed and why.

**Outrage and hype guard**

- A small classifier (local model) scores every digest candidate and every suggested account on anger-bait, clickbait, fear/hype and engagement-bait. Network signals count too: a post getting far more quote-dunks than reposts is usually a pile-on.
- It aims to tell *upsetting but substantive* (serious news, a careful critique) apart from *built to provoke* (insults, us-vs-them framing, all-caps, "you won't believe"). Only the second is held back.
- What happens to flagged items is your call: hide (default), down-rank, or just label. Accounts that are flagged often are never suggested.
- Nothing disappears silently. The digest ends with "Held back today: 6" and a titles-only list with the reason for each. You can mark any of them "not outrage", which adjusts your threshold.
- Scores, the phrases that triggered them, and the model version are visible on every item. Like any classifier it will make mistakes, so the label and the log matter as much as the filter.

**Mute controls (two taps from any card)**

- Every card has a **Don't show me this** menu with three choices: *these keywords* (pre-filled from the title, editable), *this account*, or *this underlying source*.
- **Underlying source** means where it really comes from, not who passed it on. A Daily Mail link shared by a friend on Facebook, quoted on X and posted to Feedly is muted everywhere by muting `dailymail.co.uk` once. The same goes for a YouTube channel behind a re-uploaded clip, or the original account behind a quote-post.
- Mutes apply across all platforms and in the digest, suggestions and search. Muting a source doesn't unfollow the friend who shared it.
- Duration: forever (default), 30 days or 7 days. Useful for things like "election" or "spoilers".
- Matching: whole words and phrases, case-insensitive, checked against title, text, link preview and channel name. An optional *topic mute* also catches close variants by meaning (embedding similarity), and shows what it caught.
- A single **Mutes** screen lists every keyword, account and source, with how many items each held back this week, and a one-tap undo. Muted items are counted in "Held back today" with the reason, e.g. "muted source: dailymail.co.uk".
- Mute lists can be shared and imported like rule packs (e.g. a friend's "no tabloids" list).

**Behaviour rules**

1. Feed time is one budget shared across all platforms. It counts foreground time in the digest or on any platform's feed. Idle time doesn't count, and neither does time in Saved (or in search, if enabled). It resets at a user-set hour (default 04:00 local).
2. When the time hits zero, or the digest runs out, the feed is removed with one calm screen. There's no "5 more minutes" button. A looser budget takes effect from the next day, while a stricter one applies immediately.
3. Saving is always allowed, right up to the last second. That's the release valve: anything worth a proper look goes into Saved instead of keeping you scrolling.
4. Search, if enabled after the digest, is pull-only: results appear only for what you typed, with no "more like this" and no next page beyond the cap.
5. Any video, from the digest, search or saved, ends on our own end screen, never on a next video.
6. Every card carries a `why` line, e.g. "Shared by 4 people you follow", "followed: Paul Davids", "saved 2 Nov".

**Sharing**

- **Follow lists:** export who you follow across platforms as one list (YouTube channels, X and Instagram accounts, Facebook pages, Feedly OPML, Bluesky). Someone importing it gets one-tap follow links per platform, and on Feedly and Bluesky the follows can be added for them via API.
- **Rule packs:** your filters and budget settings, minus anything personal.
- **Saved groups:** share a group (e.g. "Guitar: barre chords") as a public read-only list with a link.

## Architecture

&#91;embedded content: system architecture · clients, backend, sources\]

The Flutter clients hold no rules and no timer. They send heartbeats and render whatever the server returns, which is why switching device or reinstalling can't reset the budget. Video plays directly from YouTube's official player inside the client. The server only supplies video IDs.

## How it sits over each platform

Every platform gets the **overlay**: your own logged-in session, with a per-site adapter that hides the algorithmic surfaces, times the feed and adds a Save button. Where a usable API exists, an optional **API connector** can also feed the server directly.

| Platform | Overlay (always) | API connector (optional) | Notes |
| --- | --- | --- | --- |
| YouTube | Open on Subscriptions; hide home recommendations, Shorts, sidebar, end screens, autoplay | Channel RSS (free) + Data API search, \~100 searches/day per Google Cloud project by default ([quota](https://developers.google.com/youtube/v3/determine_quota_cost)) | Official player only |
| Instagram | Open on the Following feed; hide Reels, Explore, suggested posts | None. As far as we know, Meta offers no API to read your friends' home feed | Overlay only |
| Facebook | Open on Feeds › Friends; hide Reels, Watch, suggested groups and pages | None for the home feed | Overlay only |
| X | Open on Following; hide For You, Explore trends, "Who to follow" | Paid pay-per-use API, about $0.005 per post read with no free tier ([pricing guide](https://opentweet.io/how-to/x-api-pay-per-use-explained)), so \~300 posts/day is roughly $45/month | The overlay is free, so use it by default |
| Feedly | Keep your folders; hide trending and discovery panels | Feedly API: OAuth for a published app, or a personal developer token limited to \~250 requests/day that expires monthly ([RSS Guard docs](https://rssguard.readthedocs.io/en/latest/services/feedly.html)) | A good fit for API mode |
| Bluesky, Mastodon | Optional | Open APIs, free | Bonus sources |

**Site adapters are the fragile part.** Each is a small JS + CSS module per site: URL rules (e.g. redirect `/reels` to the Following feed), selectors to hide, and where to inject the Save button. Ship the selectors as versioned data files the community can update when a site changes its layout. Add a health check that blocks the feed (rather than silently showing the full algorithmic one) when an adapter breaks.

## Data model and rules file

Postgres for the server (SQLite allowed for single-user installs). Every item that's shown stores the rule that admitted it, which is what powers the `why` line and the audit log.

| Table | Key fields |
| --- | --- |
| `users` | id, email, timezone, reset\_hour, created\_at |
| `platforms` | user\_id, platform (youtube / instagram / facebook / x / feedly / bluesky / mastodon), mode (overlay / api), adapter\_version, api\_token\_ref? |
| `budgets` | user\_id, date, feed\_seconds\_allowed, feed\_seconds\_used, per\_platform\_json, exhausted\_at? |
| `sessions` | id, user\_id, platform, origin (feed / search / saved), started\_at, ended\_at, active\_seconds |
| `saved_items` | id, user\_id, platform, url, title, text, author, image\_url, saved\_from (feed / search), saved\_at, embedding vector, group\_id?, note? |
| `saved_groups` | id, user\_id, name, name\_source (auto / user), centroid vector, pinned, is\_public, share\_slug? |
| `follow_lists` | id, user\_id, name, items\_json (platform + handle/URL + label), is\_public, share\_slug |
| `rulesets` | id, user\_id, yaml, version, is\_active, shared\_slug? |
| `items`, `feed_entries`, `sources` | API-connector mode only: fetched posts and the rule that admitted each |
| `audit_log` | user\_id, ts, event (feed\_exhausted, rule\_changed, item\_saved, adapter\_broken), detail\_json |

**Auto-grouping the saved library**

1. On save, build text from the title, description / post text and author, then embed it with a small local model (pgvector for storage).
2. If the item is close enough to an existing group's centroid, it joins that group. Otherwise it goes to Inbox.
3. A nightly job re-clusters Inbox plus recent items (HDBSCAN), and a small LLM names any new group. Existing group IDs are kept, and names the user edited are never changed.
4. Users can rename, merge, split and pin groups, or drag an item between them, and those moves train the assignment. Each item shows why it's in its group ("similar to: barre chord tips, F major shapes").
5. Export everything as Markdown or JSON at any time.

**Suggestions and guard tables:** `suggestions` (account, platform, reason\_json, follows\_sharing\_count, guard\_scores, status: shown / trial / followed / dismissed / never, decided\_at), \`mutes\` (user\_id, kind: keyword / account / source / topic, value, platform?, expires\_at?, created\_from\_item?, held\_back\_count) and `item_scores` (item\_id, outrage, clickbait, hype, engagement\_bait, quote\_ratio, top\_signals, model\_version, user\_override?).

**Sending saves to Zotero and Obsidian**

Every save can also go to your knowledge base automatically, or only for chosen groups. Calm Feed stays the inbox; Zotero and Obsidian are where things live long-term.

| Target | How | What lands there |
| --- | --- | --- |
| Zotero | Server-side push through the Zotero Web API using your API key (write access to your library or a group library) | One item per save, typed to match: video recording for YouTube, blog post / web page for articles, forum post for social posts. Calm Feed group becomes a Zotero collection; group name, platform and "shared by" become tags; your note and the `why` line go into a child note. Duplicates are skipped by URL |
| Obsidian | A small Calm Feed **Obsidian plugin** (TypeScript) that pulls new saves from `/v1/saved?since=` and writes Markdown into your vault. It works on desktop and mobile Obsidian, and needs no server access to your files | One note per save in `Calm Feed/<group>/`, with YAML frontmatter (url, platform, author, saved\_at, group, tags, zotero\_key if synced), the post text or a Readability extract, your note, and `[[group]]` links so groups show up in the graph. A daily `Calm Feed/Digest YYYY-MM-DD.md` lists what you saved that day |

- Sync is one-way by default (Calm Feed → Zotero/Obsidian). Renaming a group renames the Zotero collection and the Obsidian folder, and deleting a save in Calm Feed never deletes anything in your knowledge base.
- Fallback for Obsidian without the plugin: a nightly Markdown export to a folder you sync yourself (Syncthing, Git, iCloud).
- Rules decide what syncs, e.g. only groups you pin, or only saves you add a note to.

**Rules file (`rules.yaml`)**: human-readable and versioned, with diffs shown in the app. A change applies from the next reset unless it makes the rules *stricter*.

```yaml
version: 1
budget:
  feed_minutes: 30              # one budget across all platforms
  reset_hour: 4
after_budget: saved_only        # or: saved_and_search
feed:
  order: network_buzz           # or: chronological
  window_hours: 36
  digest_max_items: 40
  max_per_source: 2
  close_friends_weight: 1.5
  hide_shorts: true
  exclude_keywords: [reaction, drama, prank]
search:
  results_max: 8
  hide_shorts: true
  purpose_check: off            # on = ask for a purpose, hide off-topic
suggestions:
  enabled: true
  max_per_day: 3
  min_follows_sharing: 3
  placement: end_of_digest
  trial_follow_days: 7
mute:
  keywords: [crypto, "transfer rumour"]
  accounts: ["x:@someaccount"]
  sources: [dailymail.co.uk, "youtube:UCxxxxxxxx"]
  topics: []                    # meaning-based, optional
  temporary:
    - {keyword: election, until: 2026-12-01}
guard:
  outrage_action: hide          # or: downrank, label
  outrage_threshold: 0.6
  clickbait_action: downrank
  show_held_back: titles_only
saved:
  auto_group: true              # your renames and moves always stick
  pinned_groups: [Guitar, DIY]
export:
  zotero:
    enabled: true
    library: user               # or: group:<id>
    groups: pinned              # or: all, or a list
  obsidian:
    enabled: true
    folder: "Calm Feed"
    daily_note: true
share:
  pack_name: "DIY + guitar"
```

## API surface

REST + JSON over HTTPS, auth via OAuth (Google / Apple sign-in) or email magic link, short-lived JWTs. The server is the source of truth for the budget, so clients only report activity and render what they're given.

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/v1/state` | `feed_available`, seconds left (total and per platform), reset time, rules version, adapter versions |
| POST | `/v1/heartbeat` | Every 15 s from the extension or app: `{platform, origin, session_id, active}`. The server decrements feed time only for `origin=feed` |
| POST | `/v1/capture` | The Save button: `{platform, url, title, text, author, image_url, saved_from}`. Returns the assigned group |
| GET / PATCH / DELETE | `/v1/saved`, `/v1/saved/{id}` | List, search (keyword + semantic), move between groups, add a note, delete |
| GET / PATCH / POST | `/v1/groups`, `/v1/groups/{id}`, `/v1/groups/merge` | List groups, rename, pin, merge, split, share publicly |
| GET / POST / PUT | `/v1/follow-lists` | Create, edit, publish and import follow lists; import returns per-platform follow links |
| GET | `/v1/adapters/{platform}` | Latest site-adapter data (selectors, URL rules) for that platform |
| GET | `/v1/feed?cursor=` | API-connector mode only (YouTube RSS, Feedly, Bluesky, Mastodon). `410 feed_exhausted` at zero |
| GET / PUT | `/v1/rules`, `/v1/rules/diff` | Read / replace `rules.yaml` (JSON Schema validated), view diffs between versions |
| POST / GET | `/v1/packs`, `/v1/packs/{slug}` | Publish / import a rule pack |
| GET | `/v1/audit?since=` | Transparency log |

Endpoints \`GET /v1/suggestions\` and \`POST /v1/suggestions/{id}\` (follow / trial / not\_now / never) serve suggestions, and \`POST /v1/scores/{item}/override\` marks a false positive. \`GET / POST / DELETE /v1/mutes\` manages mutes, and every feed, digest, suggestion and search call applies them server-side. Each item records its canonical source domain or channel on capture, so source mutes work however it was shared. Background workers: a digest ranker and guard scorer (every \~2 h), an embed-and-group worker (on save, plus a nightly re-cluster), an optional API poller (every 30–60 min per source), a metadata enricher (`videos.list` for duration and Shorts flag), and a daily reset job per timezone.

## Platform specifics

On desktop, the overlay is a browser extension running on the real sites. On phones, it's the Flutter app opening each site's mobile web inside its own web views, with the native apps shielded so that's the way in. The same site-adapter files drive both.

| Client | What it is | Blocking the native apps | Notes |
| --- | --- | --- | --- |
| Browser extension | WebExtension for Chrome, Edge and Firefox (Safari via Apple's converter). Injects the site adapters into youtube.com, instagram.com, facebook.com, x.com, feedly.com, and adds the Save button and countdown | Not needed: it controls the sites directly | The best experience, and the least fragile overall |
| iOS app | Flutter app, iOS 16+. One tab per platform using `flutter_inappwebview` with the adapters injected, plus Saved library, follow lists and settings | Screen Time: FamilyControls + ManagedSettings shields on YouTube, Instagram, Facebook, X and Feedly ([plugin](https://pub.dev/packages/flutter_family_controls)) | Needs Apple's Family Controls distribution entitlement for TestFlight/App Store ([write-up](https://dev.to/eniolaajani/building-a-custom-screen-time-flutter-app-with-ios-native-apis-4k9f)). Real device only |
| Android app | Same Flutter app | Kotlin plugin: `UsageStatsManager` to detect the native apps, plus an overlay that bounces you to Calm Feed | Play restricts Accessibility API use, so check current policy. Fallback: Digital Wellbeing timers |
| Web app | Flutter web: Saved library, groups, follow lists, rules and packs. It doesn't show feeds itself | n/a | Also hosts the public pages for shared follow lists and groups |

**Shared Flutter stack:** Riverpod, go\_router, dio, `flutter_inappwebview`, `youtube_player_iframe` (API mode), drift (offline copy of the saved library), `flutter_secure_storage`. Logins stay in the web views' own cookie stores on the device. Calm Feed's server never sees platform passwords.

Blocking is opt-in, but on a phone it's what makes Calm Feed the *only* door into these platforms.

## Build plan for the coding agent

Build in seven milestones, each usable on its own. Start on desktop (extension + web app), since that's the quickest way to live with it daily, and do phones last. The backend can be Go or Python/FastAPI (Python is easier for the ML pieces). Everything runs with `docker compose up` on one box.

**Repo layout**

```
calm-feed/
  server/          # API, budget engine, digest ranker, connectors, migrations
  extension/       # WebExtension (TypeScript): overlay, Save button, countdown
  adapters/        # per-site selector + URL-rule data, shared inject script
  app/             # Flutter (iOS, Android, web)
  plugins/
    screen_shield/ # Flutter plugin: Swift (FamilyControls) + Kotlin (UsageStats)
  ml/              # embeddings, clustering, guard classifier, eval sets
  packs/           # example rule packs and follow lists
  docs/            # this spec, ADRs
  docker-compose.yml
```

**Milestones**

1. **Save + library.** Web app and browser extension with a Save button on YouTube and X; `/v1/capture`; saved library with search; auto-grouping v1; Zotero push and the Obsidian plugin.
   - Done when: saving takes one click on both sites; 50 saved items land in sensible groups; a renamed group keeps its name after the nightly re-cluster.
2. **Desktop overlay.** Site adapters for YouTube, Instagram, Facebook, X and Feedly: open on the following views and hide algorithmic surfaces. Add a health check for each adapter.
   - Done when: no Reels, Shorts, For You, Explore or suggested panels are visible on any of the five; a broken selector shows "adapter needs updating" and closes the feed instead of showing the full one.
3. **Budget.** Heartbeats, one shared 30-minute budget, the after-digest screen, saved-only mode, and the "stricter now, looser tomorrow" rule.
   - Done when: with a 2-minute test budget, every open site closes its feed at zero in two browsers at once, the saved library still works, and time spent in Saved doesn't count.
4. **Digest ranker.** Connectors (YouTube RSS, Feedly, Bluesky, Mastodon; X optional), cross-platform URL merge, shares-by-follows scoring, diversity caps, a 40-item cap, a reason on every card; overlay-observed signals for Instagram and Facebook.
   - Done when: a video shared by 3 follows across two platforms appears once as "Shared by 3 people you follow", and no card is missing a reason.
5. **Guard + suggestions.** Guard classifier with a held-back list and overrides; follow suggestions from the network with reasons, trial follows on open APIs, and a follow-change log.
   - Done when: guard precision and recall on a labelled set the user builds from their own feeds are shown in the app; there are never more than 3 suggestions a day, each with a reason; nothing is followed without a tap.
6. **Sharing.** Follow lists, rule packs and public saved groups, with import producing per-platform follow links.
   - Done when: a friend imports a follow list and ends up following the same YouTube channels and Bluesky accounts in a few taps.
7. **Phones.** Flutter app with wrapped web views running the same adapters, plus the `screen_shield` plugin on iOS and Android.
   - Done when: on a real iPhone the native apps are shielded and the whole flow (digest, save, saved-only after 30 min) works end to end; the same holds on Android.

**Agent ground rules**

- Never add autoplay, infinite scroll, streaks, badges or "new content" notifications, even as options.
- Never rank or suggest by engagement, watch-time or global popularity. Every ranked item and every suggestion must carry a non-empty reason; add a test that fails otherwise.
- The budget is enforced only on the server. The client never decides whether the feed is open.
- Never follow, unfollow, post or like on the user's behalf without an explicit tap. Trial-follow expiry on open APIs is the one exception, and only when the user opts in.
- Never send platform passwords or cookies to the server.
- Use only the official YouTube player. Never strip ads or download videos.
- Write an ADR in `docs/` for any deviation from this spec. Keep a THIRD\_PARTY\_NOTICES file up to date, and never copy GPL code into the MIT/Apache codebase.

## Prior art and what we can reuse

Nobody combines all of this, but several open-source projects cover pieces. License Calm Feed under **MIT or Apache-2.0**. MIT and Apache code can then be reused with attribution in a `THIRD_PARTY_NOTICES` file, and GPL code is read for ideas only, never copied in.

| Project | What it does | License | How we use it |
| --- | --- | --- | --- |
| [News Feed Eradicator](https://addons.mozilla.org/en-US/firefox/addon/news-feed-eradicator/versions) | Extension that removes feeds on Facebook, X, Instagram, YouTube, LinkedIn, Reddit, HN, and recently Threads and Bluesky | MIT | **Reuse.** Its per-site selectors and extension scaffolding are the closest thing to our site adapters. Fork the site-detection and hide logic, then add our budget, Save button and following-view redirects |
| [Unhook NG](https://addons.mozilla.org/addon/unhook-ng/) | Fine-grained YouTube clean-up: home feed, sidebar, Shorts, end screens, autoplay, redirect to Subscriptions | GPL-3.0 | **Reference only.** It shows which YouTube elements to target. Write our own selectors (or license the extension as GPL) |
| [Gobo](https://awesome.ecosyste.ms/projects/github.com%2Fmitmedialab%2Fgobo) (MIT Media Lab) | Aggregator with user-set filters (rudeness, seriousness, virality) that shows why each post was kept or hidden | MIT | **Design reuse.** Its "why shown / why hidden" UI and rules model match ours. The code is dated (last pushed 2022, dead Twitter/Facebook APIs), so borrow patterns rather than code |
| [Tapestry connectors](https://github.com/TheIconfactory/Tapestry) | JavaScript connectors for YouTube, Bluesky, Mastodon, Reddit, RSS used by the Tapestry iOS app (the app itself isn't open source) | MIT | **Port the parsing logic.** Feed URL discovery and item parsing for YouTube, Bluesky and Mastodon save time, though they target Tapestry's runtime API, so they'd need adapting |
| [Detoxify](https://awesome.ecosyste.ms/projects/github.com%2Funitaryai%2Fdetoxify) | Open toxicity classifiers (toxic, insult, threat, identity attack), multilingual model available | Apache-2.0 | **Reuse as one guard signal**, run locally. It detects toxicity, not hype or clickbait, and its authors warn of bias against some groups, so combine it with our own outrage/clickbait model and the quote-ratio signal |
| [Bluesky feed-generator starter kit](https://www.bskyinfo.com/sdks/bluesky-social-feed-generator/) | Reference server for publishing a custom Bluesky feed | MIT | **Optional reuse** to publish your digest as a Bluesky custom feed for friends |
| Perspective API (Google Jigsaw) | Hosted toxicity scoring | Proprietary | **Don't use.** [It shuts down on 31 December 2026](https://perspectiveapi.com/) |
| Graze | No-code custom feed builder for Bluesky, now owned by Flipboard | Proprietary | Not reusable, but a good reference for a rules UI |

**Standard building blocks** (well-known permissive licenses, but check each LICENSE before vendoring): sentence-transformers for embeddings, BERTopic + HDBSCAN for auto-grouping, Mozilla Readability for clean text when saving web pages, pgvector for vector search.

## Open questions and risks

- [ ] **App Store review:** an iOS app that mainly wraps Instagram, Facebook and X web may get pushback. Start with TestFlight for yourself and friends, and apply for the Family Controls entitlement early.
- [ ] **Platform terms:** hiding page elements in your own browser is common (Unhook-style extensions). Reading what the overlay shows to count buzz stays on-device, but check each site's terms before releasing publicly.
- [ ] **X API:** pay for it (roughly $45/month at \~300 posts/day) for full buzz signal, or use the overlay only?
- [ ] **Guard strictness:** how strict should the default be, and who labels the first evaluation set?
- [ ] **After the digest:** saved-only by default, or allow search for practical needs (DIY, guitar)?
- [ ] **Instagram and Facebook buzz** is limited to what you scroll past. Is a plain Following section good enough there?
- [ ] **Hosted instance:** YouTube search quota and the X API are per project, so a shared public instance needs per-user keys.
- [ ] **Name:** "Calm Feed" is a placeholder.

**Risk:** Sites change their layouts and break adapters. Mitigation: health checks that close the feed rather than leak the algorithmic one, plus community-updatable selector files. Separately, if the YouTube player starts forcing related videos, we own the end screen and overlay it on the `ended` event regardless.

## Sources

- [YouTube Data API quota costs (Google)](https://developers.google.com/youtube/v3/determine_quota_cost)
- [X API pay-per-use explained (OpenTweet)](https://opentweet.io/how-to/x-api-pay-per-use-explained)
- [Feedly service docs (RSS Guard)](https://rssguard.readthedocs.io/en/latest/services/feedly.html)
- [flutter\_family\_controls plugin (pub.dev)](https://pub.dev/packages/flutter_family_controls)
- [Building a custom Screen Time Flutter app with iOS native APIs (DEV)](https://dev.to/eniolaajani/building-a-custom-screen-time-flutter-app-with-ios-native-apis-4k9f)
- [HackerTube, about](https://hackertube.org/about)
