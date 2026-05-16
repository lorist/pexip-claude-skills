---
name: pexip-js-sdks
description: >
  Expert knowledge for choosing between, and building applications with, the
  two JavaScript SDK families that sit on top of the Pexip Infinity Client
  REST API: the **legacy `pexrtc.js`** browser wrapper (callback-based,
  loaded as a single `<script>` from a Conferencing Node) and the **modern
  `@pexip/*` npm packages** (`@pexip/infinity`, `@pexip/media`,
  `@pexip/components`, `@pexip/hooks`, `@pexip/media-processor`,
  `@pexip/plugin-api`, and the rest of the Webapp3 building blocks). Use
  this skill whenever the user is building a browser or React conference
  client, deciding between PexRTC and the modern stack, wiring
  `createInfinityClient` / `createInfinityClientSignals`, working with
  `@pexip/signal` (signals-and-slots, not RxJS, not Promises), composing
  the `@pexip/media` pipeline (camera/mic capture, background blur via
  `@pexip/media-processor`, device hot-swap via `@pexip/media-control`),
  porting from `pexrtc.js` to the npm packages, or troubleshooting why a
  React conference UI mounts but no media flows. Triggers for "PexRTC",
  "@pexip/infinity", "@pexip/media", "@pexip/components", "Pexip React",
  "Pexip Webapp3 building blocks", "Pexip JS SDK", "Pexip npm packages",
  "createInfinityClient", "infinityClient.call", "background blur Pexip",
  and "pexrtc.js makeCall". Use this skill — the two stacks are
  interchangeable in *what* they do but completely different in *how* you
  use them, and the official docs don't put them side by side.
---

# Pexip Infinity JavaScript SDKs — Expert Skill

There are **two ways** to talk to a Pexip conference from JavaScript without
hand-rolling the raw HTTP+SSE protocol:

| Stack | Distribution | Shape |
|---|---|---|
| **Legacy `pexrtc.js`** | `<script src="https://<conferencing-node>/static/webrtc/js/pexrtc.js">` | Single global `PexRTC` class, vanilla ES5, callback properties (`rtc.onConnect = fn`). |
| **Modern `@pexip/*` packages** | `npm install @pexip/infinity @pexip/media @pexip/components …` | TypeScript, ES modules, framework-agnostic core, React-first UI layer, signals-and-slots event model. |

Both ultimately speak the same Client REST API underneath — see the
`pexip-client-api` skill for the protocol-level model (`request_token`
lifecycle, SSE `participant_sync_*` brackets, direct vs transcoded media).
This skill is the SDK layer **above** that.

