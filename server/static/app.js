// Calm Feed client. It holds no rules and no budget clock: it reports activity
// and renders what the server says. Whether the feed is open is never decided here.
"use strict";

const IDLE_AFTER_MS = 60_000;

const view = document.getElementById("view");
const bar = document.getElementById("bar");
const timeLeft = document.getElementById("time-left");
const navDigest = document.getElementById("nav-digest");
const navSaved = document.getElementById("nav-saved");

const app = {
  page: "digest",        // digest | saved
  origin: "feed",        // what the heartbeat reports: feed | saved
  budget: null,
  savedUrls: new Set(),
  player: null,
  playing: false,
  heartbeatTimer: null,
  lastInput: Date.now(),
  sessionId: crypto.randomUUID(),
};

function el(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (key === "onclick" || key === "onsubmit") node[key] = value;
    else if (key === "class") node.className = value;
    else if (key === "text") node.textContent = value;
    else node.setAttribute(key, value);
  }
  node.append(...children.filter(Boolean));
  return node;
}

function show(...nodes) {
  view.replaceChildren(...nodes.filter(Boolean));
  window.scrollTo(0, 0);
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: options.body ? { "Content-Type": "application/json" } : {},
  });
  if (response.status === 401) {
    signedOut();
    throw new Error("signed_out");
  }
  return response;
}

// --- Budget ----------------------------------------------------------------

function applyBudget(budget) {
  app.budget = budget;
  const minutes = Math.ceil(budget.seconds_left / 60);
  timeLeft.textContent = budget.feed_available ? `${minutes} min left today` : "Digest closed";
  if (!budget.feed_available && app.origin === "feed") {
    closePlayer();
    renderDigestClosed();
  }
}

function isActive() {
  if (document.visibilityState !== "visible") return false;
  return app.playing || Date.now() - app.lastInput < IDLE_AFTER_MS;
}

async function sendHeartbeat() {
  const response = await api("/v1/heartbeat", {
    method: "POST",
    body: JSON.stringify({
      platform: "youtube",
      origin: app.origin,
      session_id: app.sessionId,
      active: isActive(),
    }),
  });
  if (response.ok) applyBudget(await response.json());
}

function startHeartbeat(seconds) {
  clearInterval(app.heartbeatTimer);
  app.heartbeatTimer = setInterval(() => sendHeartbeat().catch(() => {}), seconds * 1000);
}

for (const event of ["pointerdown", "pointermove", "keydown", "scroll"]) {
  window.addEventListener(event, () => { app.lastInput = Date.now(); }, { passive: true });
}

// --- Cards -----------------------------------------------------------------

function formatDuration(seconds) {
  if (!seconds) return "";
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = String(seconds % 60).padStart(2, "0");
  return h ? `${h}:${String(m).padStart(2, "0")}:${s}` : `${m}:${s}`;
}

function saveButton(item) {
  const saved = app.savedUrls.has(item.url);
  const button = el("button", { type: "button", text: saved ? "Saved" : "Save" });
  button.disabled = saved;
  button.onclick = async () => {
    button.disabled = true;
    const response = await api("/v1/capture", {
      method: "POST",
      body: JSON.stringify({
        platform: "youtube",
        url: item.url,
        title: item.title,
        text: item.text,
        author: item.author,
        image_url: item.image_url,
        saved_from: "feed",
      }),
    });
    if (response.ok) {
      app.savedUrls.add(item.url);
      button.textContent = "Saved";
    } else {
      button.disabled = false;
    }
  };
  return button;
}

function card(item, origin, extraAction) {
  const open = () => openVideo(item, origin);
  const duration = formatDuration(item.seconds);
  return el("article", { class: "card" },
    el("button", { class: "thumb", type: "button", onclick: open, "aria-label": `Play ${item.title}` },
      el("img", { src: item.image_url, alt: "", loading: "lazy" }),
      duration && el("span", { class: "duration", text: duration })),
    el("div", { class: "body" },
      el("button", { class: "title", type: "button", onclick: open },
        el("h2", { text: item.title })),
      el("div", { class: "quiet", text: item.author }),
      el("div", { class: "quiet", text: item.why }),
      el("div", { class: "actions" }, origin === "feed" ? saveButton(item) : null, extraAction)));
}

// --- Digest ----------------------------------------------------------------

function renderHeldBack(heldBack) {
  if (!heldBack.length) return null;
  return el("details", {},
    el("summary", { text: `Held back today: ${heldBack.length}` }),
    el("ul", {}, ...heldBack.map((item) =>
      el("li", { text: `${item.title} (${item.channel}): ${item.why}` }))));
}

