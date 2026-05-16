# Pexip developer tutorial map

Annotated index of the official tutorials at
`developer.pexip.com/docs/category/tutorial`. Each tutorial is a hands-on
walkthrough; this map says which to read for which task and what to take
away from each.

## The eleven tutorials

| # | Tutorial | What it builds | Read it when |
|---|---|---|---|
| 1 | Introduction | Sets up Vite + React + the modern stack | Starting from zero. Read first. |
| 2 | App architecture | Folder layout, signal wiring patterns | After #1, before writing your own conference UI. |
| 3 | Join a conference | Minimal `infinityClient.call()` flow | Foundational. Mirror in `examples/react-infinity-minimal/`. |
| 4 | Use a PIN | The `onPinRequired` → collect → re-call pattern | Any conference that has a host PIN. |
| 5 | Change devices | Hot-swap camera/mic with `@pexip/media-control` | Building a settings panel. |
| 6 | Change effect | Background blur via `@pexip/media-processor` | Adding blur / virtual background. |
| 7 | Send presentation | Screen share via `getDisplayMedia` + `infinityClient.present()` | Adding a "share screen" button. |
| 8 | Participant list | Subscribing to `signals.onParticipants` | Rendering a roster. |
| 9 | Conference status | Subscribing to conference state signals | Showing locked / muted-all / classification banner. |
| 10 | Breakouts | `@pexip/media-components`'s `BreakoutRoom` + control | Hosts moving people between breakouts. |
| 11 | Live captions / messages | Chat and message-text APIs | Captions overlay or banner. |

(Numbering is for reference here; the docs list them by name.)

## Suggested reading paths

### "I'm building a custom React conference UI from scratch"

1 → 2 → 3 → 4 → 5 → 8 → 9 → (then 6, 7, 10, 11 as features arise).

That's the spine: scaffold, architecture, minimal join, PIN, devices,
roster, conference status. Everything else hangs off that.

### "I just need to add background blur to a working app"

6 (Change effect). Pre-req: you're already on the modern stack and have
a `MediaStream`. If you're on PexRTC, see SKILL.md §1 for why this
isn't possible without porting.

### "I need to handle breakouts as a host"

10 (Breakouts). Pre-req: you've done 1–4 and have a working host join.

### "I'm porting a PexRTC app to the modern stack"

Read 1 → 2 first to understand the new mental model. Then 3 (`call()`
replaces `makeCall` + `connect`), 4 (PIN flow shifts from `onSetup`'s
`pin_status` arg to the `onPinRequired` signal), 8 (roster shifts from
`onRosterList` / `onParticipantCreate` callbacks to `signals.onParticipants`).

The package map's PexRTC ↔ modern correspondence (rough):

| PexRTC | Modern |
|---|---|
| `new PexRTC()` | `createInfinityClient(signals)` |
| `rtc.makeCall(node, alias, name, bw)` + `rtc.connect(pin)` | `infinityClient.call({ node, conferenceAlias, displayName, bandwidth, mediaStream })` plus `signals.onPinRequired` |
| `rtc.onConnect = fn` | `signals.onConnected.add(fn)` |
| `rtc.onParticipantCreate / onParticipantUpdate / onParticipantDelete` | `signals.onParticipants` (single signal, full list) |
| `rtc.muteAudio(true)` | `setMuted({ audio: true })` from `@pexip/media-control` |
| `rtc.present("screen")` | `infinityClient.present(stream)` (you supply the `getDisplayMedia` stream) |
| `rtc.disconnect()` | `infinityClient.disconnect({ reason })` |

A symbol-by-symbol port table is a candidate for a future
`references/migration-pexrtc-to-npm.md` if there's appetite.

## What the tutorials don't cover

Worth knowing where the tutorials stop, so you know where you'll need to
fall back on the `pexip-client-api` skill:

- **Reconnect strategy.** The tutorials don't cover what happens when
  the network drops mid-call. The SDK does *something* under the
  hood — but if you need predictable behaviour for a kiosk or recorder
  that runs 24/7, you'll need to dig into signals and possibly drop
  to the raw API for the reconnect orchestration.
- **Token refresh cadence.** Auto-refreshed by the SDK. Not surfaced.
  If you see drops at hour ~22 of a 24h session, that's where to look.
- **Multi-node behaviour.** Tutorials assume one Conferencing Node. If
  your conference is hosted across multiple, behaviour around joining
  / leaving / reconnecting can be subtle — see `pexip-client-api`
  skill §6.5.
- **Server-side anything.** All tutorials assume a browser. For Node /
  Deno / mobile native, neither SDK applies — use the raw Client API.
