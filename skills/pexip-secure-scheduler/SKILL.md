---
name: pexip-secure-scheduler
description: >
  Expert knowledge for designing, building, and integrating against the
  **Pexip Secure Scheduler** Portal API (formerly the Pexip Web Scheduler) —
  the HTTP REST API used to schedule, update, cancel, and invite participants
  to Pexip Infinity meetings. Use this skill whenever the user is working with
  `/api/encounter/`, `/api/participant/`, `/api/role/`, `/api/alias_template/`,
  `/api/breakout_room/`, the `/api/command/` actions (`send_email`,
  `generate_email`, `long_lived_token`), or any other Portal API endpoint;
  authenticating to the Scheduler with basic auth or a long-lived token;
  modelling the encounter / participant / role / alias-template object graph;
  wiring Scheduler resources to a Pexip Infinity deployment (themes, views,
  passthrough aliases, VMRs); integrating with calendar systems (iCalendar
  SEQUENCE, recurrence); or driving the Scheduler from a custom portal,
  Outlook/Google plug-in, or SCIM provisioner. Also triggers for questions
  about the Portal API object model (encounter vs. encounter-participant vs.
  participant), breakout-by-role semantics, interpreter pairing, the Jinja2
  email template variables, IdP/SSO-driven participant authentication, OAuth2
  feature groups, or "what's the right order to create things in." Use this
  skill — the Portal API has subtle DRF semantics (PUT vs PATCH, paginated
  lists, singletons, nested-on-create), opaque fields (recurrence, alias
  template syntax), and several integration points with Infinity that the
  OpenAPI spec leaves implicit.
---

# Pexip Secure Scheduler (Portal API) — Expert Skill

Practical knowledge for building and integrating applications against the
**Pexip Secure Scheduler** — the standalone web service that schedules,
provisions, and invites participants to meetings on Pexip Infinity.

The product has had a few names over its life:

| Name | What it refers to |
|---|---|
| **Pexip Secure Scheduler** | The current product name (5.x) |
| **Pexip Web Scheduler** | The earlier product name (4.x and prior) |
| **Portal API** | The internal name used by the OpenAPI spec (`title: Portal API`) |
| **Pexip Scheduling Core** | The underlying engine (you'll see this in dev tutorials) |

They all refer to the same thing. The skill assumes Portal API **v5.x** (the
OpenAPI document this is distilled from is v5.1.0). Where v4.x differs, it's
called out.

> **What this is NOT:** the Secure Scheduler is **not** the Pexip Infinity
> Management Node API (`/api/admin/{configuration,status,…}/v1/` — see
> `pexip-management-api` for that), and it is **not** the in-meeting Client
> API (`/api/client/v2/conferences/…` — see `pexip-client-api`). It sits
> *alongside* Infinity and orchestrates meeting provisioning **on** Infinity
> using its own back-channel — your integration talks to the Scheduler,
> the Scheduler talks to Infinity.

> **Sourcing:** every field name, enum value, and endpoint in this skill is
> taken directly from the v5.1.0 OpenAPI document (`secure_scheduler_schema.yaml`).
> The default email body template quoted in [references/email-and-branding.md](references/email-and-branding.md)
> is the literal default shipped in the spec. A few items are marked
> ⚠️ **verify-against-your-version** — these are observable behaviours the
> spec doesn't pin down (recurrence string format, token return mechanism,
> exact Infinity provisioning back-channel).

---

## Quick Decision Tree

