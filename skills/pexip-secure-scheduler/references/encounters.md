# Encounters — the meeting object

The **Encounter** is the only per-meeting object in the system. Everything
else (Participants, Roles, AliasTemplates, Themes) is library / tenant-wide
configuration. Get the Encounter model right and the rest follows.

Endpoints (all under `/api/encounter/`):

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/encounter/` | List (paginated; `limit`, `offset`) |
| POST | `/api/encounter/` | Create — nested `encounter_participants` + `breakout_rooms` supported |
| GET | `/api/encounter/{uuid}/` | Retrieve |
| PUT | `/api/encounter/{uuid}/` | **Replace** — must send all required fields |
| PATCH | `/api/encounter/{uuid}/` | **Partial update** — safe default for changes |
| DELETE | `/api/encounter/{uuid}/` | Cancel & remove (also tears down the Infinity VMR) |

The id is a **UUID**, not an integer — this is unusual in this API
(Participants, Roles, BreakoutRooms etc. all use int64 ids). Treat
encounter ids as opaque strings.

---

## 1. Schema field-by-field

Source: `Encounter` / `EncounterRequest` in `secure_scheduler_schema.yaml`.

### Identity & scheduling

| Field | Type | Required | Notes |
|---|---|---|---|
| `id` | uuid, readOnly | — | Server-assigned on create |
| `name` | string ≤250 | ✅ | Human-readable meeting name |
| `vmr` | string ≤250 | ✅ | **Conference Name Prefix** — becomes the Infinity VMR name. Defaults to `name` if not set, but the spec still requires it on POST. |
| `description` | string ≤250 | — | Free text, shown in the invite |
| `start_date` | `date` (YYYY-MM-DD) | ✅ | First day. **Not** a datetime — see gotchas. |
| `end_date` | `date`, nullable | — | Last day, for multi-day events |
| `all_day` | bool, default `false` | — | If true, `start_time`/`end_time` ignored |
| `start_time` | `time` (HH:MM:SS), nullable | — | Start clock time in `timezone` |
| `end_time` | `time` (HH:MM:SS), nullable | — | End clock time in `timezone` |
| `timezone` | enum (400+ IANA names) | — | e.g. `Europe/Oslo`, `America/Los_Angeles`. **Must** be from the fixed enum; `"UTC"` works, `"EST"` and offset strings do not. |
| `recurrence` | string, nullable | — | Opaque recurrence rule. ⚠️ **Verify version** — Pexip's Scheduling Core consumes iCalendar `RRULE` strings (e.g. `FREQ=WEEKLY;BYDAY=MO;COUNT=10`) but the spec gives no validation hint. |
| `mail_sequence` | int, default `0` | — | **iCalendar SEQUENCE counter.** Increment before sending an update invite — see §5. |

### Behaviour toggles

| Field | Type | Default | Notes |
|---|---|---|---|
| `enable_chat` | bool | `true` | Chat in main room + breakouts |
| `enable_overlay_text` | bool | `true` | Participant name overlay |
| `guests_can_present` | bool | `true` | Permit non-host content share |
| `mute_all_guests` | bool | `false` | Auto-mute guests on join |
| `participant_limit` | int, nullable | — | Hard cap, 0–2147483647 |

### Branding / layout (Infinity-side references)

| Field | Type | Default | Notes |
|---|---|---|---|
| `theme` | int FK → `theme.id`, nullable | — | IVR theme used in the main room. The theme is configured on Pexip Infinity; the Scheduler references it by name. See [infinity-integration.md](infinity-integration.md). |
| `breakout_room_theme` | int FK → `theme.id`, nullable | — | Separate theme for breakouts. Falls back to `theme` when unset. |
| `pinning_config` | string ≤50 | — | Pinning configuration name. Must be one of the `pinning_configs` declared on the selected `theme`. |
| `view` | int FK → `view.id` | — | Pexip Infinity **Layout** to use in the main VMR (e.g. `1:7`, `1:21`). |

### Audio / interpretation / streaming

| Field | Type | Default | Notes |
|---|---|---|---|
| `main_language` | int FK → `language.id`, nullable | — | The primary spoken language. Used to wire interpreters. |
| `rtmp_streams` | array of int FK → `rtmp_stream.id` | `[]` | Up to **5** RTMP destinations to push the conference to. |

### Routing / access

| Field | Type | Default | Notes |
|---|---|---|---|
| `breakout_rooms_mode` | enum: `OFF`/`MANUAL`/`AUTOMATIC` | `AUTOMATIC` (per `global_settings.default_breakout_rooms_mode`) | Whether to use breakout rooms. See [breakouts-and-interpreters.md](breakouts-and-interpreters.md). |
| `access_groups` | array of int FK → `access_group.id` | `[]` | Which access groups are permitted to schedule / view this encounter. |
| `created_by` | int FK → user, nullable, readOnly-ish | — | The portal user that created the meeting. |

### Read-only / derived

| Field | Type | Notes |
|---|---|---|
| `adhoc_guest_breakout_id` | uuid, **readOnly, required** | Every encounter has one auto-created breakout room for ad-hoc / guest dial-ins (people who join without a known participant). This UUID is the breakout's id; you don't create or modify it. |
| `encounter_aliases` | array of strings, readOnly | The dial aliases for the meeting itself (separate from per-participant aliases). Generated from active AliasTemplates. |
| `encounter_participants` | array of `NestedEncounterParticipant` | The participants of this meeting; can be **populated inline on POST**, otherwise managed via `/api/encounter_participant/`. |
| `breakout_rooms` | array of `NestedBreakoutRoom` | The breakout rooms of this meeting; can be populated inline on POST, otherwise via `/api/breakout_room/`. |

---

## 2. Create — minimal vs. fully nested

**Minimal** (the meeting itself, no participants/breakouts yet):

```json
POST /api/encounter/
{
  "name": "Quick Sync",
  "vmr": "quick-sync",
  "start_date": "2026-06-01",
  "start_time": "09:00:00",
  "end_time": "09:30:00",
  "timezone": "Europe/Oslo"
}
```

Then add participants and breakouts in follow-up calls to
`/api/encounter_participant/` and `/api/breakout_room/`.

**Fully nested** (one request creates the whole graph):

```json
POST /api/encounter/
{
  "name": "Quarterly Review",
  "vmr": "quarterly-review",
  "start_date": "2026-06-15",
  "start_time": "14:00:00",
  "end_time": "16:00:00",
  "timezone": "Europe/Oslo",
  "description": "Q2 readout + breakouts",
  "theme": 3,
  "view": 2,
  "main_language": 1,
  "enable_chat": true,
  "guests_can_present": false,
  "mute_all_guests": true,
  "breakout_rooms_mode": "MANUAL",
  "participant_limit": 50,
  "encounter_participants": [
    { "participant": 42, "role": 1 },
    { "participant": 43, "role": 2 },
    { "participant": 44, "role": 3, "language": 5, "paired_participant": 42 }
  ],
  "breakout_rooms": [
    { "name": "Sales breakout", "role": 4, "locked": false },
    { "name": "Engineering breakout", "role": 5, "locked": true }
  ]
}
```

Notes:

- Nested participants use `NestedEncounterParticipantRequest` — required:
  `participant`, `role`. Don't include `encounter` (the parent supplies it).
- Nested breakouts use `NestedBreakoutRoomRequest` — required: `name`, `role`.
  Don't include `encounter`.
- The server fills in `participant_aliases` from your AliasTemplates,
  generates the `breakout_id` UUID for each breakout, and assigns an
  `adhoc_guest_breakout_id` to the encounter.

---

## 3. Read — list & filter

```
GET /api/encounter/?limit=20&offset=0
```

Response shape (consistent across all `*_list` endpoints):

```json
{
  "count": 137,
  "next": "https://scheduler.example.com/api/encounter/?limit=20&offset=20",
  "previous": null,
  "results": [ /* 20 Encounter objects */ ]
}
```

**There is no built-in search/filter** on Encounter beyond pagination.
Some other endpoints (`access_group`, `alias_template`, etc.) expose
`name` / `name__contains` query params; Encounter does **not**. Plan to
either fetch and filter client-side or store your own index.

---

## 4. Update & cancel

**Default to PATCH** unless you really mean to replace the whole record.

```json
PATCH /api/encounter/{uuid}/
{
  "end_time": "16:30:00",
  "description": "Q2 readout + breakouts — extended by 30 min"
}
```

**Reschedule** (change date/time):

```json
PATCH /api/encounter/{uuid}/
{
  "start_date": "2026-06-16",
  "start_time": "14:00:00",
  "end_time": "16:00:00",
  "mail_sequence": 1
}
```

**Add a participant** to an existing meeting — call `encounter_participant`
directly:

```json
POST /api/encounter_participant/
{
  "encounter": "8b3e3f44-…",
  "participant": 99,
  "role": 2
}
```

**Cancel** (deletes the encounter and the underlying Infinity VMR):

```
DELETE /api/encounter/{uuid}/
```

If you've already sent calendar invites, you typically want to send a
**cancellation email** *before* the DELETE, otherwise recipients won't
get the iCalendar METHOD:CANCEL message. The `command/send_email` endpoint
takes a `cancel: true` flag for exactly this:

```json
POST /api/command/send_email
{ "encounter": "8b3e3f44-…", "participant": 42, "cancel": true }
```

Then DELETE.

---

## 5. Recurrence and the iCalendar SEQUENCE counter

`recurrence` is **opaque** in the OpenAPI spec — `type: string, nullable: true`,
no pattern, no description. Pexip Scheduling Core consumes iCalendar `RRULE`
strings, e.g.:

| Goal | RRULE |
|---|---|
| Weekly on Mondays, 10 occurrences | `FREQ=WEEKLY;BYDAY=MO;COUNT=10` |
| Every weekday for 4 weeks | `FREQ=DAILY;BYDAY=MO,TU,WE,TH,FR;COUNT=20` |
| Monthly on the 1st, indefinitely | `FREQ=MONTHLY;BYMONTHDAY=1` |
| Every 2nd Tuesday, ending 2026-12-31 | `FREQ=WEEKLY;INTERVAL=2;BYDAY=TU;UNTIL=20261231T235959Z` |

⚠️ **Verify against your version** before committing to RRULE in production
— the spec does not document the exact accepted syntax, and Scheduling Core
may apply stricter rules than RFC 5545 (e.g. it may reject `BYSETPOS` or
sub-day intervals).

### `mail_sequence` — why it matters

`mail_sequence` is an integer counter (`int`, default `0`) that maps directly
to the iCalendar **SEQUENCE** property in the invite email. iCalendar clients
(Outlook, Apple Calendar, Google) use SEQUENCE to decide whether an updated
invite supersedes the original. **If you don't bump it, the update is
silently ignored** by most clients.

**Lifecycle:**

```
POST /api/encounter/         → mail_sequence: 0  (initial invite has SEQUENCE:0)
POST /api/command/send_email → invites sent

