# CoSpaces, Conferences, Meetings, and Call Control

This is the conferencing surface of the API. Three things live here:

| Concept | Resource | What it is |
|---|---|---|
| **CoSpace** (CMS) | `/cospace-acano/` | Persistent CMS Meeting Space. Has a URI, call ID, members, access methods. |
| **Conference** (Pexip) | `/cospace-pexip/` | Persistent Pexip Infinity VMR. Has aliases, theme, host/guest views. |
| **Unified read** | `/cospace/` | Read-only view that surfaces both CMS and Pexip spaces under the same shape. Does NOT support create. |
| **Scheduled meeting** | `/meeting/` | A future-time-bounded reservation (often tied to a CoSpace and one or more endpoints). |
| **Active call** | `/calls/` + `/call_legs/` | A live call in progress on a CMS or Pexip cluster. Disappears when the call ends. |

## CMS vs Pexip: which endpoint to use

The endpoint name tells you which backend a write goes to:

- `cospace-acano/` — writes to a CMS Call Bridge cluster ("acano" is the historical name for CMS).
- `cospace-pexip/` — writes to a Pexip Infinity cluster.
- `cospace/` — reads from whichever cluster the resource lives in; the unified ID format `{provider_type}:{external_id}` lets you address either.

You must know the **target cluster type** before choosing the endpoint. To decide programmatically:

1. List `/cluster/` and pick the one whose `type` matches your need (`pexip` or `acano`).
2. Or list `/provider/` and look at `subtype`: 1=CMS Call Bridge, 4=CMS Service Node, 2=Pexip Management Node, 6=Expressway, 7=CUCM.

The unified `/cospace/?type=cms` or `?type=pexip` filter helps you query a single backend through the unified read interface.

## Creating a CMS CoSpace

```python
c.post("/cospace-acano/", {
    "name": "Engineering Standup",
    "uri": "eng-standup",
    "call_id_generation_method": "increase",   # or "random", or "cospace"
    "owner_jid": "alice@example.com",
    "owner_as_member": True,                   # auto-add owner as a member
    "access_methods": [
        {"name": "Host",  "scope": "private", "uri_method": "call_id"},
        {"name": "Guest", "scope": "public",  "uri_method": "call_id"},
    ],
})
```

Key fields (`CoSpaceCreate` schema):

- `name` — display name.
- `uri` — the dial-string left-hand side (e.g. `eng-standup` → `eng-standup@cluster-domain`).
- `call_id` / `call_id_generation_method` — numeric ID. Generation method: `random` (slumpa), `increase` (next available), or omit to enter manually.
- `passcode` / `moderator_passcode` — guest and host PINs.
- `owner_jid` — JID of the CMS user who owns the cospace.
- `owner_email` — pre-fills owner from email lookup.
- `access_methods[]` — see below. CMS supports rich access-method configuration; Mividas exposes most of it.
- `organization_path` or `organization_unit` — assign to an organizational unit (Mividas concept, not CMS).
- `template_name` — apply a CMS Call Profile / Branding template by name.

## Access methods

Each AccessMethod gets its own URI and PIN policy:

| Field | Meaning |
|---|---|
| `name` | Display name (e.g. "Host", "Guest"). |
| `scope` | `public` (anyone can join), `private` (members only), `member` (member-only), `directory` (visible in directories). |
| `uri_method` | `call_id` reuses the numeric call ID as the URI; blank means enter manually. |
| `call_id_generation_method` | If `uri_method` is `call_id`: how to derive — `cospace` (same as parent), `random`, `increase`, or blank. |
| `passcode` | Per-access-method PIN. |
| `system_id` | Legacy backward-compat field for `guest` / `moderator` mapping. |
| `is_default` | Mark as the room's default access method. |
| `regenerate_secret` | On update: regenerate the WebRTC secret. |

## Pexip Conferences