| Goal | Read this first |
|---|---|
| Understand the object model (encounter / participant / role / alias) | §1 below |
| Authenticate to the API | §2 below + [auth-and-identity.md](references/auth-and-identity.md) |
| Schedule a new meeting end-to-end | §3 below + [encounters.md](references/encounters.md) |
| Update or cancel an existing meeting | [encounters.md](references/encounters.md) §4 |
| Recurring meetings, iCalendar SEQUENCE | [encounters.md](references/encounters.md) §5 |
| Set up breakout rooms by role | [breakouts-and-interpreters.md](references/breakouts-and-interpreters.md) |
| Add an interpreter / sign-language channel | [breakouts-and-interpreters.md](references/breakouts-and-interpreters.md) §3 |
| Customise the invite email | [email-and-branding.md](references/email-and-branding.md) |
| Drive sign-on with an Infinity IdP | [auth-and-identity.md](references/auth-and-identity.md) §3 |
| Wire to a running Pexip Infinity | [infinity-integration.md](references/infinity-integration.md) |
| Provision users from SCIM / OAuth2 | [auth-and-identity.md](references/auth-and-identity.md) §4–5 |
| Debug a 400 / weird PUT behaviour | [gotchas-and-conventions.md](references/gotchas-and-conventions.md) |
| Per-endpoint field reference | the topic-specific reference file |

---

## 1. The Object Model

The Scheduler is built around five core types. Internalise these and the rest
of the API falls out naturally.

```
Encounter ─────────────────────────────┐
  │   (the meeting: date, time, vmr,    │ has many
  │    timezone, recurrence, themes...) │
  │                                     │
  │ has many                            │
  ▼                                     ▼
EncounterParticipant ──► Participant   BreakoutRoom
  (link row: which          (re-usable     (child of encounter,
   participant has           profile:       attached to a Role —
   which role in this        display name,  all participants with
   meeting; carries          email, PIN,    that role land here)
   their generated           dialout addr,         │
   aliases + interpreter     auth method)          │ refers to
   pairing)                                        ▼
   │                                              Role
   │ refers to                                    (name, host?, interpreter?)
   ▼                ────────────────────────────────▲
  Role                                              │
                                              ◄─────┘
                                              (same Role is shared by
                                               many EncounterParticipants)
```

The relationships in prose:

- An **Encounter** is one meeting (possibly recurring). It has a
  `start_date`, optional `start_time`/`end_time`, a `timezone`, and a `vmr`
  — the **Conference Name Prefix** that becomes the actual Pexip Infinity
  VMR name when the meeting is provisioned. The encounter id is a UUID.

- A **Participant** is a **re-usable profile** — a person (or system endpoint)
  who can be invited to many meetings. Fields: `display_name`, `email`,
  `dialout_alias`, `dialout_alias_protocol` (`SIP|H323|WEB`),
  `authentication_method` (`PIN|IDP|""`), `pin`, `identity_provider`,
  `identity_provider_value`. Integer id.

- A **Role** is a *label* applied to a participant **in a meeting**. Fields:
  `name`, `host` (boolean — host joins the main room, non-host lands in a
  breakout if one is attached to the role), `interpreter` (boolean), and
  `description`. Roles are **re-usable** across encounters — define a Chair
  role once, attach it to whoever needs it.

- An **EncounterParticipant** is the **link row**. It carries the foreign
  keys (`encounter`, `participant`, `role`), the *generated* dial aliases for
  this participant in this meeting (`participant_aliases`, read-only),
  optional `short_alias` / `long_alias` overrides, the `auto_dial` flag,
  and (for interpreters) `language` + `paired_participant`.

- A **BreakoutRoom** is a child of an Encounter, with a `name`, a `role`
  foreign key, and a `locked` flag. **Any participant with that role joins
  this breakout** rather than the main room. There's also an automatically
  created `adhoc_guest_breakout_id` on every Encounter for ad-hoc dial-ins.

And one supporting type:

- An **AliasTemplate** is a tenant-wide Jinja2 template that generates the
  dial aliases for newly created EncounterParticipants, per protocol
  (`SIP`, `H323`, `WEB`). Each template emits one alias string per
  participant per enabled protocol. See
  [participants-roles-aliases.md](references/participants-roles-aliases.md) §4
  for the template variables actually in scope.

**Mental model check:** Roles and Participants are **library** objects.
Encounters and EncounterParticipants are **instance** objects (one per
meeting). Don't try to model "John Doe is a chair in the Monday team
meeting" with a fresh Role each time — make `Chair` a single Role and link
John to it via an EncounterParticipant for the Monday encounter.

