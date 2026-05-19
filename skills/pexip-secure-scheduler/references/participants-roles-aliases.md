# Participants, Roles, EncounterParticipants, and Alias Templates

This is the "people side" of the Scheduler. Four resources, tightly
coupled:

```
Participant  ─── (reusable profile: name, email, PIN/IDP, dialout) ──┐
                                                                     │
Role         ─── (reusable: name, host?, interpreter?) ──────────────┤
                                                                     │ both
                                                                     │ referenced
                                                                     │ by
                                                                     ▼
EncounterParticipant  ─── (link row: who has what role in which meeting,
                          + generated dial aliases, + interpreter pairing)

AliasTemplate ─── (Jinja2 template used to generate the aliases on
                  every EncounterParticipant, per protocol)
```

---

## 1. Participant

A **reusable profile** for someone (or something — kiosks count) that can
join meetings. Don't create a new Participant for every meeting; create
one and link it via EncounterParticipants.

Endpoints under `/api/participant/` — full CRUD (`list`, `create`,
`retrieve`, `replace` [PUT], `partial_update` [PATCH], `destroy`).

### Schema

| Field | Type | Required | Notes |
|---|---|---|---|
| `id` | int64, readOnly | — | Integer id (not UUID) |
| `display_name` | string ≤250 | ✅ | Shown in the meeting overlay. Participants can change this themselves unless `enforce_display_name` is set. |
| `enforce_display_name` | bool, default `false` | — | When true, the participant cannot rename themselves in-call. |
| `description` | string ≤250 | — | Free-text note (admin-only) |
| `email` | string ≤100 | — | Where invites are sent. Defaults to `""`. |
| `dialout_alias` | string ≤250 | — | Where to dial out to this participant when `auto_dial` is on. Empty string by default. |
| `dialout_alias_protocol` | enum `SIP`/`H323`/`WEB`/null | — | Protocol for the dialout. Null when no dialout. |
| `authentication_method` | enum `PIN`/`IDP`/`""` | ✅ | How the participant proves who they are. Empty string = no authentication. |
| `pin` | string, default `""` | — | Only meaningful when `authentication_method == "PIN"`. Pattern: `^((\d{3,19}#)|(\d{4,20}))?$` — 4–20 digits, or 3–19 digits + `#`. |
| `identity_provider` | int FK → `identity_provider.id`, nullable | — | Only meaningful when `authentication_method == "IDP"`. Points to an IdP row (mapping to an Infinity-configured IdP). |
| `identity_provider_value` | string ≤250 | — | The expected attribute value from the IdP response that grants this participant entry. See [auth-and-identity.md](auth-and-identity.md). |

### Authentication method semantics

| `authentication_method` | What happens when they join |
|---|---|
| `""` (empty) | No authentication — they walk in by knowing the dial alias |
| `"PIN"` | Infinity prompts for the participant's `pin` value |
| `"IDP"` | Infinity redirects to the configured SSO IdP, requires the IdP-supplied attribute to match `identity_provider_value` |

The participant `pin` is **per-participant**, not per-meeting. If you
want a single meeting-wide PIN (e.g. for ad-hoc dial-ins), that's an
**Infinity VMR PIN** — configured on Infinity, not in the Scheduler.

### PIN regex — common mistakes

The pattern `^((\d{3,19}#)|(\d{4,20}))?$` accepts:

- `""` (empty) → no PIN
- `"1234"`, `"12345678"`, `"12345678901234567890"` → 4–20 digits
- `"123#"`, `"12345#"`, `"1234567890123456789#"` → 3–19 digits + trailing `#`

It rejects:

- `"123"` — too short, and no `#`
- `"#1234"` — `#` in the wrong place
- `"1234#5"` — anything after `#`
- `"abcd"`, `"12-34"` — non-digits

Validate on the client; a malformed PIN comes back as a 400 with no
hint about which field.

### Create example

```json
POST /api/participant/
{
  "display_name": "Alice Example",
  "email": "alice@example.com",
  "authentication_method": "PIN",
  "pin": "742918",
  "dialout_alias": "alice@example.com",
  "dialout_alias_protocol": "SIP"
}
```

For an IdP-authenticated participant:

```json
POST /api/participant/
{
  "display_name": "Bob Example",
  "email": "bob@example.com",
  "authentication_method": "IDP",
  "identity_provider": 7,
  "identity_provider_value": "bob@example.com"
}
```

---

## 2. Role

A **reusable label** that determines (a) where in the meeting a
participant lands, and (b) whether they're an interpreter.

Endpoints under `/api/role/` — full CRUD.

### Schema

