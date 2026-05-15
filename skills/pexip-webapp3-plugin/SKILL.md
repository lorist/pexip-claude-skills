---
name: pexip-webapp3-plugin
description: >
  Build, package, and deploy Pexip Infinity webapp3 plugins using
  @pexip/plugin-api. Covers the plugin SDK (registration, events, UI
  buttons/toasts/forms, conference control, sendRequest), Vite project
  scaffold, branding ZIP structure and manifest.json, installing plugins
  into brandings via the Management API, webapp alias routing, and 22
  production-tested gotchas. Use this skill whenever the user is building
  a webapp3 plugin, adding buttons or toasts to Pexip meetings, working
  with @pexip/plugin-api, packaging plugins into branding ZIPs, uploading
  brandings to Pexip Infinity, debugging why a plugin doesn't load or
  events don't fire, asking about webapp3 plugin development patterns,
  using sendRequest for banner text or conference control from a plugin,
  handling participant actions or breakout rooms in a plugin, or asking
  about the webapp3 manifest.json format. Also triggers for "pexip plugin",
  "plugin-api", "branding ZIP", "webapp3 branding", "plugin manifest",
  "participant action button", "plugin toolbar button", "showToast",
  "showForm", "registerPlugin", or "plugin sandbox values".
---

# Pexip Webapp3 Plugin Development — Expert Skill

Practical knowledge for building, packaging, and deploying **webapp3 plugins**
for Pexip Infinity — the sandboxed iframe extensions that run alongside the
meeting UI. Plugins register via `@pexip/plugin-api`, subscribe to meeting
events (participants joining, chat messages, conference state), add buttons
and toasts to the UI, and control the conference via RPC. They ship inside
**branding ZIPs** uploaded to Pexip's Management API and are loaded by the
webapp3 client at meeting join time.

This skill is distilled from building and operating three production plugins
(chat relay, send-to-lobby, screenshare shortcut) and includes 22 non-obvious
behaviours discovered through production debugging.

> **Sourcing:** the canonical plugin API reference is
> `https://docs.pexip.com/end_user/guide_for_admins/webapp3_plugins_overview.htm`.
> Where this skill states something the docs don't, it's marked **(field-tested)**
> or **(common pattern)**.

---

## Quick Decision Tree

| Goal | Read first |
|---|---|
| Build a plugin from scratch | §2 (scaffold) then §1 (SDK) |
| Add buttons, toasts, or forms to the meeting UI | `references/sdk-ui-methods.md` |
| Send messages / set banner text from a plugin | §1 sendRequest subsection |
| React to participant joins, messages, auth events | `references/sdk-events.md` |
| Control participants (role, mute, breakout, transfer) | `references/sdk-conference-control.md` |
| Understand branding ZIP and manifest.json format | `references/branding-zip-structure.md` |
| Install a plugin into a branding via Management API | `references/management-api-brandings.md` |
| Plugin not loading or events not firing | §5 (debugging) + §6 (gotchas) |
| See a minimal working plugin | `examples/hello-world-plugin/` |
| See participant action patterns | `examples/participant-action-plugin/` |

---

## 1. Plugin SDK API

### Registration

Every plugin starts with `registerPlugin`:

```typescript
import { registerPlugin } from '@pexip/plugin-api';

const plugin = await registerPlugin({
  id: 'my-plugin',
  version: 1,
});
```

The `id` must match the folder name inside the branding ZIP. `version` is an
integer shown in debug logs.

### Events — the signal pattern

Subscribe to meeting events via `plugin.events.<name>.add(callback)`:

```typescript
plugin.events.authenticatedWithConference.add((info) => {
  console.log('Joined conference:', info.conferenceAlias);
});
```

**Critical rule:** callbacks receive the payload **directly** — never destructure
as `({value}) =>` (there is no `value` wrapper). You can destructure the
payload's own fields, e.g. `({ participants }) =>`, but not a non-existent
outer wrapper.

| Event | Fires when | Key fields |
|---|---|---|
| `authenticatedWithConference` | User joins a conference | `conferenceAlias`, `conferenceName` |
| `me` | Own participant info updates | `participant.displayName`, `participant.uuid` |
| `participants` | Participant list changes | `participants[]` with `uuid`, `displayName`, `protocol`, `isWaiting` |
| `message` | Chat message from ANOTHER participant | `payload` (text), `displayName` (sender) |
| `presentationConnectionStateChange` | Screenshare starts/stops | `state` |

> `message` only fires for **other** participants' messages — never your own.
> Chat/message features require 2+ participants to test. **(field-tested)**