```python
c.post("/cospace-pexip/", {
    "name": "Engineering Standup",
    "service_type": "conference",              # or "lecture", "two_stage_dialing", …
    "template_name": "default",
    "primary_owner_email_address": "alice@example.com",
    "pin": "1234",
    "allow_guests": True,
    "guest_pin": "0000",
    "aliases": [
        {"alias": "eng-standup@example.com", "description": "Primary"},
    ],
    "call_id_generation_method": "increase",
    "host_view": "one_main_seven_pips",
    "guest_view": "one_main_seven_pips",
})
```

The `Conference` schema is different from `CoSpace` — match field names exactly. Common gotchas:

- `pin` is the **host PIN**, `guest_pin` is the guest PIN (CMS uses `passcode` / `moderator_passcode` instead).
- `service_type` and `template_name` map to Pexip Management Node service configurations. They must already exist on the cluster.
- `host_view` and `guest_view` accept Pexip layout strings (`one_main_seven_pips`, `four_mains_zero_pips`, etc.) — see the `HostViewEnum` / `GuestViewEnum` in the spec for the full list.
- `aliases[]` are full alias strings (with domain). Each gets its own `description` field.

## CoSpace operations

| Endpoint | Use |
|---|---|
| `POST /cospace-acano/{id}/add_dialout/` | Persistent automatic dial-out target attached to the cospace. |
| `POST /cospace-acano/{id}/automatic_dialout/` | Returns the current automatic-dialout `hook_id` + sessions. |
| `POST /cospace-acano/{id}/disconnect_session/` | Disconnect a specific session (hook). |
| `POST /cospace-acano/{id}/remove_dialout/` | Remove a configured dial-out. |
| `GET /cospace-acano/{id}/access_methods/` | Inspect/manage access methods individually. |
| `POST /cospace-acano/bulk_create/` | Create many cospaces from one payload. |
| `GET /cospace-acano/changes/?date_start=&date_stop=` | Audit of added/removed cospaces in a window. |
| `POST /cospace-pexip/automatic_dialout/` | Pexip equivalent of CMS automatic dial-outs. |
| `POST /cospace-pexip/bulk_create/` | Bulk-create Pexip Conferences. |
| `GET /cospace/{id}/diagnostics/` | Active-call diagnostics for the cospace. |
| `GET /cospace/{id}/invite/` / `POST /cospace/{id}/send_invite_message/` | Generate / send invite emails. |
| `POST /cospace/bulk_delete/` | Bulk delete (CoSpaces by IDs). |

## Scheduled meetings (`/meeting/`)

A `Meeting` is a future-time-bounded reservation. Typical sources:

1. **Mividas Portal** end-user booking.
2. **Calendar sync** (EWS / MS Graph room mailboxes).
3. **API**: `POST /meeting/` with `MeetingCreate`.

Lifecycle:

- `status`: `future` → `ongoing` → `ended` / `ended_deprovisioned` / `cancelled` / `superseded` / `placeholder`.
- `was_activated` flips true when at least one participant joined.
- `ts_unbooked` is set when the meeting was actively cancelled.

Useful filters on `GET /meeting/`:

- `ts_start` (required) and `ts_stop` to scope by time.
- `only_active`, `include_external`, `only_endpoints` toggles.
- `endpoints[]` to filter to meetings involving a specific endpoint.
- `cospace`, `dialout_uri`, `title`, `creator` text filters.

Special endpoints:

- `GET /meeting/in_call/` — only meetings currently in call.
- `GET /meeting/{id}/calls/` — paginated `CallIncludeLegs` for the meeting's calls.
- `GET /meeting/{id}/diagnostics/` and `download_diagnostics/` — debug a problematic meeting.
- `GET /meeting/{id}/invite_message/` / `POST /meeting/{id}/send_invite_message/` — invite rendering.

## Active calls and call legs

`Call` is one logical conference instance; `CallLeg` is one participant's connection. CoSpaces persist; calls and legs exist only while live.

### Listing live calls