| Field | Type | Required | Notes |
|---|---|---|---|
| `id` | int64, readOnly | — | |
| `name` | string ≤250 | ✅ | e.g. "Chair", "Guest", "Sales Breakout", "Interpreter NO→EN" |
| `host` | bool | ✅ | **`true`** → joins the main VMR. **`false`** → joins the breakout room attached to this role (if any); falls back to the main VMR. |
| `interpreter` | bool, default `false` | — | When true, participants with this role are interpreters (see §3 below). |
| `description` | string ≤250 | — | Admin-only note. |

### Role design patterns

**Pattern A — only need host vs guest:** create two roles, `Chair`
(`host: true`) and `Guest` (`host: false`). Every EncounterParticipant
uses one of these.

**Pattern B — breakouts by role:** for each breakout room you'll ever
need, create a dedicated guest role. Example for a team meeting:

```
Chair          (host: true)
Eng Breakout   (host: false)
Sales Breakout (host: false)
Marketing Breakout (host: false)
```

Then on each meeting, attach `BreakoutRoom` rows that name the
target role:

```
BreakoutRoom { name: "Engineering", role: <Eng Breakout id> }
BreakoutRoom { name: "Sales",       role: <Sales Breakout id> }
BreakoutRoom { name: "Marketing",   role: <Marketing Breakout id> }
```

A participant with `role = Eng Breakout` automatically lands in the
Engineering breakout.

**Pattern C — interpreters:** one role per interpreter "direction" is
cleanest, e.g. `Interpreter NO→EN`, `Interpreter EN→FR`. Each has
`host: false`, `interpreter: true`. See §3.

### Roles are global

Roles are **tenant-wide** — there is no scoping to a specific user,
encounter, or access group. If you serve multiple customers from one
Scheduler instance, namespace your role names yourself
(`acme-chair`, `globex-chair`) or you'll get collisions in the UI.

---

## 3. EncounterParticipant — the link row

The bridge between a Participant and an Encounter. Endpoints under
`/api/encounter_participant/` — full CRUD — **and** these objects can
also be created inline as a nested array on `POST /api/encounter/` (see
[encounters.md](encounters.md) §2).

### Schema

| Field | Type | Required | Notes |
|---|---|---|---|
| `id` | int64, readOnly | — | |
| `encounter` | uuid | ✅ | The meeting. (Not required when nested inside an Encounter POST.) |
| `participant` | int FK → `participant.id` | ✅ | Who. |
| `role` | int FK → `role.id` | ✅ | What role they have in *this* meeting. |
| `participant_aliases` | array of strings, **readOnly** | ✅ (read) | The generated dial aliases. **You cannot set these in a request body** — the Scheduler generates them from active AliasTemplates. |
| `short_alias` | string, 4–20 chars | — | Override for the short alias (the "human" part). |
| `long_alias` | uuid string | — | Override for the long alias (the "machine" part). |
| `auto_dial` | bool, default `false` | — | When true, the Scheduler tells Infinity to dial **out** to this participant's `dialout_alias` at meeting start (instead of waiting for them to dial in). |
| `language` | int FK → `language.id`, nullable | — | **For interpreters only** — the language *this interpreter handles*. |
| `paired_participant` | int FK → another participant, nullable | — | **For interpreters only** — the participant whose channel they interpret on. |

### The interpreter pattern

For interpreted meetings, the wiring is:

1. Create a `Role` for the interpreter (`host: false`, `interpreter: true`).
2. Create `Language` rows for each spoken/sign language (e.g.
   `Norwegian` kind=SPOKEN, `English` kind=SPOKEN, `NSL` kind=SIGN).
3. Set `encounter.main_language` to the primary language.
4. On each EncounterParticipant that's an interpreter:
   - `role` = interpreter role
   - `language` = the language they speak/sign **into**
   - `paired_participant` = the (usually non-host) participant whose
     audio they're translating (often left null on a many-to-many
     interpretation set-up)

Infinity then surfaces interpretation channels in the client — each
listener picks the language they want to hear. See
[breakouts-and-interpreters.md](breakouts-and-interpreters.md) §3 for
the full mechanics.

### Auto-dial behaviour

Setting `auto_dial: true` on an EncounterParticipant means **the
Scheduler tells Infinity to dial out to the participant's
`dialout_alias` at meeting start**. Use this for video endpoints that
should join automatically — e.g. a room system in a boardroom that you
want auto-connected without anyone pressing a button.

Requirements:

- The Participant must have `dialout_alias` set.
- `dialout_alias_protocol` (`SIP`/`H323`/`WEB`) must be set.
- Infinity must be configured with appropriate **outbound** routing for
  that protocol/destination.

If `dialout_alias` is empty, `auto_dial: true` is a no-op (Infinity has
nothing to dial).

---

## 4. AliasTemplate

This is what wires it all together. An AliasTemplate is a **Jinja2
string** that the Scheduler evaluates **once per EncounterParticipant
per enabled protocol** to generate that participant's dial aliases.

Endpoints under `/api/alias_template/` — full CRUD. Supports filters
`template`, `template__contains`, `alias_protocols`.