Full payload shapes and subscription examples: `references/sdk-events.md`

### UI methods

**Toolbar button:**
```typescript
const btn = await plugin.ui.addButton({
  position: 'toolbar',
  label: 'My Action',
  icon: 'IconChat',
});
btn.onClick.add(async () => { /* handler */ });
```

**Participant action button** (context menu on a participant):
```typescript
const btn = await plugin.ui.addButton({
  position: 'participantActions',
  label: 'Send to Lobby',
});
btn.onClick.add(async ({ participantUuid }) => {
  // CORRECT: destructure the object
  // WRONG: (participantUuid) => ... gives you the object, not the UUID string
  await plugin.conference.setRole({ participantUuid, role: 'guest' });
});
```

**Toast notifications:**
```typescript
plugin.ui.showToast({ message: 'Done!' });
plugin.ui.showToast({ message: 'Error occurred', isDanger: true });
```

**Modal forms:**
```typescript
const input = await plugin.ui.showForm({
  title: 'Enter message',
  form: {
    elements: {
      message: { name: 'Message', type: 'text', isOptional: false },
    },
    submitBtnTitle: 'Send',
  },
});
const text = input?.message || '';
```

Full reference (all positions, icon names, dynamic updates): `references/sdk-ui-methods.md`

### Conference control — sendRequest

For Client API actions that lack a dedicated SDK method, use `sendRequest`:

```typescript
// Set banner/overlay text (no setMessageText method exists on the SDK)
await plugin.conference.sendRequest({
  method: 'POST',
  path: 'set_message_text',
  payload: { text: 'Meeting classified: RESTRICTED' },
});

// Read current banner text
const resp = await plugin.conference.sendRequest({
  method: 'GET',
  path: 'get_message_text',
});
const text = resp.data.result.text;
```

**Response wrapping** — all RPC calls return a nested structure:
```typescript
// Response shape:
// { status: 200, data: { status: "success", result: <actual_data> } }

// CORRECT:
const participants = resp.data.result;

// WRONG (gives undefined):
const participants = resp.result;
```

This is the #1 gotcha. Every `requestParticipants`, `sendRequest`, or other
RPC call wraps the response. Always access `resp.data.result`. **(field-tested)**

### Role and participant control

```typescript
// Set role — uses "host"/"guest", NOT "chair"/"guest"
await plugin.conference.setRole({ participantUuid, role: 'guest' });

// Get participant list via RPC (returns snake_case fields)
const resp = await plugin.conference.requestParticipants({});
const participants = resp.data.result;
// participants[].display_name (snake_case) — NOT displayName
// Events use camelCase, RPC uses snake_case. (field-tested)

// Breakout rooms
const room = await plugin.conference.breakout({
  name: 'room-1',
  end_action: 'transfer',
});
await plugin.conference.breakoutMoveParticipants({
  toRoomUuid: room.breakout_uuid,
  participants: [participantUuid],
});
await plugin.conference.closeBreakoutRoom({
  breakoutUuid: room.breakout_uuid,
});
```

Full method reference and send-to-lobby pattern: `references/sdk-conference-control.md`

### External communication

Plugins can `fetch()` to external servers. Two rules:

1. **Include the conference alias in POST bodies** — plugin-to-server routes
   are stateless; the server cannot derive the alias from headers or session:
   ```typescript
   fetch('https://my-server.example/api/action', {
     method: 'POST',
     headers: { 'Content-Type': 'application/json' },
     body: JSON.stringify({ conference: conferenceAlias, data: '...' }),
   });
   ```

2. **CORS** — the external server must allow the conferencing FQDN origin.

---

## 2. Project Scaffold with Vite

Minimal project structure:

```
my-plugin/
  index.html
  package.json
  vite.config.ts
  tsconfig.json
  src/
    index.ts
```

**index.html** — entry point loaded by the webapp3 branding runtime:
```html
<!DOCTYPE html>
<html>
  <head><script type="module" src="/src/index.ts"></script></head>
  <body></body>
</html>
```

**package.json** — `@pexip/plugin-api` is the only required dependency:
```json
{
  "private": true,
  "type": "module",
  "scripts": { "dev": "vite", "build": "vite build" },
  "dependencies": { "@pexip/plugin-api": "^22.0.0" },
  "devDependencies": { "typescript": "^5.5.4", "vite": "^5.0.0" }
}
```

**vite.config.ts** — `base: './'` is mandatory for relative asset paths:
```typescript
import { defineConfig } from 'vite';
export default defineConfig({
  base: './',
  build: { outDir: 'dist', emptyOutDir: true, target: 'esnext' },
});
```

