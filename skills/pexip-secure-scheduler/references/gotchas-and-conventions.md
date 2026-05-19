# DRF conventions and field-tested gotchas

The Portal API is a Django REST Framework (DRF) project. Most of the
oddities here are standard DRF behaviour — they only surprise you if
you've not built against DRF before. The rest are Pexip-specific.

---

## 1. DRF conventions you must internalise

### Pagination shape

Every `*_list` endpoint returns:

```json
{
  "count": 137,
  "next": "https://scheduler.example.com/api/encounter/?limit=20&offset=20",
  "previous": null,
  "results": [ /* up to `limit` objects */ ]
}
```

- `count` is the total, not the page size.
- `next` / `previous` are full URLs (or `null` at the edges).
- Query params: `limit` (page size) and `offset` (start index).
  No defaults are documented — the deployment may impose its own.
- **There is no cursor pagination.** For very large lists you'll
  walk offset-by-offset; data shifting under you between pages is
  possible.

To page through everything from Python:

```python
import requests
url = "https://scheduler.example.com/api/encounter/?limit=100"
while url:
    r = requests.get(url, headers={"Authorization": f"Bearer {token}"}).json()
    for enc in r["results"]:
        ...
    url = r["next"]
```

### Filtering

**Most** list endpoints expose only `limit` and `offset`. A handful
also expose `name` / `name__contains` (e.g. `access_group`,
`alias_template`). **Encounter does not** — there's no `start_date__gte`
or any other filter. If you need filtered queries on encounters,
your options are:

- Pull all and filter client-side (only viable for small N).
- Use `/api/calendar/?start=…&end=…` for date-range filtering of
  expanded events.
- Cache encounter ids out-of-band and query individually.

### PUT vs PATCH semantics

This trips up everyone who's not used to DRF:

| Method | Behaviour | When to use |
|---|---|---|
| `PUT /api/<resource>/{id}/` | **Full replacement.** All required fields must be present in the body. Any optional field you omit is reset to its default (or null). | When you genuinely have the full canonical state and want to set it. |
| `PATCH /api/<resource>/{id}/` | **Partial update.** Only the fields you include are touched; the rest stay as-is. | Default for "change just these fields." |

**Default to PATCH.** A common bug: you GET an Encounter, modify
two fields, and PUT it back, forgetting to send a no-longer-defaulting
field — and now your meeting has a different recurrence rule because
the field was reset.

### Multiple write content types

Every write endpoint declares three content types:

- `application/json` (preferred)
- `application/x-www-form-urlencoded`
- `multipart/form-data`

Stick to `application/json`. The form variants are declared by the
DRF tooling but rarely exercised in practice; nested objects and
arrays don't survive form encoding cleanly.

### Singletons

Four resources have **no POST and no DELETE** — they exist as a
single row at id `1` and you only ever GET or PATCH them:

- `/api/smtp_server/` (SMTP relay config)
- `/api/authentication_mode/` (local vs OIDC for portal users)
- `/api/global_settings/` (system-wide defaults)
- `/api/email_template/` (the invite email template)

Attempting `POST /api/smtp_server/` returns `405 Method Not Allowed`.

### Bulk operations

There are **none**. No `DELETE /api/encounter/?id__in=...`, no bulk
PATCH, no batch endpoint. If you want to delete 50 encounters,
that's 50 DELETE requests. Plan for it; rate-limit your callers if
needed.

---

## 2. Pexip-specific footguns

### F1. `start_date` is a date, not a datetime

```json
✘ { "start_date": "2026-06-01T10:00:00Z" }   /* fails or truncates */
✓ { "start_date": "2026-06-01",
    "start_time": "10:00:00",
    "end_time":   "10:30:00",
    "timezone":   "Europe/Oslo" }
```

Time-of-day is **separate** from the date. Timezone is **separate**
again. All three must be set if you care about the actual moment in
wall-clock time.

### F2. `timezone` is a 400-entry enum, not a free string

Accepted: `"UTC"`, `"Europe/Oslo"`, `"America/Los_Angeles"`,
`"Asia/Tokyo"`, etc.

Rejected: `"EST"`, `"PST"`, `"UTC+1"`, `"GMT"`, `"Europe/Kyiv"` (the
enum spells it `"Europe/Kiev"` in many builds — verify), arbitrary
strings.

Pre-validate against the enum. The Scheduler returns 400 with a
clear error but it's easy to ship a UI that lets users pick a
banned value.

### F3. `recurrence` is opaque