---

## 2. Authentication

The Portal API accepts **two** auth schemes on every business endpoint:

| Scheme | OpenAPI name | Header | When to use |
|---|---|---|---|
| HTTP Basic | `basicAuth` | `Authorization: Basic <base64(user:pass)>` | Bootstrap, one-off scripts, the `long_lived_token` endpoints themselves |
| Bearer token | `tokenAuth` | `Authorization: Bearer <token>` | Everything else, especially long-running integrations and SCIM provisioners |

The bearer token is a **long-lived token** issued by the `command` endpoints:

```
GET  /api/command/long_lived_token/          # auth: basicAuth ONLY
POST /api/command/long_lived_token/          # auth: basicAuth ONLY
POST /api/command/long_lived_token/revoke/   # auth: basicAuth ONLY
```

The endpoint description in the spec is *"View to create a long-lived
token for the scim client."* Both `GET` and `POST` return `200` with the
description **"No response body"** — meaning **the OpenAPI document does
not declare where the token surfaces**. In practice it is returned in a
response header or `Set-Cookie`. ⚠️ **Verify against your version** — check
`curl -i` output the first time and pin the contract in your code, because
the spec is silent on this.

```bash
# Provision a token
curl -i -u admin:hunter2 \
  -X POST https://scheduler.example.com/api/command/long_lived_token/

# Then use it
curl -H "Authorization: Bearer $TOKEN" \
  https://scheduler.example.com/api/encounter/
```

**Gotchas worth pre-loading:**

- The token endpoints accept **basicAuth only**, not tokenAuth. You can't
  rotate a token using another token; you bounce through basic credentials.
- All other endpoints accept either scheme — don't send both in the same
  request.
- The Scheduler can be configured for **OIDC** at the application level
  (`/api/authentication_mode/` — singleton at id 1, `mode: local|oidc`).
  That governs how *human users* log in to the Scheduler UI. It does NOT
  change how your **API integration** authenticates — that's still
  basicAuth + long-lived token.

See [auth-and-identity.md](references/auth-and-identity.md) for the full
auth+identity surface: OAuth2 clients, FeatureGroups (permission bundles),
and how IdentityProvider rows let participants sign in via Infinity SSO.

---

## 3. The Four-Step Recipe: Schedule a Meeting from Scratch

The `info.description` block of the OpenAPI spec lays out the canonical
creation flow:

> Creating an initial encounter involves several steps:
> 1. Create **Roles**
> 2. Create **Alias Templates**
> 3. Create **Participants**
> 4. Create the **Encounter** and associate participants with it.

Steps 1–3 are **library setup** — do them once per tenant, not once per
meeting. Step 4 is where every scheduled meeting starts.

### Step 1 — Create the Roles (one-time)

```bash
# A host role
curl -X POST https://scheduler.example.com/api/role/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{ "name": "Chair", "host": true, "description": "Meeting chair" }'
# → 201, returns { "id": 1, ... }

# A guest role
curl -X POST https://scheduler.example.com/api/role/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{ "name": "Guest", "host": false }'
# → 201, returns { "id": 2, ... }
```

Required: `name`, `host`. The `host: true` participants go to the main
room; `host: false` go to a breakout if the role has one, otherwise also
to the main room (no breakout = no segregation).

### Step 2 — Create at least one Alias Template (one-time)

```bash
curl -X POST https://scheduler.example.com/api/alias_template/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "template": "meet.{{ participant.long_alias }}@scheduler.example.com",
    "alias_protocols": ["SIP", "H323", "WEB"]
  }'
```

The `template` is a Jinja2 string with the participant in scope. The
exact variables in scope are documented in
[participants-roles-aliases.md](references/participants-roles-aliases.md) §4.
Define **one or more** templates — every active template will emit aliases
on every EncounterParticipant.

### Step 3 — Create Participants (per person, but re-used across meetings)