**Deterministic filenames** — for simpler branding ZIP assembly, use Vite
library mode to produce `assets/index.js` instead of `assets/index-HASH.js`:

```typescript
export default defineConfig({
  base: './',
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    lib: { entry: 'src/index.ts', formats: ['es'], fileName: 'assets/index' },
    rollupOptions: { external: [] },
  },
});
```

Library mode is optional — both hashed and deterministic filenames work in
branding ZIPs. **(common pattern)**

**Build and package:**
```bash
npm install
npm run build
# dist/ now contains assets/index-HASH.js (or assets/index.js in library mode)
# IMPORTANT: copy index.html into dist/ — Vite doesn't do this automatically
cp index.html dist/
```

The `dist/` folder contents go into the branding ZIP at `plugins/<plugin-id>/`.

**Singleton guard** — prevents double-initialisation if the plugin iframe reloads:
```typescript
if ((globalThis as any).__myPluginInit) {
  console.log('Plugin already initialized, skipping');
} else {
  (globalThis as any).__myPluginInit = true;
  initializePlugin().catch(console.error);
}
```

Use silent return instead of throwing — `throw` creates noisy console output on plugin iframe reload. **(field-tested)**

For working examples, see `examples/hello-world-plugin/` and
`examples/participant-action-plugin/`.

---

## 3. Branding ZIP Structure

Plugins ship inside **webapp3 branding ZIPs** uploaded to Pexip Infinity.

```
webapp3/branding/
  manifest.json         ← source of truth
  plugins/
    my-plugin-id/
      index.html
      assets/
        index-HASH.js
  images/
    jumbotron.jpg
```

**manifest.json** controls which plugins load:
```json
{
  "plugins": [
    {
      "src": "./plugins/my-plugin-id/index.html",
      "sandboxValues": [
        "allow-same-origin", "allow-popups",
        "allow-popups-to-escape-sandbox", "allow-forms", "allow-scripts"
      ]
    }
  ]
}
```

Rules:
- `plugins` array is at **root level**, NOT under `applicationConfig`
- Plugin files without a `manifest.json` entry are **silently ignored**
- `sandboxValues` must include `allow-same-origin` (for `fetch()`) and
  `allow-scripts` (for execution)
- `src` paths may use `./plugins/` **or** `./branding/` as parent folder —
  both conventions exist in the wild **(field-tested)**
- Some brandings have plugin folders at the ZIP root instead of under
  `plugins/`; relocate them during install

Full ZIP anatomy and alias routing: `references/branding-zip-structure.md`

---

## 4. Deployment via Management API

End-to-end flow to install a plugin into a Pexip deployment:

1. **Download** target branding ZIP:
   `GET /api/admin/configuration/v1/webapp_branding/{uuid}/download/`

2. **Inject** the plugin: extract ZIP → copy `dist/` into
   `plugins/{id}/` → add entry to `manifest.json` → re-zip

3. **Upload** modified branding:
   `POST /api/admin/configuration/v1/webapp_branding/` (multipart:
   `name`, `description`, `webapp_type=webapp3`, `branding_file`)

4. **Route** webapp alias to new branding:
   `PATCH /api/admin/configuration/v1/webapp_alias/{id}/`

5. **Clean up** old branding (optional):
   `DELETE /api/admin/configuration/v1/webapp_branding/{uuid}/`

**Watch out:**
- The stock "Pexip webapp3 branding" is a ~152-byte empty ZIP — downloading
  and re-uploading fails. Start from a real branding or a bundled base ZIP.
  **(field-tested)**
- After upload, clear any local API cache — stale UUIDs cause 404s.
- Include the plugin version in the branding name for traceability.

Python and curl examples for each endpoint: `references/management-api-brandings.md`

---

## 5. Testing and Debugging

**Local development:** run `npx vite` for hot-reload on port 5173. Full plugin
testing requires the webapp3 host runtime — deploy to a branding on a dev Pexip
instance. For UI-only testing (toasts, buttons, forms), use a mock plugin API
with environment detection:

```typescript
const isLocalDev = window.location.hostname === 'localhost'
  && window.parent === window; // Not in iframe = not in webapp

const plugin = isLocalDev
  ? createMockPlugin()
  : await registerPlugin({ id: 'my-plugin', version: 1 });
```

See `references/sdk-conference-control.md` for mock pattern details.
**(field-tested)**

**Two-participant constraint:** `plugin.events.message` only fires for other
participants' messages. Chat features need 2+ participants to test.

**Debugging checklist:**