The spec declares it `type: string, nullable: true` with no pattern
and no description. Pexip Scheduling Core consumes iCalendar
`RRULE` strings, but ⚠️ verify against your version. Test rules
before deploying:

```bash
# Make a test encounter, set recurrence, GET it back to see if the server normalised it
```

Common pitfalls:

- `BYSETPOS` may not be supported.
- `INTERVAL` may have a maximum (e.g. INTERVAL ≤ 12).
- Sub-day frequencies (`FREQ=MINUTELY`) are typically rejected.

### F4. `mail_sequence` and update invites

If you PATCH an encounter that's already had invites sent, **bump
`mail_sequence`** before resending. Calendar clients (Outlook,
Apple, Google) use the iCalendar SEQUENCE property to decide whether
to apply the update. If SEQUENCE didn't increase, the update is
silently discarded.

```json
GET /api/encounter/{uuid}/        ← returns mail_sequence: 0
PATCH /api/encounter/{uuid}/      { "end_time": "...", "mail_sequence": 1 }
POST /api/command/send_email      (resend to affected participants)
```

### F5. `participant_aliases` is read-only

On `EncounterParticipant`:

```json
✘ POST /api/encounter_participant/ { ..., "participant_aliases": ["foo@example.com"] }
   /* silently ignored — aliases are computed from AliasTemplates */

✓ POST /api/encounter_participant/ { ..., "short_alias": "alice", "long_alias": "<uuid>" }
   /* override the parts the template uses */
```

If you want a specific alias for a specific participant, override
`short_alias` and/or `long_alias` and design your `AliasTemplate`s
to use them.

### F6. PIN regex is strict

`^((\d{3,19}#)|(\d{4,20}))?$` — see
[participants-roles-aliases.md](participants-roles-aliases.md) §1.

Test these before shipping a UI:
- `"1234"` ✓
- `"1234#"` ✓ (3 digits + `#`)
- `"123"` ✘
- `"1234#5"` ✘
- `"hunter2"` ✘

Pre-validate; 400s give the field name but the regex error is opaque.

### F7. `host: true` plus no breakout = main-room

A role with `host: false` only directs the participant to a breakout
**if there is a BreakoutRoom keyed off that role on the encounter**.
Otherwise they land in the main VMR too. Don't rely on the host flag
alone to keep non-hosts out of the main room — explicitly create the
breakouts.

### F8. The `long_lived_token` endpoint returns no body

The spec declares all three `long_lived_token` operations as
`200 — No response body`. In practice the token is in a response
header. **Verify with `curl -i` on your version** and pin the
contract in code:

```bash
curl -i -u admin:pw -X POST https://scheduler.example.com/api/command/long_lived_token/
```

The header name varies between releases — don't hardcode against
the spec, hardcode against your deployment.

### F9. Email body limit is 24,576 chars

`email_template.body_template` is `maxLength: 24576`. With inline
CSS, image data URIs, and tracking pixels, this fills fast. Strip
whitespace, externalise CSS where possible, and avoid embedding
base64 images.

### F10. Themes / Views / Languages / IdPs match by name, not by id

The Scheduler stores the **name** of an Infinity-side resource and
sends it to Infinity at provision time. If you rename the theme on
Infinity (or delete and recreate it), the Scheduler row keeps
pointing at the **old** name and meetings silently fall back to
defaults. See [infinity-integration.md](infinity-integration.md) §3.

### F11. `default_response_type` controls unknown-alias behaviour

The Scheduler can either own every alias (`REJECT`) or share aliases
with Infinity (`CONTINUE`). If your deployment mixes Scheduler-managed
and pre-existing VMRs and you don't configure
`global_settings.default_response_type` + `PassthroughAlias`
correctly, you'll get one of:

- Unknown aliases rejected at the door (when `REJECT` and the alias
  isn't a passthrough)
- Scheduler accidentally shadowing an Infinity-direct VMR (rare; the
  Scheduler doesn't claim aliases it didn't generate)

### F12. AccessGroup gates the portal, not the meeting

`encounter.access_groups` controls who can **edit / view in the
Scheduler UI**. It does NOT control who can join the meeting on
Infinity. To restrict who joins, use:

- `participant.authentication_method = "PIN"` + a strong PIN
- `participant.authentication_method = "IDP"` + an IdP group constraint
- A locked breakout to gate guests

### F13. Roles are global, not per-tenant

There's no namespacing of Roles by user, AccessGroup, or anything
else. If you run a multi-tenant deployment, prefix your role names
yourself or you'll have name collisions.

### F14. Nested-on-create is supported, nested-on-update is NOT

`POST /api/encounter/` with nested `encounter_participants` and
`breakout_rooms` works. `PATCH /api/encounter/{id}/` with the same
nested arrays is **not** documented and typically does not replace
those collections — you'd silently keep the existing
EncounterParticipants and BreakoutRooms. To change those after
creation, use the dedicated `/api/encounter_participant/` and
`/api/breakout_room/` endpoints.

### F15. `auto_dial: true` needs a `dialout_alias` on the Participant

Setting `auto_dial: true` on the EncounterParticipant when the
Participant's `dialout_alias` is empty silently does nothing —
Infinity has no destination to dial.

### F16. `cancel: true` before DELETE, not after

To cancel a meeting, the order is:

```
POST /api/command/send_email   { encounter, participant, cancel: true }   ← per recipient
DELETE /api/encounter/{uuid}/
```

If you DELETE first, `send_email` returns `404` because the encounter
is gone. Calendar clients then don't see the cancellation and the
meeting hangs around in their calendar.

### F17. `participant_limit` is a hard cap on the Infinity side

When the limit is hit, the next caller is **rejected by Infinity**,
not queued. There's no waitlist. The reject message is generic ("at
capacity") — don't expect Pexip to expose which participant got
bumped.

### F18. `start_date` without `start_time` + `all_day: false` is undefined

If `all_day: false` and `start_time` / `end_time` are null, the
meeting has no defined time and the iCalendar invite ends up
malformed (most clients show "All day" anyway). Either set
`all_day: true` or always provide times.

### F19. Connection security on SMTP port 587

`SMTPServer.port = 587` + `connection_security: NONE` is a common
misconfiguration. Port 587 is the **submission** port and typically
requires STARTTLS. If TLS handshakes fail, try `STARTTLS` first.

### F20. The `view.layout_name` strings are case-sensitive

`"1:7"` ≠ `"1 : 7"` ≠ `"1.7"`. Match exactly what Infinity expects.
Pexip's standard layouts include `1:0`, `1:7`, `1:21`, `2:21`,
`4:0`, `5:7`, plus several others depending on the version. Check
the Infinity admin UI for the precise list.

### F21. Time fields don't include seconds in some clients

`start_time` / `end_time` are `HH:MM:SS`. Some clients (and the
default email template, via `.strftime('%H:%M')`) display only
`HH:MM`. Always send seconds in the API (`"10:30:00"` not `"10:30"`)
or you'll get a 400.

### F22. The Scheduler creates the `adhoc_guest_breakout_id`, you can't suppress it

Every Encounter has an auto-created breakout for unknown dial-ins.
There's no flag to disable it. If you want zero ad-hoc joins, you
need to control access via PIN/IDP at the participant level **or**
make `default_response_type: REJECT` on the global settings.

---

## 3. Quick reference — error codes

| Status | Common causes |
|---|---|
| `400 Bad Request` | Schema violation: wrong type, value outside enum, regex mismatch, missing required field. Body usually lists the offending fields. |
| `401 Unauthorized` | Missing or bad `Authorization:` header. Token expired, or basicAuth credentials wrong. |
| `403 Forbidden` | Authenticated but not permitted — your FeatureGroup doesn't include the required permission, or the resource is restricted by `access_groups`. |
| `404 Not Found` | UUID/id doesn't exist (or has just been DELETEd). Check spelling. |
| `405 Method Not Allowed` | Method not supported on the URI (e.g. `POST /api/smtp_server/`, `DELETE /api/encounter/` without an id). |
| `415 Unsupported Media Type` | Sent a content type the endpoint doesn't accept — should be rare since the API accepts json / form / multipart everywhere. |
| `500 Internal Server Error` | Most often: Scheduler couldn't reach Infinity, or Infinity returned an error during provisioning. Check the Scheduler-side logs (not in the API). |

---

## 4. Cross-references

- The Encounter object → [encounters.md](encounters.md)
- People model (PIN regex, host vs guest, IDP auth) → [participants-roles-aliases.md](participants-roles-aliases.md)
- Breakout routing semantics → [breakouts-and-interpreters.md](breakouts-and-interpreters.md)
- Token lifecycle → [auth-and-identity.md](auth-and-identity.md)
- Email pipeline → [email-and-branding.md](email-and-branding.md)
- Infinity provisioning failure modes → [infinity-integration.md](infinity-integration.md)
