# Gotchas and Pitfalls — Expanded Reference

All 22 production-tested gotchas with reproduction steps, root causes, and
fixes. These are things that bit real developers on Pexip v39+.

---

## 1. Response wrapping

**Symptom:** `resp.result` is `undefined` when calling `requestParticipants`
or `sendRequest`.

**Root cause:** All plugin RPC calls wrap the response in a nested structure:
`{ status: 200, data: { status: "success", result: <payload> } }`.

**Fix:**
```typescript
// WRONG
const data = resp.result;

// CORRECT
const data = resp.data.result;
```

---

## 2. No setMessageText method

**Symptom:** `TypeError: plugin.conference.setMessageText is not a function`

**Root cause:** The SDK does not expose a dedicated method for banner text.

**Fix:** Use `sendRequest`:
```typescript
await plugin.conference.sendRequest({
  method: 'POST',
  path: 'set_message_text',
  payload: { text: 'Banner text here' },
});
```

---

## 3. participantActions onClick receives object

**Symptom:** Using `participantUuid` in a URL produces `[object Object]`
instead of the UUID string.

**Root cause:** The onClick callback for `participantActions` buttons
receives `{ participantUuid: "uuid-string" }`, not a bare string.

**Fix:**
```typescript
// WRONG — participantUuid is the whole { participantUuid: "..." } object
btn.onClick.add(async (participantUuid) => { ... });

// CORRECT — destructure the object
btn.onClick.add(async ({ participantUuid }) => { ... });
```

---

## 4. Message event only fires for others

**Symptom:** Sending a chat message from the same participant never triggers
`plugin.events.message`.

**Root cause:** By design, `message` events only fire for other participants'
messages. Your own messages are not echoed back through the event system.

**Fix:** Accept this behaviour. To test chat/message features, join with a
second participant (second browser tab, SIP endpoint, or CLI client).

---

## 5. Message content type must be text/plain

**Symptom:** `plugin.events.message` never fires despite messages being sent
via the Client API.

**Root cause:** Messages sent with `Content-Type: application/json` through
the Client API's `/message` endpoint are not delivered to the plugin event
system. The Client API requires `text/plain`.

**Fix:** When sending messages programmatically via the Client API (not from
within a plugin), use:
```bash
curl -X POST \
  -H "token: <token>" \
  -H "Content-Type: text/plain" \
  -d "Hello from bot" \
  "https://<node>/api/client/v2/conferences/<alias>/message"
```

Within a plugin, `sendRequest` with `payload` handles this automatically.

---

## 6. Signal callback receives value directly

**Symptom:** Event data is `undefined` or the wrong shape.

**Root cause:** The signal pattern passes the payload directly to the
callback, not inside a wrapper object.

**Fix:**
```typescript
// WRONG — destructuring a non-existent wrapper
plugin.events.participants.add(({value}) => { ... });

// CORRECT — value IS the parameter
plugin.events.participants.add((value) => {
  const { participants } = value;
});
```

---

## 7. Role naming: "host" not "chair"

**Symptom:** `setRole` call fails or is rejected by the Client API.

**Root cause:** The Client API uses `"host"` / `"guest"` for role values.
The External Policy server uses `"chair"` / `"guest"`. Mixing them up
causes silent failures.

**Fix:** In plugin code, always use `"host"` or `"guest"`:
```typescript
await plugin.conference.setRole({ participantUuid, role: 'host' });
```

---

## 8. Case convention split between events and RPC

**Symptom:** `participant.displayName` is `undefined` when reading RPC
response data.

**Root cause:** Events use camelCase (`displayName`, `overlayText`,
`isWaiting`). RPC responses use snake_case (`display_name`, `overlay_text`,
`is_waiting`).

**Fix:** Use the correct case for each context:
```typescript
// Events (camelCase)
plugin.events.participants.add(({ participants }) => {
  participants.forEach(p => console.log(p.displayName));
});

// RPC (snake_case)
const resp = await plugin.conference.requestParticipants({});
resp.data.result.forEach(p => console.log(p.display_name));
```

---

## 9. Manifest is the source of truth

**Symptom:** Plugin files exist in the branding ZIP but the plugin doesn't
load in the meeting.

**Root cause:** The webapp3 runtime reads `manifest.json` to discover
plugins. Files not listed in the `plugins[]` array are ignored.

**Fix:** Ensure `manifest.json` has an entry for the plugin:
```json
{
  "plugins": [
    { "src": "./plugins/my-plugin/index.html", "sandboxValues": [...] }
  ]
}
```

---

## 10. Vite dist missing index.html

**Symptom:** Plugin folder in the branding has `assets/index-abc.js` but no
`index.html`. Plugin fails to load.

**Root cause:** `vite build` with default config produces `dist/assets/`
but does not copy `index.html` into `dist/`.

**Fix:** Copy `index.html` into `dist/` after building:
```bash
npm run build
cp index.html dist/
```

Or add a post-build script in `package.json`:
```json
{
  "scripts": {
    "build": "vite build && cp index.html dist/"
  }
}
```

---

## 11. Branding src path variants

**Symptom:** Plugin ID resolves to "branding" instead of the actual plugin
name when parsing an existing branding ZIP.

**Root cause:** Some brandings use `"./branding/my-plugin/index.html"`
instead of `"./plugins/my-plugin/index.html"`. Code that only extracts the
ID from `./plugins/<id>/` misidentifies the second convention.