PATCH /api/encounter/{id}/ { mail_sequence: 1, end_time: "..." }
POST /api/command/send_email → updated invite has SEQUENCE:1 (overrides)

PATCH /api/encounter/{id}/ { mail_sequence: 2, start_date: "..." }
POST /api/command/send_email → another update overrides
```

A simple rule: **bump `mail_sequence` by 1 on every PATCH that changes the
when, the where, or the who.** Don't bump it for cosmetic changes (a
description tweak that you're not re-sending an invite for).

---

## 6. EncounterTemplate — saved meeting presets

Endpoints: `/api/encounter_template/` (full CRUD).

An `EncounterTemplate` is a saved preset — a user creates one for "my
standard customer call" or "weekly all-hands" and applies it when scheduling
new meetings. It mirrors most of the Encounter fields with an `encounter_`
prefix:

| Field | Maps to Encounter field |
|---|---|
| `name` | (template name, not the encounter name) |
| `user` | The portal user that owns the template (required) |
| `created` | readOnly timestamp |
| `encounter_name` | `name` |
| `encounter_vmr` | `vmr` |
| `encounter_description` | `description` |
| `encounter_timezone` | `timezone` |
| `encounter_main_language` | `main_language` |
| `encounter_enable_chat` | `enable_chat` |
| `encounter_enable_overlay_text` | `enable_overlay_text` |
| `encounter_guests_can_present` | `guests_can_present` |
| `encounter_mute_all_guests` | `mute_all_guests` |
| `encounter_theme` | `theme` |
| `encounter_pinning_config` | `pinning_config` |
| `encounter_breakout_room_theme` | `breakout_room_theme` |
| `encounter_participant_limit` | `participant_limit` |
| `encounter_view` | `view` |
| `encounter_rtmp_streams` | `rtmp_streams` |
| `encounter_breakout_rooms_mode` | `breakout_rooms_mode` |
| `encounter_participants` | `encounter_participants` (nested) |
| `encounter_breakout_rooms` | `breakout_rooms` (nested) |
| `encounter_access_groups` | `access_groups` |
| `encounter_enable_interpretation` | (controls whether interpretation is enabled in instantiated meetings; no direct equivalent on Encounter — surfaces via interpreter participants instead) |

Templates have **no** `start_date`, `start_time`, `end_time`, `recurrence`,
or `mail_sequence` — those are per-instance. The Scheduler UI applies a
template by copying its `encounter_*` fields into a new POST to
`/api/encounter/` and letting the user fill in the scheduling fields.

If you're building a portal that wants saved presets, model your "preset"
button as: GET the EncounterTemplate, copy its fields into your encounter
POST, and let the user override.

---

## 7. Worked example — recurring weekly meeting with breakouts + interpreter

Pre-requisites (created **once**, library-side):

- Role `Chair` (id=1, `host: true`)
- Role `Guest` (id=2, `host: false`)
- Role `Interpreter` (id=3, `host: false`, `interpreter: true`)
- Role `Eng Breakout` (id=4, `host: false`)
- Role `Sales Breakout` (id=5, `host: false`)
- Language `Norwegian` (id=1, `kind: SPOKEN`), `English` (id=2)
- AliasTemplate `meet.{{ participant.long_alias }}@example.com` (SIP+H323+WEB)
- Participants: Alice (id=42, Chair-eligible), Bob (id=43), Carla (id=44, interpreter), various engineers and salespeople (ids 50–60)
- Theme `Acme-Theme` (id=3), View `1:7` (id=2), RTMP stream `Internal Mirror` (id=1)

Now schedule the meeting:

```json
POST /api/encounter/
{
  "name": "Acme Weekly All-Hands",
  "vmr": "acme-allhands",
  "description": "Weekly all-hands with breakouts; NO/EN interpretation",
  "start_date": "2026-06-01",
  "start_time": "15:00:00",
  "end_time": "16:00:00",
  "timezone": "Europe/Oslo",
  "recurrence": "FREQ=WEEKLY;BYDAY=MO;COUNT=20",
  "theme": 3,
  "breakout_room_theme": 3,
  "view": 2,
  "main_language": 1,
  "rtmp_streams": [1],
  "breakout_rooms_mode": "MANUAL",
  "participant_limit": 80,
  "enable_chat": true,
  "guests_can_present": false,
  "mute_all_guests": true,
  "encounter_participants": [
    { "participant": 42, "role": 1, "auto_dial": false },
    { "participant": 43, "role": 2, "auto_dial": false },
    { "participant": 44, "role": 3, "language": 2, "paired_participant": 42 },
    { "participant": 50, "role": 4 },
    { "participant": 51, "role": 4 },
    { "participant": 52, "role": 5 },
    { "participant": 53, "role": 5 }
  ],
  "breakout_rooms": [
    { "name": "Engineering", "role": 4, "locked": false },
    { "name": "Sales", "role": 5, "locked": false }
  ]
}
```

Response (abridged):

```json
{
  "id": "8b3e3f44-9c8a-4f1a-9c2d-5b1f3a7e9c11",
  "name": "Acme Weekly All-Hands",
  "vmr": "acme-allhands",
  "adhoc_guest_breakout_id": "f0a2…",
  "encounter_aliases": ["acme-allhands@example.com", ...],
  "mail_sequence": 0,
  "encounter_participants": [
    {
      "id": 1001,
      "participant": 42,
      "role": 1,
      "participant_aliases": ["meet.5f3a-…@example.com"],
      "auto_dial": false
    },
    ...
  ],
  "breakout_rooms": [
    { "id": 201, "breakout_id": "a1…", "name": "Engineering", "role": 4, "locked": false },
    { "id": 202, "breakout_id": "b2…", "name": "Sales", "role": 5, "locked": false }
  ]
}
```

Send invites to everyone:

```bash
for PID in 42 43 44 50 51 52 53; do
  curl -X POST https://scheduler.example.com/api/command/send_email \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d "{ \"encounter\": \"8b3e3f44-…\", \"participant\": $PID }"
done
```

Three weeks later, the chair wants to extend the meeting to 90 minutes:

```json
PATCH /api/encounter/8b3e3f44-…/
{ "end_time": "16:30:00", "mail_sequence": 1 }
```

Then resend invites (only to the affected attendees — typically all).

That's the full life-cycle.

---

## 8. Cross-references

- Participant / Role / EncounterParticipant / AliasTemplate field detail → [participants-roles-aliases.md](participants-roles-aliases.md)
- Breakout room semantics, `breakout_rooms_mode` behaviour, interpreter setup → [breakouts-and-interpreters.md](breakouts-and-interpreters.md)
- The `command/send_email` and `command/generate_email` request shapes + the Jinja2 variables in scope → [email-and-branding.md](email-and-branding.md)
- How `vmr`, `theme`, `view` map onto Pexip Infinity → [infinity-integration.md](infinity-integration.md)
- All the DRF / API conventions (pagination, PUT vs PATCH, etc.) → [gotchas-and-conventions.md](gotchas-and-conventions.md)
