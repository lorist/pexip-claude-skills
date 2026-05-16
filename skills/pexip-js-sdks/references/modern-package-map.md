# `@pexip/*` package map

The complete set of `@pexip/*` npm packages, what each does, what it
depends on, and when you'd actually reach for it. Sourced from
`developer.pexip.com/docs/category/npm-packages` (May 2026).

## At a glance

| Package | Tier | Reach for it when |
|---|---|---|
| `@pexip/infinity` | orchestration | Building any non-plugin Pexip client. **The default.** |
| `@pexip/infinity-api` | primitive | You want raw fetch + TS types, no peer-connection. Rare. |
| `@pexip/media` | orchestration | Capturing camera/mic with effect pipeline support. |
| `@pexip/media-processor` | orchestration | Background blur, virtual background, denoise. |
| `@pexip/media-control` | orchestration | Hot-swap devices mid-call without re-negotiation. |
| `@pexip/media-components` | UI | React components specific to Pexip media (selfview, mute toggle wired up). |
| `@pexip/components` | UI | React UI primitives (buttons, modals, icons) styled to match Webapp3. |
| `@pexip/hooks` | UI | React hooks for state Pexip apps need (`useMediaStream`, etc.). |
| `@pexip/peer-connection` | primitive | You're rolling your own client and need a typed `RTCPeerConnection` wrapper. Rare. |
| `@pexip/signal` | primitive | Direct dependency only — re-exported by every higher package. |
| `@pexip/plugin-api` | parallel | Building a Webapp3 plugin (button/toast/panel inside the stock UI). **See `pexip-webapp3-plugin` skill.** |

## The four tiers, with arrows

```
            ┌─────────────────────────────────────────────────────┐
   UI       │  @pexip/components   @pexip/hooks                   │
            │       └────────────┬─────────────┘                  │
            │                    ▼                                │
            │  @pexip/media-components                            │
            └────────────────────┬────────────────────────────────┘
                                 │ uses
            ┌────────────────────┴────────────────────────────────┐
   Orches.  │  @pexip/infinity   @pexip/media                     │
            │      │                  │                           │
            │      │            ┌─────┴─────┐                     │
            │      │            ▼           ▼                     │
            │      │   @pexip/media-     @pexip/media-            │
            │      │   processor        control                   │
            └──────┼─────────────────────────────────────────────-┘
                   │ wraps
            ┌──────┴──────────────────────────────────────────────┐
   Prim.    │  @pexip/infinity-api   @pexip/peer-connection       │
            │           │                       │                 │
            │           └────────────┬──────────┘                 │
            │                        ▼                            │
            │               @pexip/signal                         │
            └─────────────────────────────────────────────────────┘
```

`@pexip/plugin-api` lives **outside** this tower — it's a sandbox API for
plugins that run inside the stock Webapp3 iframe, not a building block for
custom clients. Don't confuse the two paths.

## Per package

### `@pexip/infinity` — high-level conference client

**The package you actually use.** Exposes `createInfinityClient(signals)`
and `createInfinityClientSignals(extras)`. Manages the token lifecycle
(request, auto-refresh, release), holds the peer connections, fires
signals on every state change. Methods include `.call()`, `.disconnect()`,
`.mute()`, `.present()`, and the breakout / participant control surface.

```ts
import { createInfinityClient, createInfinityClientSignals, ClientCallType } from "@pexip/infinity";
const signals = createInfinityClientSignals([]);
const client  = createInfinityClient(signals);
await client.call({ conferenceAlias, displayName, callType: ClientCallType.AudioVideo, mediaStream, node });
```

### `@pexip/infinity-api` — generated HTTP types

100+ functions matching `/api/client/v2/conferences/<alias>/...`. No peer
connection, no signal layer, no token management. Re-exports the request
and response types so `@pexip/infinity` can stay typed end-to-end.

You'd reach for this directly only if you want typed `fetch` calls without
the rest of the client. If that's truly your goal, you might be better
served by reading the `pexip-client-api` skill and writing it yourself.

