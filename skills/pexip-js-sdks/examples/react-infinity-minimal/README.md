# react-infinity-minimal

Minimal Pexip Infinity client built with `@pexip/infinity` + `@pexip/media`,
React, TypeScript, and Vite.

Demonstrates the canonical signal-wiring pattern from SKILL.md §4:

1. `createInfinityClientSignals([])`
2. Subscribe to `onConnected`, `onPinRequired`, `onError`, `onDisconnected`,
   `onParticipants`, `onRemoteStream` *before* calling `.call()`
3. `createInfinityClient(signals)`
4. `getUserMedia()` → `infinityClient.call({ mediaStream, ... })`

Plus PIN handling (the "fail then retry" pattern), participant list, and
clean teardown.

## Run it

```bash
# .npmrc may be required for some @pexip/* packages (see SKILL.md §7 gotcha #3
# and references/modern-package-map.md). Set up a GitHub token if npm install
# fails with 401.
npm install
npm run dev
# Vite serves at http://localhost:5173/
```

## Caveats

- `package.json` pins `@pexip/*` at `^2.0.0` — adjust to whatever your project standardises on. Don't mix major versions across packages.
- The signal shape used here (`onParticipants`, `onRemoteStream`) reflects `@pexip/infinity` v2; if you target a different major, check the actual exports.
- Uses native `<input>`s, no UI library. For real apps, layer `@pexip/components` on top.
- No background blur. To add it, capture into a `MediaStream`, run it through `createVideoProcessor({ effects: "blur" })`, and pass the *processed* stream to `.call()`. See `references/media-pipeline.md`.
- No reconnect handling. The SDK manages token refresh; the page reload story is your own.

## When to use this pattern

The default for any non-plugin Pexip browser app you're going to maintain.
See SKILL.md §1 for the longer answer.
