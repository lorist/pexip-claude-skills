# pexrtc-minimal

A single HTML file that joins a Pexip conference using the legacy
`pexrtc.js` browser wrapper. Demonstrates:

- Loading `pexrtc.js` from a Conferencing Node at runtime
- The `makeCall` → `onSetup` → `connect` two-stage join
- PIN handling (required / optional / none)
- IDP / Virtual Reception detection (handled minimally — IDP picks the first option, VR is flagged as out-of-scope)
- Local + remote video rendering
- Mute audio/video toggles
- Clean `disconnect` and teardown

## Run it

```bash
# Any static file server works. From this directory:
python3 -m http.server 8080
# Then open http://localhost:8080/ in a browser.
```

You'll need:
- A reachable Pexip Conferencing Node (HTTPS, trusted cert)
- A conference alias on that node
- The browser must be served over HTTPS or `localhost` (`getUserMedia` requires a secure context)

## Caveats

- Loads `pexrtc.js` from the CN you type into the form. In production, hardcode the script `src` to your CN — don't take it from user input.
- Doesn't handle reconnect, token expiry, network drops. PexRTC handles much of this internally; it's not visible to the page.
- Doesn't handle Virtual Reception extension dispatch beyond detecting it.
- IDP picker uses the first IDP in the list — a real client should let the user choose.

## When to use this pattern

Quick PoCs. Kiosks. Throwaway demos. Anything where you'd rather not stand up a Vite/Webpack build. See the parent skill SKILL.md §1 decision tree for the longer answer.