```bash
# A PIN-authenticated participant
curl -X POST https://scheduler.example.com/api/participant/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "display_name": "Alice Example",
    "email": "alice@example.com",
    "authentication_method": "PIN",
    "pin": "12345678",
    "dialout_alias": "alice@example.com",
    "dialout_alias_protocol": "SIP"
  }'
# → 201, returns { "id": 42, ... }
```

Required: `display_name`, `authentication_method`. The PIN regex is
`^((\d{3,19}#)|(\d{4,20}))?$` — i.e. 4–20 digits, **or** 3–19 digits
followed by `#`. Pre-validate on the client; a malformed PIN gets a 400.

### Step 4 — Create the Encounter (the only per-meeting object)

You have two choices: create the Encounter empty and add EncounterParticipants
in a second call, **or** nest them inline. The nested form is supported by
the schema (`NestedEncounterParticipantRequest`) and is preferable for new
meetings.

```bash
curl -X POST https://scheduler.example.com/api/encounter/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Monday Sync",
    "vmr": "monday-sync",
    "start_date": "2026-06-01",
    "start_time": "10:00:00",
    "end_time": "10:30:00",
    "timezone": "Europe/Oslo",
    "description": "Weekly team sync",
    "enable_chat": true,
    "guests_can_present": false,
    "encounter_participants": [
      { "participant": 42, "role": 1 },
      { "participant": 43, "role": 2, "auto_dial": true }
    ]
  }'
# → 201, returns the full Encounter with id (UUID),
#   adhoc_guest_breakout_id, generated encounter_aliases,
#   and the EncounterParticipants populated with their participant_aliases.
```

That's the full create. The Scheduler now owns this meeting and will
provision the VMR on Infinity, generate aliases from your alias templates,
and (when you ask it to) send invites.

A complete worked example with a recurring meeting + breakouts +
interpreter is in [encounters.md](references/encounters.md) §6.

---

## 4. Top Gotchas (the short list)

Quick hits — the full list with mitigations lives in
[gotchas-and-conventions.md](references/gotchas-and-conventions.md).

1. **PUT replaces, PATCH merges.** PUT on `/api/encounter/{id}/` requires
   *every required field* in the body. Missing fields → 400 or silent
   field reset. **Default to PATCH** for partial updates.
2. **`timezone` is a fixed enum** of 400+ IANA names — `"UTC"`, `"Europe/Oslo"`,
   etc. `"EST"`, `"UTC+1"`, or arbitrary offsets are rejected.
3. **`recurrence` is an opaque string** — the spec declares it as
   `type: string, nullable: true` with no format. ⚠️ Treat as iCalendar
   `RRULE` (e.g. `FREQ=WEEKLY;BYDAY=MO`); verify your version accepts the
   format before relying on it.
4. **`start_date` is a date, not a datetime.** Splitting time into
   `start_time`/`end_time` plus `timezone` is mandatory; sending an ISO 8601
   datetime in `start_date` is a 400.
5. **`mail_sequence` is the iCalendar SEQUENCE counter.** Bump it before
   sending an update invite or calendar clients will silently drop the
   change. (Default `0` works for the first invite.)
6. **`participant_aliases` is read-only.** Use `short_alias` /
   `long_alias` on the EncounterParticipant to override; submitting
   `participant_aliases` in the request body is silently ignored.
7. **Lists paginate with `limit` + `offset`.** Response shape is
   `{ count, next, previous, results }`. There is **no bulk DELETE** — to
   wipe N encounters, iterate.
8. **Singletons exist.** `/api/smtp_server/`, `/api/authentication_mode/`,
   `/api/global_settings/`, and the email template-style resources have no
   POST/DELETE. Read with GET, mutate with PATCH on id `1`.
9. **All write endpoints accept `json`, `x-www-form-urlencoded`, and
   `multipart/form-data`.** Stick to `application/json`; the others are
   declared but rarely tested.
10. **Roles are global, not per-tenant.** If you have a multi-customer
    deployment, namespace role names yourself (e.g. `acme-chair`,
    `globex-chair`); the API gives you no isolation.

---

## 5. How the Scheduler Talks to Infinity