**Fix:** Parse both path conventions:
```python
src = entry["src"]  # e.g. "./branding/my-plugin/index.html"
parts = src.replace("./", "").split("/")
# Could be plugins/id/... or branding/id/...
if parts[0] in ("plugins", "branding") and len(parts) >= 2:
    plugin_id = parts[1]
```

---

## 12. Root-level plugin folders

**Symptom:** Plugin not found during ZIP parsing — folder exists at ZIP root
instead of under `plugins/`.

**Root cause:** Older or manually-assembled brandings sometimes place plugin
folders at the root level of the `branding/` directory.

**Fix:** During plugin installation, scan for plugin-like folders (containing
`index.html`) at any level and relocate them under `plugins/`.

---

## 13. Empty default branding

**Symptom:** Downloading the stock "Pexip webapp3 branding" and re-uploading
fails with `{"branding_file": ["No branding files found"]}`.

**Root cause:** The factory-default branding is a ~152-byte near-empty ZIP.
It serves as a placeholder but isn't a valid base for modification.

**Fix:** Never clone from the stock branding. Use a previously-uploaded real
branding or a bundled base ZIP as the starting point.

---

## 14. Summary race after branding mutation

**Symptom:** After installing or removing a plugin, the UI shows stale data
(old plugin count, wrong plugin list).

**Root cause:** A batch summary endpoint that lists all brandings can race
with a direct load of the just-modified branding, overwriting fresh data
with stale cached data.

**Fix:** After mutating a branding, skip its UUID in the batch summary
response and load it directly instead.

---

## 15. Mass branding download causes 502

**Symptom:** Page load triggers 502 errors when many brandings exist (45+).

**Root cause:** Downloading every branding ZIP on page load to inspect
plugins overwhelms the Management API.

**Fix:** Use a lightweight batch summary endpoint for counts and plugin
names. Only download the full ZIP on demand (edit, install, export).

---

## 16. Version not in upload name

**Symptom:** After updating a branding, the Management API UI shows the
old version name, causing confusion about which version is deployed.

**Root cause:** The branding `name` field is set at upload time and not
automatically updated.

**Fix:** Include the version in the upload name:
```python
data={"name": f"My Branding v{VERSION}", "webapp_type": "webapp3"}
```

---

## 17. Embedded iframe doesn't support plugins

**Symptom:** Plugins load in the full webapp3 client but not when joining
via an embedded `@pexip/infinity` React iframe.

**Root cause:** The React embed (`@pexip/infinity` WebRTC SDK) is a minimal
media client. It doesn't load brandings or initialise the plugin runtime.

**Fix:** Test plugins via "Join with Browser" in a standard Pexip meeting,
not through an embedded iframe.

---

## 18. CSP/iframe camera access denied

**Symptom:** Camera or microphone access is denied when the webapp3 client
runs inside an iframe on a third-party page.

**Root cause:** The embedding page must explicitly allow media permissions
to the iframe.

**Fix:** Set all three headers/attributes on the embedding page:
- `Content-Security-Policy: frame-src https://<conferencing-node>`
- `X-Frame-Options: SAMEORIGIN` (or remove for cross-origin embedding)
- iframe `allow="camera; microphone; display-capture"`
- `Permissions-Policy: camera=(self "https://<conferencing-node>")`

---

## 19. External POST routes need conference alias

**Symptom:** POST to an external backend from a plugin returns 404.

**Root cause:** Plugin-to-server routes are stateless — the server has no
session or context. If it needs the conference alias (for routing, logging,
or per-conference state), the plugin must include it in the request body.

**Fix:**
```typescript
fetch('https://server.example/api/action', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    conference: conferenceAlias,  // Include alias
    action: 'some-action',
  }),
});
```

---

## 20. Singleton guard should use silent return, not throw

**Symptom:** Console shows `Error: duplicate` or `Error: already initialized`
on every plugin iframe reload.

**Root cause:** Using `throw new Error('duplicate')` in the singleton guard
creates noisy console output. Plugin iframes can reload during conference
state changes.

**Fix:** Use silent return instead of throwing:
```typescript
if ((globalThis as any).__myPluginInit) {
  console.log('Already initialized, skipping');
  return;
}
(globalThis as any).__myPluginInit = true;
```

---

## 21. overlayText preferred over displayName for user-facing labels

**Symptom:** Participant names shown in toasts or forms don't match what the
host sees — they show the bare join name instead of the policy-assigned display
name.

**Root cause:** `display_name` (RPC) / `displayName` (events) contains the
name the participant used when joining. `overlay_text` / `overlayText` contains
the name set by the host or policy server (e.g., "John Doe | Major (L2)").

**Fix:** Prefer overlayText with fallback:
```typescript
const label = participant.overlay_text || participant.display_name || 'Participant';
```

---

## 22. Conference alias unavailable at plugin init time

**Symptom:** Plugin needs the conference alias during initialization (before
`authenticatedWithConference` fires), but the alias is empty.

**Root cause:** `authenticatedWithConference` fires asynchronously after
conference join. During plugin initialization, the alias isn't available via
events yet.

**Fix:** Parse the alias from the URL synchronously, then update from the
event when it fires:
```typescript
const hashParams = new URLSearchParams(window.location.hash.split('?')[1] || '');
let alias = hashParams.get('conference') || '';
plugin.events.authenticatedWithConference.add((info) => {
  alias = info.conferenceAlias;
});
```