```python
calls = c.get("/calls/")                 # bare array (NOT paginated)
for call in calls:
    print(call["cospace"], call["legs"])
```

`/calls/?` filters: there's no `q=` search; filter client-side. Each `GenericCall` includes its current legs (`GenericNestedCallLeg`).

### Per-call control

| `POST /calls/{id}/...` | What it does |
|---|---|
| `lock/` (POST=lock, DELETE=unlock) | Lock the conference. |
| `record/` (POST=start, DELETE=stop) | Start/stop recording. |
| `stream/` (POST=start, DELETE=stop) | Start/stop streaming. |
| `set_layout/` | Set the call-wide layout (`GenericSetCallLayout`). |
| `set_all_mute/` | Mute every participant (audio). |
| `set_all_video_mute/` | Mute every participant (video). |
| `send_notice/` | Display an on-screen notice; `{message, duration}` in seconds. |
| `bulk_send_notice/` | One payload, many calls. |
| `send_notice_to_all/` | One payload, every active call. |

`GET /calls/{id}/legs/` returns the full leg list; `/calls/{id}/meeting/` returns the matching `Meeting` (with `MeetingWithDialouts`) if known.

### Per-leg control (`/call_legs/{id}/...`)

`call_legs` IDs are MCU-side leg IDs (UUIDs on CMS, opaque strings on Pexip):

| Action | Notes |
|---|---|
| `set_mute/` (POST=mute, DELETE=unmute) | Audio mute. |
| `set_video_mute/` | Video mute. |
| `set_moderator/` (POST/DELETE) | Promote/demote moderator (CMS). |
| `set_lock/` (POST/DELETE) | Per-leg lock (`CallControlParticipantFlag`). |
| `set_raised_hand/` (POST/DELETE) | Raise/lower hand. |
| `set_name/` | Rename the participant. |
| `set_layout/` | Per-leg layout override. |
| `set_importance/` | Pin / set importance for layout weighting. |
| `send_dtmf/` | Send DTMF (`CallControlParticipantDtmf`). |
| `move_to_call/` | Move a leg to another call (transfer). |

`POST /call_legs/` creates a new leg (dial-out into a call) using `GenericCreateCallLeg` — fields include `call_id`, `remote`, `name`, `protocol` (`sip`/`h323`/`mssip`/`rtmp`/`gms`/`teams`), `call_type` (`audio`/`video`/`video-only`/`streaming`), `role`, optional `dtmf_sequence` for post-connect DTMF.

`GET /call_legs/?call=<call_id>` lists legs of one call; `?cospace=<cospace_id>` lists legs of one cospace. Add `?full=true` for a heavier `GenericCallLeg` payload, or `?include_participant=true` to embed participant metadata.

## Recurring meetings

`Meeting.recurring_master` (FK) and `Meeting.is_recurring` indicate series membership; the create endpoint accepts `MeetingCreate.recurring` as an iCalendar RRULE string (`RRULE:FREQ=WEEKLY;COUNT=2`). The master "placeholder" meeting has `status: placeholder` and won't run; individual instances are concrete `future` / `ongoing` / `ended` meetings.

## Common pitfalls

- The `/cospace/` (unified) endpoint **cannot create** — POST returns 405. Use `/cospace-acano/` or `/cospace-pexip/`.
- CoSpace `password` / `lobby_pin` / `moderator_password` / `title` are deprecated aliases of `passcode` / `moderator_passcode` / `moderator_passcode` / `name`. New code should use the canonical names; reads return both.
- Active-call ID format differs per backend: CMS gives you UUIDs, Pexip gives you opaque strings. Treat them as opaque.
- `/calls/` is a bare array — see [gotchas-and-conventions.md](gotchas-and-conventions.md#paginated-vs-bare-list-responses).
- Cancelling a meeting is `DELETE /meeting/{id}/`. The meeting becomes `cancelled` (with `ts_unbooked` set) but is not purged immediately — historical analytics still see it.