| Symptom | Check |
|---|---|
| Plugin not loading | `manifest.json` entry exists? `src` path correct? |
| No events firing | `allow-scripts` in `sandboxValues`? |
| RPC returns `undefined` | Using `resp.data.result` (not `resp.result`)? |
| Messages not arriving | Sender using `text/plain` content type? |
| Button click gives `[object Object]` | Destructuring `{ participantUuid }` from onClick? |
| `displayName` undefined in RPC result | RPC uses `display_name` (snake_case) |
| Plugin works locally but not in branding | `vite.config.ts` has `base: './'`? `index.html` in `dist/`? |

**Embedded iframe limitation:** the `@pexip/infinity` React embed does NOT
support webapp3 plugins. Plugins require the full webapp3 runtime — test via
"Join with Browser" in a real Pexip meeting. **(field-tested)**

---

## 6. Gotchas

| # | Gotcha | Symptom | Fix |
|---|--------|---------|-----|
| 1 | Response wrapping | `resp.result` undefined | Access `resp.data.result` |
| 2 | No `setMessageText` method | Method not found | `sendRequest({ path: 'set_message_text' })` |
| 3 | participantActions onClick shape | UUID is `[object Object]` | Destructure `{ participantUuid }` |
| 4 | Message event scope | Own messages never arrive | By design — only others' messages fire |
| 5 | Message content type | `message` event never fires | Sender must use `text/plain`, not `application/json` |
| 6 | Signal callback shape | Event data undefined | `(value) =>` not `({value}) =>` |
| 7 | Role naming mismatch | "chair" rejected by Client API | Use `"host"` / `"guest"` |
| 8 | Case convention split | `displayName` undefined in RPC | RPC: `display_name` (snake); events: `displayName` (camel) |
| 9 | Manifest is source of truth | Plugin files exist but don't load | Must add to `manifest.json` `plugins[]` |
| 10 | Vite dist missing index.html | No entry point in branding | Copy `index.html` into `dist/` after build |
| 11 | Branding src path variants | Plugin ID resolves to "branding" | Handle both `./plugins/` and `./branding/` |
| 12 | Root-level plugin folders | Plugins not detected in ZIP | Relocate to `plugins/` subdirectory |
| 13 | Empty default branding | Upload fails after re-zip | Stock branding is ~152 bytes; use a real base |
| 14 | Summary race after mutation | Stale plugin data in UI | Skip changed UUID in batch; load directly |
| 15 | Mass branding download | 502 errors on page load | Lazy-load on demand; use summary endpoint |
| 16 | Version not in upload name | UI shows wrong version | Include version in branding name |
| 17 | Embedded iframe | Plugins don't load | Use "Join with Browser" for full webapp3 |
| 18 | CSP/iframe camera | Camera denied in embed | Align `frame-src`, `X-Frame-Options`, `Permissions-Policy` |
| 19 | External POST missing alias | 404 from stateless server | Include `conference` in POST body |
| 20 | Singleton guard throws on reload | Console error on iframe reload | Use silent `return` instead of `throw new Error` |
| 21 | overlayText vs displayName | Wrong participant name in toasts | Prefer `overlay_text` / `overlayText` for user-facing labels |
| 22 | Alias unavailable at init | Conference alias empty during setup | Parse from URL hash; update from `authenticatedWithConference` event |

Expanded entries with reproduction steps and code fixes: `references/gotchas-and-pitfalls.md`

---

## Reference Index

| File | Coverage |
|---|---|
| `references/sdk-events.md` | All event types with TypeScript payload shapes and subscription examples |
| `references/sdk-ui-methods.md` | `addButton`, `showToast`, `showForm` — positions, icons, dynamic updates |
| `references/sdk-conference-control.md` | `sendRequest` paths, `setRole`, `requestParticipants`, breakout lifecycle |
| `references/branding-zip-structure.md` | Branding ZIP anatomy, manifest.json schema, sandboxValues, alias routing |
| `references/management-api-brandings.md` | CRUD endpoints for webapp_branding and webapp_alias with curl/Python |
| `references/gotchas-and-pitfalls.md` | All 22 gotchas expanded with reproduction, root cause, and fix |

---

## When NOT to use this skill

| Topic | Use instead |
|---|---|
| IVR themes, meeting backgrounds, visual customisation | `pexip-branding-theme` (future) |
| Client API token lifecycle, WebRTC media | `pexip-client-api` |
| External policy server design | `pexip-external-policy` |
| Call failure diagnosis from logs | `pexip-call-rca` |
| Management API resource CRUD (non-branding) | `pexip-management-api` |