### `@pexip/media` — capture pipeline

Orchestrates `getUserMedia`, holds the captured stream, and exposes the
"effects pipeline" hooks. Pairs naturally with `@pexip/media-processor`
(processors plug into the pipeline) and `@pexip/media-control` (the
control side — mute, switch device).

The package's job is to give you a stream you can hand to
`infinityClient.call({ mediaStream })`. Conceptually:

```
getUserMedia() → @pexip/media stream → (optional: @pexip/media-processor) → infinityClient.call()
                          ↑
                    @pexip/media-control mutates this
```

### `@pexip/media-processor` — effects

MediaPipe-backed video segmentation (background blur, virtual background)
and AudioWorklet-based audio processing (denoise). Returns a transformed
stream — see SKILL.md gotcha #4. You **must** pass the processed stream,
not the original, to `infinityClient.call()`.

Heavy: pulls a MediaPipe model. Lazy-load if you can.

### `@pexip/media-control` — device & mute orchestration

Hot-swap camera and microphone without renegotiating the SDP. Exposes
`setStream()` semantics that the rest of the stack respects. Also handles
the muted-state machine so React components stay in sync.

The package documents that it **requires GitHub-authenticated npm
install**. Set up an `.npmrc` with a GitHub personal access token before
`npm install`, or your CI build will fail with a 401. The same is rumoured
to apply to other `@pexip/*` packages — check before bare-installing.

### `@pexip/components` — vanilla React UI primitives

Buttons, modals, icons, form fields, layout primitives. Styled to match
Webapp3. **CSS import is mandatory** — `@pexip/components/dist/index.css`
plus `fonts.css`. Skip them and components render unstyled with no
warning.

Not Pexip-specific. Could in principle be used in any React app.

### `@pexip/hooks` — React hooks

Custom hooks for state shapes Pexip apps repeatedly need: `useMediaStream`,
`useDevices`, etc. Light layer over the orchestration packages.

### `@pexip/media-components` — Pexip-specific React components

The "this is the bit that knows about Pexip" UI layer. Pre-wired
selfview, participant tile, mute toggle, breakout-room switcher, etc.
You can mix-and-match with your own components; you don't have to use
all of them.

### `@pexip/peer-connection` — typed `RTCPeerConnection` wrapper

Provides `MainPeerConnection` and `PresentationPeerConnection` classes.
Used internally by `@pexip/infinity`. You'd touch this directly only if
you're rolling your own client — at which point you should ask whether
that's actually the right call vs. using `@pexip/infinity` and
extending it.

### `@pexip/signal` — signals-and-slots event system

The event primitive every higher package builds on. Four variants:

- **`Signal`** — fire-and-forget. Late subscribers don't see past values.
- **`BehaviorSignal`** — holds the last value. Late subscribers
  immediately receive it.
- **`ReplaySignal`** — holds the last N values. Late subscribers receive
  the buffer.
- **`BatchedSignal`** — coalesces emissions within a microtask.

Full deep-dive in `references/signal-pattern.md`.

### `@pexip/plugin-api` — Webapp3 plugin SDK

Different concern, different path. For building a button/toast/panel that
runs inside the stock Pexip Webapp3 (sandboxed iframe). Covered in full
by the `pexip-webapp3-plugin` skill — read that, not this one, if that's
your goal.

## Versioning

The packages share a major-version cadence aligned with Webapp3 releases
but version independently. Pin compatible majors in `package.json`. Don't
mix `@pexip/infinity@2.x` with `@pexip/media-components@1.x` — the signal
shapes diverge.

## Auth for npm install

At least `@pexip/media-control` requires GitHub authentication. Create
`.npmrc` in the project root (or `~/.npmrc`):

```
//npm.pkg.github.com/:_authToken=ghp_xxxxxxxxxxxxxxxxxxxx
@pexip:registry=https://npm.pkg.github.com
```

Don't commit the token. CI should inject it from a secret.