function resetTime() {
  return new Date(app.budget.reset_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function renderDigestClosed() {
  setNav("digest");
  show(el("section", { class: "calm" },
    el("h1", { text: "That's today's digest" }),
    el("p", { class: "quiet", text: `It's back at ${resetTime()}. Your saved videos are here whenever you want them.` }),
    el("div", { class: "actions" },
      el("button", { class: "primary", type: "button", text: "Open Saved", onclick: openSaved }))));
}

function renderProblem(title, detail) {
  show(el("section", { class: "calm" },
    el("h1", { text: title }),
    el("p", { class: "quiet", text: detail }),
    el("div", { class: "actions" },
      el("button", { type: "button", text: "Try again", onclick: openDigest }))));
}

async function openDigest() {
  closePlayer();
  setNav("digest");
  app.origin = "feed";
  show(el("p", { class: "quiet", text: "Gathering today's digest…" }));

  const [feed, saved] = await Promise.all([api("/v1/feed"), api("/v1/saved")]);
  if (saved.ok) app.savedUrls = new Set((await saved.json()).items.map((item) => item.url));
  if (feed.status === 410) return renderDigestClosed();
  if (!feed.ok) {
    return renderProblem("Couldn't reach YouTube",
      "Today's digest hasn't been built yet. Nothing was used from your time.");
  }

  const digest = await feed.json();
  const failed = digest.channels_failed
    ? el("p", { class: "quiet", text: `${digest.channels_failed} of ${digest.channels_total} channels couldn't be reached today.` })
    : null;
  const heading = digest.items.length
    ? el("h1", { text: "Today's digest" })
    : el("h1", { text: "Nothing new from your subscriptions" });

  show(
    heading,
    failed,
    ...digest.items.map((item) => card(item, "feed")),
    el("div", { class: "ending" }, el("p", { text: "That's what's worth seeing today." })),
    renderHeldBack(digest.held_back),
  );
}

// --- Saved -----------------------------------------------------------------

async function openSaved() {
  closePlayer();
  setNav("saved");
  app.origin = "saved";
  const input = el("input", { type: "search", placeholder: "Search your saved videos", "aria-label": "Search saved videos" });
  const results = el("div");

  const load = async () => {
    const response = await api(`/v1/saved?q=${encodeURIComponent(input.value)}`);
    if (!response.ok) return;
    const { items } = await response.json();
    if (!input.value) app.savedUrls = new Set(items.map((item) => item.url));
    if (!items.length) {
      results.replaceChildren(el("p", { class: "quiet", text: input.value ? "No matches." : "Nothing saved yet." }));
      return;
    }
    results.replaceChildren(...items.map((item) => card(item, "saved",
      el("button", {
        type: "button", class: "link", text: "Remove",
        onclick: async () => {
          await api(`/v1/saved/${item.id}`, { method: "DELETE" });
          app.savedUrls.delete(item.url);
          load();
        },
      }))));
  };

  show(
    el("h1", { text: "Saved" }),
    el("form", { class: "search", onsubmit: (event) => { event.preventDefault(); load(); } },
      input, el("button", { type: "submit", text: "Search" })),
    results,
  );
  await load();
}

// --- Player ----------------------------------------------------------------

let youtubeApi;
function loadYouTubeApi() {
  youtubeApi ??= new Promise((resolve) => {
    window.onYouTubeIframeAPIReady = () => resolve(window.YT);
    document.head.append(el("script", { src: "https://www.youtube.com/iframe_api" }));
  });
  return youtubeApi;
}

function backToList(origin) {
  return origin === "feed" ? openDigest() : openSaved();
}

async function openVideo(item, origin) {
  closePlayer();
  app.origin = origin;
  const mount = el("div", { id: "player" });
  show(
    el("div", { class: "player-frame" }, mount),
    el("section", { class: "player-meta" },
      el("h1", { text: item.title }),
      el("div", { class: "quiet", text: item.author }),
      el("div", { class: "quiet", text: item.why }),
      el("div", { class: "actions" },
        origin === "feed" ? saveButton(item) : null,
        el("button", { type: "button", text: "Back", onclick: () => backToList(origin) }))),
  );

  const YT = await loadYouTubeApi();
  if (!mount.isConnected) return;  // the user left while the API was loading
  app.player = new YT.Player(mount, {
    videoId: item.video_id,
    playerVars: { autoplay: 0, rel: 0, playsinline: 1, origin: location.origin },
    events: {
      onStateChange: (event) => {
        app.playing = event.data === YT.PlayerState.PLAYING;
        if (event.data === YT.PlayerState.ENDED) renderEndScreen(item, origin);
      },
    },
  });
}

// We own the ending: the player is torn down before it can offer a next video.
function renderEndScreen(item, origin) {
  closePlayer();
  show(el("section", { class: "calm" },
    el("h1", { text: "That's the end of the video" }),
    el("p", { class: "quiet", text: item.title }),
    el("div", { class: "actions" },
      origin === "feed" ? saveButton(item) : null,
      el("button", { class: "primary", type: "button", text: "Back", onclick: () => backToList(origin) }))));
}

function closePlayer() {
  app.playing = false;
  app.player?.destroy();
  app.player = null;
}

// --- Shell -----------------------------------------------------------------

function setNav(page) {
  app.page = page;
  navDigest.classList.toggle("current", page === "digest");
  navSaved.classList.toggle("current", page === "saved");
}

function signedOut() {
  closePlayer();
  clearInterval(app.heartbeatTimer);
  bar.hidden = true;
  const params = new URLSearchParams(location.search);
  const setup = params.has("setup") && el("div", { class: "notice" },
    el("p", { text: "Google sign-in isn't set up yet." }),
    el("p", { class: "quiet", text: "Add GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET to server/.env and restart. The README has the steps." }));
  const cancelled = params.has("signin") && el("p", { class: "quiet", text: "Sign-in was cancelled." });
  show(el("section", { class: "calm" },
    el("h1", { text: "Calm Feed" }),
    el("p", { class: "quiet", text: "A short daily digest of the YouTube channels you follow. Then it stops." }),
    setup,
    cancelled,
    el("div", { class: "actions" },
      el("a", { class: "button primary", href: "/auth/login", text: "Sign in with Google" }))));
}

navDigest.onclick = () => openDigest();
navSaved.onclick = () => openSaved();
document.getElementById("sign-out").onclick = async () => {
  await fetch("/auth/logout", { method: "POST" });
  location.href = "/";
};

async function start() {
  const response = await api("/v1/state");
  if (!response.ok) return;
  const budget = await response.json();
  bar.hidden = false;
  applyBudget(budget);
  startHeartbeat(budget.heartbeat_seconds);
  if (budget.feed_available) await openDigest();
}

start().catch((error) => {
  if (error.message !== "signed_out") renderProblem("Something went wrong", "The server didn't respond.");
});