> If the user is building a **plugin for the stock Webapp3** (a button, a
> toast, a side panel that runs alongside Pexip's own UI), don't read
> further — that's `@pexip/plugin-api`, fully covered in the
> `pexip-webapp3-plugin` skill. This skill is for *replacing or rewriting*
> the conference UI itself.

---

## 1. Quick decision tree

| What you're building | Use |
|---|---|
| Quick browser PoC, kiosk, demo on a single Conferencing Node | **`pexrtc.js`** — zero build, one script tag, works offline of npm |
| Custom React conference UI with full control of layout | **Modern stack**: `@pexip/infinity` + `@pexip/media` + `@pexip/media-components` + `@pexip/components` |
| Custom UI in Vue / Svelte / vanilla TS | **Modern stack** but skip the React UI layers — `@pexip/infinity` + `@pexip/media` + `@pexip/peer-connection` are framework-agnostic |
| Background blur, denoise, virtual backgrounds | **Modern stack** — `@pexip/media-processor` (no PexRTC equivalent) |
| Hot-swap camera/mic mid-call without re-negotiating | **Modern stack** — `@pexip/media-control` (PexRTC needs a `renegotiate(false)` dance) |
| Adding UI to the stock Webapp3 (button, toast, panel) | Stop. Use `pexip-webapp3-plugin` skill. |
| Server-side bot, recorder, transcriber (Node, Python, Go) | Neither SDK — both are browser-only. Use the raw Client API (`pexip-client-api` skill). |
| Live read-only dashboard | Raw Client API SSE is enough. SDK is overkill. |
| Just typed bindings around `/api/client/v2/...` | `@pexip/infinity-api` (generated HTTP types only — no peer-connection, no signals) |

---

## 2. The two stacks at a glance

| Dimension | Legacy `pexrtc.js` | Modern `@pexip/*` |
|---|---|---|
| Language / build | Vanilla ES5, no transpile | TypeScript, ES modules, requires a bundler (Vite, Webpack) |
| Framework assumption | None — global `window.PexRTC` | Framework-agnostic core; React-first UI layer |
| Distribution | Self-hosted on every Conferencing Node | npm registry (some packages need GitHub-authenticated `.npmrc`) |
| State management | Internal to the PexRTC instance | Caller-owned (`useState`, signal subscriptions) |
| Event model | `rtc.onConnect = fn` (single assignment, last-write-wins) | `signal.add(cb)` returning a detach function (multiple subscribers) |
| WebRTC abstraction | Hidden inside PexRTC | `@pexip/peer-connection` wraps `RTCPeerConnection`; `MainPeerConnection` / `PresentationPeerConnection` |
| Background blur / effects | Not built-in | `@pexip/media-processor` (MediaPipe segmentation, AudioWorklet denoise) |
| Device hot-swap | `renegotiate(false)` after changing source | `@pexip/media-control` `setStream()` |
| Plugin / extension model | None | `@pexip/plugin-api` (covered by `pexip-webapp3-plugin` skill) |
| Versioning | Tracks the Conferencing Node it's hosted from | Independent npm semver |

---

## 3. Architecture: how the modern packages layer

The modern stack is 13+ packages. They are **not** a flat list — they sit in
roughly four tiers:

```
┌──────────────────────────────────────────────────────────────────┐
│  UI components & hooks                                           │
│  @pexip/components   (vanilla React UI primitives)               │
│  @pexip/hooks        (React hooks: useMediaStream, etc.)         │
│  @pexip/media-components  (Pexip-specific React components)      │
└─────────────────────────┬────────────────────────────────────────┘
                          │
┌─────────────────────────┴────────────────────────────────────────┐
│  Conference & media orchestration                                │
│  @pexip/infinity      (high-level client: createInfinityClient)  │
│  @pexip/media         (capture: getUserMedia + processor chain)  │
│  @pexip/media-processor   (background blur, denoise, effects)    │
│  @pexip/media-control     (device hot-swap, mute orchestration)  │
└─────────────────────────┬────────────────────────────────────────┘
                          │
┌─────────────────────────┴────────────────────────────────────────┐
│  Primitives                                                      │
│  @pexip/infinity-api  (generated TS bindings for /api/client/v2) │
│  @pexip/peer-connection  (RTCPeerConnection wrapper)             │
│  @pexip/signal        (signals-and-slots event system)           │
└──────────────────────────────────────────────────────────────────┘
```

Plus `@pexip/plugin-api` for the Webapp3 plugin sandbox (separate concern,
separate skill). See `references/modern-package-map.md` for one paragraph
per package and which depend on which.

The **two packages that get confused on day one** are `@pexip/infinity` and
`@pexip/infinity-api`:

- `@pexip/infinity-api` = autogenerated HTTP+SSE types (every `/api/client/v2`
  endpoint, no behaviour). Use this if you want raw fetch calls with
  TypeScript types — basically nothing else.
- `@pexip/infinity` = the **client** you actually use. Wraps the API,
  manages the token lifecycle, holds the peer connections, fires signals.

If you `npm install @pexip/infinity-api` and start writing code, you've
picked the wrong package.

---

## 4. Modern stack — minimal join flow

The canonical four-step pattern, which every tutorial on
`developer.pexip.com` boils down to:

```ts
import { createInfinityClient, createInfinityClientSignals, ClientCallType } from "@pexip/infinity";

// 1. Create the signals bundle. The client emits into these; you subscribe.
const signals = createInfinityClientSignals([]);

// 2. Wire the signals you care about BEFORE creating the client.
signals.onConnected.add(() => console.log("joined"));
signals.onPinRequired.add(() => promptUserForPin());      // see §7 gotcha #7
signals.onError.add(({ error }) => console.error(error));
signals.onParticipants.add(({ participants }) => render(participants));

// 3. Create the client. This does NOT join yet.
const infinityClient = createInfinityClient(signals);

// 4. Capture media (or pass a MediaStream you already have) and join.
const localStream = await navigator.mediaDevices.getUserMedia({ audio: true, video: true });
await infinityClient.call({
  conferenceAlias: "meet.alice",
  displayName:     "Bob",
  callType:        ClientCallType.AudioVideo,
  bandwidth:       1280,
  mediaStream:     localStream,
  node:            "conf.example.com",
});
```

Three things to internalise:

1. **Subscribe to signals before calling `call()`.** If you wire them after,
   you can miss the first `onConnected` / `onPinRequired` if the network is
   fast.
2. **`createInfinityClientSignals([])` takes an array of *additional* signals
   to register**, not an empty config. Pass `[]` for the defaults.
3. **Token refresh is automatic** — the client manages it. You don't need a
   `setInterval` loop. (Compare with the raw API where you do — see
   `pexip-client-api` skill §5.)

Disconnect is always `await infinityClient.disconnect({ reason: "..." })`.
Don't `release_token` directly — the client owns that.

For the React equivalent (with `useEffect` lifecycle and signal cleanup),
see `examples/react-infinity-minimal/`.

---

## 5. Legacy PexRTC — minimal join flow

```html
<!doctype html>
<html>
  <body>
    <video id="local"  autoplay muted playsinline></video>
    <video id="remote" autoplay      playsinline></video>
    <script src="https://conf.example.com/static/webrtc/js/pexrtc.js"></script>
    <script>
      const rtc = new PexRTC();
      rtc.onSetup   = (stream, pin_status) => {
        document.getElementById("local").srcObject = stream;
        rtc.connect(pin_status === "required" ? prompt("PIN?") : null);
      };
      rtc.onConnect = (stream) => {
        document.getElementById("remote").srcObject = stream;
      };
      rtc.onError      = (err)    => console.error(err);
      rtc.onDisconnect = (reason) => console.warn("bye:", reason);

      rtc.makeCall("conf.example.com", "meet.alice", "Bob", 1280);
    </script>
  </body>
</html>
```

That's a complete client. Three things to internalise:

1. **Two stages: `makeCall` then `connect`.** `makeCall` does media capture
   and signalling setup, then fires `onSetup`. You read `pin_status` /
   `conference_extension` / `idp_selection` from `onSetup` and call
   `connect()` with the appropriate args. **You can't pass the PIN to
   `makeCall` upfront.** This trips up everyone exactly once.
2. **Callbacks are properties, not subscriptions.** `rtc.onConnect = fn`
   replaces any previous handler. There's no `addEventListener` or array
   of listeners — assign one function per hook.
3. **PexRTC is global on `window` and CN-version-pinned.** Loading
   `pexrtc.js` from two different Conferencing Nodes in the same page (or
   loading it twice from the same node) gives you the wrong instance. The
   protocol the script speaks tracks the CN it came from.

The full PexRTC reference (every property, method, and callback) is in
`references/pexrtc-api.md`.

---

## 6. When to drop down to the raw Client API

The SDKs are convenient. They are also **opinionated** about lifecycle
(token refresh, reconnect, sync brackets). When you need to do something
the SDKs don't model — or when you want to debug what the SDK is doing —
read the raw protocol in the `pexip-client-api` skill. Common cases:

- Server-side bots, recorders, transcribers (no DOM available).
- Custom reconnect logic with your own backoff strategy.
- Polling `/conference_status` and `/participants` independently of the SDK.
- Implementing the Client API on a runtime PexRTC doesn't support
  (Node, Deno, mobile native).

Don't drop to the raw API just because something feels hidden — most
"hidden" things in the modern stack are exposed as signals if you look.
Read `references/signal-pattern.md` first.

---

## 7. Gotchas

A short, pointed list. The longer story for each is in the relevant
reference file.

1. **`@pexip/signal` is not RxJS, not Promises.** The API is
   `signal.add(cb)` returning a detach function. New devs reach for
   `.subscribe()` or `.then()` and find neither. Four signal variants
   (`Generic`, `Behavior`, `Replay`, `Batched`) behave differently for
   late subscribers — see `references/signal-pattern.md`.

2. **`@pexip/infinity-api` ≠ `@pexip/infinity`.** The first is generated
   types only. The second is the actual client. Picking the wrong one
   means rebuilding the call/signal layer yourself.

3. **Some `@pexip/*` packages need GitHub-authenticated npm install** —
   `@pexip/media-control` documents this explicitly and the same probably
   applies to others in the scope. Set up `.npmrc` with a GitHub token
   before `npm install`. Bare `npm install` in CI fails with 401.

4. **The effects pipeline replaces the stream, doesn't mutate it.**
   `videoProcessor.process(localStream)` returns a *new* `MediaStream`
   that you must hand to `infinityClient.call({ mediaStream })` or to
   `setStream()`. Forget that and you send the raw camera feed.

5. **Mobile browsers cannot send screen share.** Chrome on Android/iOS
   silently fails `getDisplayMedia()`. Detect platform and hide the
   button.

6. **Device hot-swap is BYO on PexRTC.** PexRTC requires
   `renegotiate(false)` after you change `audio_source` or `video_source`.
   The modern stack handles it inside `@pexip/media-control`'s
   `setStream()`.

7. **PIN flow is "fail then retry", not "pass upfront".** Both stacks:
   you start the join, the SDK reports `pin_status: "required"` (PexRTC's
   `onSetup`) or fires `onPinRequired` (modern), you collect the PIN, you
   *re-call* the connect/join function with the PIN. Treating PIN as a
   constructor/init argument silently drops it.

8. **CSS import is mandatory for `@pexip/components`.** Import
   `@pexip/components/dist/index.css` and `fonts.css` from your entry
   file. Skip them and components render unstyled with no warning.

9. **PexRTC `makeCall` and `connect` are two stages.** See §5. Most "my
   call connects but never enters the conference" bug reports are
   "forgot to call `rtc.connect()` from `onSetup`".

10. **Token refresh and reconnect aren't documented in the tutorials.**
    The raw lifecycle rules from the `pexip-client-api` skill still
    apply underneath both SDKs — most of the time the SDK handles it,
    but if your bot runs for 24h+ and starts dropping at hour 22, that's
    where to look.

---

## 8. Reference index

| File | Covers |
|---|---|
| `references/modern-package-map.md` | All 13 `@pexip/*` packages: one paragraph each, dependency arrows, "use this when". |
| `references/signal-pattern.md` | `@pexip/signal` deep dive: the four variants, detach lifecycle, React integration with `useEffect`. |
| `references/media-pipeline.md` | `@pexip/media` + `@pexip/media-processor` + `@pexip/media-control` interplay. Capture, blur, denoise, hot-swap, ordering. |
| `references/tutorial-map.md` | Annotated index of the 11 official tutorials at `developer.pexip.com/docs/category/tutorial`, what each demonstrates, and which to read for which task. |
| `references/pexrtc-api.md` | Full PexRTC reference: every config property, every method (grouped by purpose), every `onX` callback with parameter shapes, and version markers (v37 / v38 / v39 / v40 / v41+). |

| Example | Covers |
|---|---|
| `examples/pexrtc-minimal/` | Single HTML file, joins a meeting via `pexrtc.js`. Drop into any web server, point at a Pexip CN, open in a browser. |
| `examples/react-infinity-minimal/` | Vite + React + `@pexip/infinity` + `@pexip/media`. Join, render selfview + remote, hangup. ~150 lines total. |

---

## 9. Cross-skill pointers

- **Raw protocol** (`request_token`, SSE sync brackets, direct media flow,
  reconnect strategy): `pexip-client-api`.
- **Webapp3 plugins** (`@pexip/plugin-api`, branding ZIPs, manifest):
  `pexip-webapp3-plugin`.
- **Live system debugging** (logs, "why did this call fail"):
  `pexip-infinity-debugging` for live; `pexip-call-rca` for downloaded
  log archives.