This is the bit the OpenAPI spec is silent on, and the bit field engineers
trip over most. The short version:

| Scheduler resource | What Infinity sees |
|---|---|
| `encounter.vmr` | becomes the **Conference Name prefix** of a Pexip Infinity Virtual Meeting Room |
| `encounter_aliases` (read-only on the encounter) | becomes the set of **Aliases** on that VMR — generated from your active `AliasTemplate`s |
| `encounter_participant.short_alias` / `long_alias` | overrides for the alias the participant dials |
| `breakout_room` rows | become **breakout sub-conferences** under the VMR — Infinity routes participants between them based on the role they joined as |
| `theme.name` | must **match the IVR Theme name in Infinity** verbatim — the Scheduler does *not* upload the theme, it only references it by name |
| `view.layout_name` | likewise references an Infinity **layout** by name |
| `language` (for interpreters) | must match Infinity's interpreter language config |
| `passthrough_alias` | aliases the Scheduler should **not** claim — handed straight through to Infinity's existing config |

The Scheduler uses the **Infinity Management API** (`/api/admin/configuration/v1/conference/`)
under the hood to create/update/delete VMRs and aliases. You don't drive
that yourself; you drive the Scheduler. But it does mean: **the Scheduler
must hold admin credentials for the Infinity it sits in front of**, and
the Infinity URL + creds are part of the Scheduler's deployment config
(not exposed in the Portal API).

See [infinity-integration.md](references/infinity-integration.md) for the
full mapping plus the operational considerations (theme propagation,
license counting, passthrough behaviour, what to do if the Scheduler and
Infinity drift).

---

## 6. What's in this skill

### Reference files

| File | Covers |
|---|---|
| [encounters.md](references/encounters.md) | The Encounter schema field-by-field; create / update / cancel; recurrence; iCalendar SEQUENCE; encounter templates; the full worked example. |
| [participants-roles-aliases.md](references/participants-roles-aliases.md) | Participant, Role, EncounterParticipant, AliasTemplate — the people side. PIN regex, dialout protocols, alias template syntax + variables in scope, alias overrides. |
| [breakouts-and-interpreters.md](references/breakouts-and-interpreters.md) | BreakoutRoom (`OFF`/`MANUAL`/`AUTOMATIC`), role-driven routing, `adhoc_guest_breakout_id`, interpreter setup (`language` + `paired_participant`), sign-language. |
| [auth-and-identity.md](references/auth-and-identity.md) | basicAuth, long-lived tokens, OAuth2 clients, FeatureGroups, AuthenticationMode (local/OIDC), IdentityProvider rows, the participant `IDP` vs `PIN` auth flow. |
| [email-and-branding.md](references/email-and-branding.md) | EmailTemplate (with the default body + every Jinja2 variable in scope), `command/generate_email`, `command/send_email`, SMTPServer, Theme, View, Language, RTMPStream, i18n. |
| [infinity-integration.md](references/infinity-integration.md) | How Scheduler resources map onto Pexip Infinity; theme/view name matching; passthrough aliases; encounter→VMR mechanics; multi-Infinity scenarios. |
| [gotchas-and-conventions.md](references/gotchas-and-conventions.md) | DRF conventions (pagination, PUT vs PATCH, filters, content types), singletons, opaque fields (recurrence, alias template body), date/time/timezone splits, and 20+ field-tested footguns. |
| [openapi-spec.yaml](references/openapi-spec.yaml) | The raw v5.1.0 OpenAPI document — the authoritative source for every field name, enum value, and endpoint. Consult this when the distilled markdown leaves a question open (e.g. obscure schemas like `NestedEncounterTemplateParticipant`). |

### Scripts

| File | Purpose |
|---|---|
| [scripts/scheduler_client.py](scripts/scheduler_client.py) | A stdlib-only Python client. Demonstrates the long-lived-token bootstrap probe (which response header carries the token on **your** version), the full four-step recipe (`demo` subcommand), and primitive `list` / `get` / `delete` CRUD. Read it as a worked example, or run it against a sandbox to verify behaviour. |
