# Breakout rooms and interpreters

Two related topics that both come down to **role-driven routing**.
Breakouts route by role; interpreters are participants in a role
flagged as interpretive, with extra wiring via `language` and
`paired_participant`.

---

## 1. The BreakoutRoom object

Endpoints under `/api/breakout_room/` — full CRUD. Also creatable
inline as nested `breakout_rooms` on `POST /api/encounter/`.

### Schema

| Field | Type | Required | Notes |
|---|---|---|---|
| `id` | int64, readOnly | — | Scheduler-local id |
| `encounter` | uuid | ✅ | Owning meeting. Not required when nested. |
| `name` | string ≤250 | ✅ | Display name in the meeting UI |
| `role` | int FK → `role.id` | ✅ | **All participants with this role join this breakout on entry.** |
| `breakout_id` | uuid, readOnly | ✅ (read) | Server-assigned UUID; this is the id used by Infinity for the actual sub-conference |
| `locked` | bool, default `false` | — | If true, participants arrive in a waiting room and a host must admit them |

### How a participant lands in a breakout

When a meeting starts:

1. Each EncounterParticipant joins the meeting via their `participant_aliases`.
2. Infinity reads the participant's `role` (via the Scheduler).
3. If the participant's role has `host: true`, they land in the **main VMR**.
4. Otherwise, the Scheduler looks for a `BreakoutRoom` with `role` equal to
   their role.
   - If found, the participant lands in that breakout's sub-conference.
   - If not found, the participant lands in the main VMR (same as host).
   - If the breakout is `locked: true`, they land in the **breakout's waiting
     room** until a host admits them.

So: **a non-host role with no matching breakout behaves like a host
role.** Don't rely on `host: false` alone to keep guests out of the main
room; you also need a breakout room for them.

### The ad-hoc guest breakout

Every Encounter has an `adhoc_guest_breakout_id` (readOnly UUID, required
on the response). This is an auto-created breakout for **ad-hoc / unknown
dial-ins** — people who dial the meeting's main alias but aren't a known
EncounterParticipant. Infinity routes them into this breakout so they
don't accidentally land in the host room with the chair.

You can't change or delete this — it's part of every encounter.

---

## 2. `breakout_rooms_mode` — the master switch

On the **Encounter**, the `breakout_rooms_mode` enum controls how
breakouts behave:

| Value | Behaviour |
|---|---|
| `OFF` | No breakouts. All participants land in the main VMR regardless of role. |
| `MANUAL` | Breakouts exist but participants do **not** auto-route — a host must move people in/out via the conference UI. |
| `AUTOMATIC` | Breakouts auto-route on join based on `role`. (This is the default.) |

The default comes from `global_settings.default_breakout_rooms_mode`,
which itself defaults to `AUTOMATIC`.