### Schema

| Field | Type | Required | Notes |
|---|---|---|---|
| `id` | int64, readOnly | — | |
| `template` | string ≤250 | ✅ | Jinja2 template string |
| `alias_protocols` | array of enum `SIP`/`H323`/`WEB` | — | Which protocols this template emits aliases for. Default: all three. |

### Template variables in scope

The exact variables vary across versions — the OpenAPI spec doesn't
enumerate them. Based on the default Email template (which shares the
same evaluation context) and standard Scheduling Core conventions, the
following are typically available:

| Variable | Type | Description |
|---|---|---|
| `participant.long_alias` | string (UUID) | The participant's long-form alias for this encounter — globally unique, hard to guess |
| `participant.short_alias` | string | The participant's short-form alias — friendlier, but only locally unique |
| `participant.display_name` | string | (use cautiously — may contain spaces and unicode) |
| `participant.email` | string | The participant's email address |
| `encounter.vmr` | string | The encounter's conference name prefix |
| `encounter.name` | string | The encounter's display name |
| `protocol` | string `SIP`/`H323`/`WEB` | The protocol being generated for this pass |

⚠️ **Verify against your version.** The exact identifier names
(`participant.long_alias` vs `long_alias` vs `p.long_alias`) have varied
across Scheduling Core releases. Check the Pexip "Pexip Scheduling Core
dev tutorial" PDF for the version you're targeting, or test against
a sandbox before deploying templates to production.

### Common template patterns

```
# 1. Per-participant unique alias (recommended default)
meet.{{ participant.long_alias }}@scheduler.example.com

# 2. Human-friendly alias keyed off the short alias
{{ encounter.vmr }}.{{ participant.short_alias }}@scheduler.example.com

# 3. Numeric-only alias for phone gateways
{{ participant.short_alias }}@gateway.example.com

# 4. Protocol-conditional template
{% if protocol == 'WEB' %}https://join.example.com/{{ participant.long_alias }}{% else %}{{ participant.long_alias }}@scheduler.example.com{% endif %}
```

### Multiple templates

The Scheduler runs **every** active AliasTemplate against every
EncounterParticipant. So:

- Define **one template per alias style** you want to publish.
- Each template should typically target a single protocol (or a
  protocol-conditional template like #4 above).
- The `participant_aliases` array on EncounterParticipant ends up
  containing the union of every template's output for the protocols
  it covers.

You generally don't want overlapping templates that produce duplicate
or near-duplicate aliases — pick one strategy and stick with it.

### Length and uniqueness

- `participant_aliases` strings inherit from `template` (≤250 chars).
- Templates that produce short, predictable aliases (e.g. just
  `{{ participant.short_alias }}`) are easier to dial but easier to
  enumerate.
- Templates that use `long_alias` are UUID-based: not enumerable, but
  ugly to dictate over a phone. The default email template uses both
  — `long_alias` for WEB join links (so the URL is unguessable), and
  the human-readable form for SIP/H323.

---

## 5. Putting it together — a sequence diagram in prose

```
Setup (one-time, tenant-wide):
  → POST /api/role/                  (e.g. Chair, Guest, Eng Breakout, Sales Breakout, Interp NO→EN)
  → POST /api/alias_template/        (meet.{{ p.long_alias }}@example.com, SIP+H323+WEB)
  → POST /api/language/              (Norwegian, English, NSL)
  → POST /api/participant/           (one per known user/endpoint)

For each meeting:
  → POST /api/encounter/             with nested encounter_participants + breakout_rooms
                                     ↓
                                     Scheduler iterates every alias_template × participant × enabled protocol
                                     to populate participant_aliases on each EncounterParticipant.
                                     Scheduler creates the VMR + aliases on Infinity.
                                     Scheduler returns the fully-populated Encounter.

  → POST /api/command/send_email     (loop over participants)
                                     ↓
                                     Scheduler runs the EmailTemplate Jinja2 against each
                                     participant's data and POSTs to its SMTP server.

For updates:
  → PATCH /api/encounter/{id}/       with mail_sequence: prev + 1
  → POST  /api/command/send_email    (loop)

For cancellation:
  → POST   /api/command/send_email   with cancel: true (loop)  ← do this FIRST
  → DELETE /api/encounter/{id}/
```

---

## 6. Cross-references

- The Encounter object itself, recurrence, mail_sequence → [encounters.md](encounters.md)
- BreakoutRoom semantics, `breakout_rooms_mode`, interpreter pairing in practice → [breakouts-and-interpreters.md](breakouts-and-interpreters.md)
- IdentityProvider, IDP auth flow, OAuth2 client → [auth-and-identity.md](auth-and-identity.md)
- Email template Jinja2 context (same evaluation engine as alias templates) → [email-and-branding.md](email-and-branding.md)