| If you want… | Use… |
|---|---|
| Plain meeting, everyone in one room | `OFF` |
| Mostly one room, host occasionally pulls a small group aside | `MANUAL` (don't bother creating breakout rooms unless needed) |
| Pre-divided meeting — different teams in different breakouts from the start | `AUTOMATIC` + create BreakoutRooms keyed off non-host roles |
| Pre-divided meeting + host can pull people back to the main room | `AUTOMATIC` — the host can always pull a guest into the main room from the meeting UI |

---

## 3. Interpreters

Pexip Infinity supports **language interpretation channels**: an
interpreter speaks on a separate audio channel, and each listener picks
which language to hear. The Scheduler models this with three pieces:

1. A `Role` with `interpreter: true`
2. `Language` rows for each spoken or sign language
3. EncounterParticipants of the interpreter role with `language` and
   (optionally) `paired_participant` set.

### Language resource

Endpoints under `/api/language/` — full CRUD.

| Field | Type | Required | Notes |
|---|---|---|---|
| `id` | int64, readOnly | — | |
| `name` | string ≤250 | ✅ | "English", "Norwegian", "Auslan", etc. |
| `kind` | enum `SPOKEN`/`SIGN`, default `SPOKEN` | — | |

The Scheduler's `language.name` must align with **whatever Pexip Infinity
expects** for the matching language id/label. Pexip Infinity's IVR
language list (under System > IVR languages) is the source of truth — if
you call a language `Norsk Bokmål` on the Scheduler but `Norwegian` on
Infinity, the binding fails silently.

### Wiring an interpreter into an encounter

```json
POST /api/role/
{ "name": "Interpreter NO→EN", "host": false, "interpreter": true }
# → id 7

POST /api/language/
{ "name": "English", "kind": "SPOKEN" }
# → id 1

POST /api/language/
{ "name": "Norwegian", "kind": "SPOKEN" }
# → id 2

POST /api/participant/
{ "display_name": "Carla Interpreter", "authentication_method": "PIN", "pin": "12345678" }
# → id 99

POST /api/encounter/
{
  "name": "Bilingual Meeting",
  "vmr": "bilingual",
  "start_date": "2026-06-01",
  "start_time": "10:00:00",
  "end_time": "11:00:00",
  "timezone": "Europe/Oslo",
  "main_language": 2,
  "encounter_participants": [
    { "participant": 42, "role": 1 },                                    /* Norwegian-speaking chair */
    { "participant": 43, "role": 2 },                                    /* Norwegian-speaking guest */
    { "participant": 50, "role": 2 },                                    /* English-speaking guest */
    { "participant": 99, "role": 7, "language": 1, "paired_participant": null }  /* Carla interprets *into* English */
  ]
}
```

Breakdown:

- `encounter.main_language = 2` (Norwegian) — the floor language.
- Carla's EncounterParticipant has `role = 7` (interpreter role),
  `language = 1` (English — the *output* language she speaks),
  and `paired_participant = null` (she's interpreting the floor for
  anyone, not a specific person).
- English-speaking guests in the meeting pick the "English"
  interpretation channel in their Pexip client; they hear Carla
  rather than the floor audio.

### When to use `paired_participant`

Use `paired_participant` for **shadow / chuchotage / signed**
interpretation, where one interpreter is dedicated to **one specific
participant's** audio stream rather than the room floor. The
interpreter listens to that one person and speaks (or signs) on a
dedicated channel.

For most generic conference interpretation, leave it `null`.

### Two-way interpretation

For bi-directional interpretation (e.g. someone speaking English needs
to be heard in Norwegian and vice versa), you typically need **two
interpreters** — one per direction — each as a separate
EncounterParticipant with its own `language`:

```
EncounterParticipant { participant: Carla,  role: Interp(NO→EN), language: English }
EncounterParticipant { participant: David,  role: Interp(EN→NO), language: Norwegian }
```

A single interpreter cannot serve both directions on Infinity at once;
they need separate channels.

### Sign-language interpreters

Same pattern, just with `language.kind = SIGN`. The interpreter's
**video** stream becomes the "sign language channel" — listeners
opt-in via the client UI. Practical considerations:

- Sign interpreters need video on; if `mute_all_guests: true` they may
  also have video disabled depending on the Infinity config — verify.
- Bandwidth: a signer's video should ideally be pinned for clarity;
  set the encounter's `pinning_config` so their feed is foregrounded.

---

## 4. Common breakout patterns

### Pattern: pre-assigned breakouts

```
Roles:    Chair (host), Eng (guest), Sales (guest), Marketing (guest)
BreakoutRooms (per encounter):
  - { name: "Engineering", role: <Eng id> }
  - { name: "Sales",       role: <Sales id> }
  - { name: "Marketing",   role: <Marketing id> }
breakout_rooms_mode: AUTOMATIC
```

On meeting start, chair lands in main room; engineering folks land in
the Engineering breakout, etc. Chair can pull anyone into the main room.

### Pattern: locked breakout for vetting guests

```
Roles:    Chair (host), External (guest)
BreakoutRoom: { name: "Waiting Room", role: <External id>, locked: true }
breakout_rooms_mode: AUTOMATIC
```

External participants join into the locked breakout; chair admits them
one by one. (This is "waiting room" semantics — the breakout is the
waiting room.)

### Pattern: chair-controlled ad-hoc breakouts

```
Roles:    Chair (host), Guest (guest)
BreakoutRoom: none (or some empty ones to populate manually)
breakout_rooms_mode: MANUAL
```

Everyone starts in the main room; the chair creates breakouts on the
fly via the conference UI and moves people in/out. Use this when you
don't know up front who will need to be in which breakout.

### Pattern: completely flat meeting

```
Roles:    Chair (host), Attendee (guest)
breakout_rooms_mode: OFF
```

Even if you accidentally have breakout rooms configured, `OFF` ignores
them and everyone stays in the main room.

---

## 5. Cross-references

- The Encounter object that owns these breakouts → [encounters.md](encounters.md)
- The Role / Participant / EncounterParticipant link rows → [participants-roles-aliases.md](participants-roles-aliases.md)
- How Infinity actually executes the breakout routing (the underlying conference + sub-conference model) → [infinity-integration.md](infinity-integration.md)
