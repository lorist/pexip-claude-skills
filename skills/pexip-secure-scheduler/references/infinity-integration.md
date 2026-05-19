# How the Secure Scheduler integrates with Pexip Infinity

The Scheduler is a **front-end** to a Pexip Infinity deployment.
It does not host meetings itself — Infinity does. The Scheduler's
job is to:

1. **Provision** Virtual Meeting Rooms (VMRs) and their aliases on
   Infinity when an Encounter is created.
2. **Update** those VMRs when the Encounter changes.
3. **Tear them down** when the Encounter is deleted or has ended.
4. **Reference** Infinity-side resources (IVR themes, layouts,
   languages, IdPs) by name so that the experience matches what
   the deployment owner has configured.

The wire between Scheduler → Infinity is the **Pexip Infinity
Management Node REST API** (`/api/admin/configuration/v1/`).
You don't drive it; the Scheduler does. But understanding the
mapping helps you reason about what's happening when a meeting
doesn't behave as expected.

> For the Infinity Management API itself, see the sister skill
> `pexip-management-api`.

---

## 1. Resource mapping

| Scheduler resource | Infinity resource (Mgmt API) | Lifecycle |
|---|---|---|
| `Encounter` | `conference` (VMR) at `/api/admin/configuration/v1/conference/` | Created on Encounter POST, updated on PATCH/PUT, deleted on Encounter DELETE |
| `encounter.vmr` | `conference.name` | Direct mapping. The "Conference Name Prefix" terminology comes from Infinity. |
| `encounter.theme` | `conference.ivr_theme` | The Scheduler `theme.name` must match `ivr_theme.name` on Infinity verbatim |
| `encounter.breakout_room_theme` | `conference.ivr_theme` on the breakout sub-conferences | Same matching rule |
| `encounter.pinning_config` | `conference.pinning_config` | Must be one of the names declared on the matched IVR theme |
| `encounter.view` (FK to View) | `conference.view` | The Scheduler `view.layout_name` is the value sent to Infinity |
| `encounter.main_language` | (interpretation config on the conference) | Infinity must have the matching interpreter language configured |
| `encounter.rtmp_streams` | One or more `conference_alias` rows with RTMP destinations / outbound calls | Up to 5 |
| `encounter.encounter_aliases` (readOnly) | `conference_alias` rows on the VMR | Generated from active `AliasTemplate`s |
| `encounter_participant.short_alias` / `long_alias` | `conference_alias` rows scoped to a participant | Generated from AliasTemplates with overrides |
| `breakout_room` | Sub-conference under the main VMR | Tied to a `role` for auto-routing |
| `breakout_room.locked` | The waiting-room flag on the sub-conference | |
| `participant.authentication_method = "IDP"` + `identity_provider` + `identity_provider_value` | `conference_alias` constraints + Infinity IdP config | Infinity's existing `identity_provider` configuration is the source; Scheduler references it by `group_name` |
| `participant.pin` | `conference_alias.pin` (per-participant alias) | Set when Scheduler creates the alias |
| `passthrough_alias` | (none — explicit Scheduler non-claim) | The alias is NOT created on Infinity by the Scheduler |
| `theme` (Scheduler) | `ivr_theme` (Infinity) | Reference-by-name only; theme assets live on Infinity |
| `view` (Scheduler) | (Infinity built-in layout) | Reference-by-name; layouts are part of Infinity |
| `language` (Scheduler) | Interpretation config on Infinity | Reference-by-name |

---

## 2. The provisioning flow in detail

When you POST `/api/encounter/`, the Scheduler:

1. Validates the Encounter request server-side (field types, FKs, etc.).
2. Generates the `encounter_aliases` set by running every active
   `AliasTemplate` against the encounter and (for participant-scoped
   aliases) each `EncounterParticipant`.
3. POSTs to Infinity's Management API:
   - `POST /api/admin/configuration/v1/conference/` to create the
     main VMR with `name = encounter.vmr`, the chosen theme/view,
     the participant limit, and so on.
   - `POST /api/admin/configuration/v1/conference_alias/` once per
     alias in `encounter_aliases` (and per participant alias).
   - If breakouts: `POST` additional `conference` rows for the
     sub-conferences, each linked to the parent via Infinity's
     breakout-room mechanism.
   - If RTMP streams: configure the dial-out destinations on the
     conference.
4. Returns the populated Encounter to you, with the generated
   `participant_aliases`, `encounter_aliases`, `breakout_id`s, etc.

A PATCH propagates as a corresponding PATCH on the Infinity side.
A DELETE on the Encounter triggers DELETEs on all the Infinity
resources the Scheduler created for it.

> **Failure modes:** if the Scheduler can't reach Infinity, your
> POST/PATCH/DELETE will fail with a 500 (or similar). Inspect the
> Scheduler's logs (not exposed via the Portal API) for the Infinity
> Management API error. Common causes: Infinity admin credentials in
> the Scheduler config are wrong; Infinity's Management Node is
> firewalled; a referenced theme name doesn't exist on Infinity.

---

## 3. Reference-by-name resources — the matching rule

For four resources the Scheduler only stores a **name** that must
match exactly what Infinity has configured:

| Scheduler | Infinity | What to match |
|---|---|---|
| `theme.name` | IVR theme `name` (Conferencing > IVR themes) | string-equal, case-sensitive |
| `view.layout_name` | Built-in layout id | one of Infinity's known layout strings (e.g. `1:7`, `1:21`) |
| `language.name` | Interpreter language name | string-equal |
| `identity_provider.group_name` | Identity provider `name` (Platform > Identity providers) | string-equal |

If a name doesn't match, the behaviour varies:

- **Theme:** the meeting silently uses Infinity's **default** theme.
  You can confirm by joining the meeting yourself and observing the
  branding.
- **View / layout:** Infinity falls back to its default layout (often
  `1:7`).
- **Language:** the interpreter channel doesn't wire up; participants
  selecting that language hear floor audio.
- **Identity provider:** participants with that IdP can't authenticate;
  they get an IdP-not-found error from Infinity.

**Mitigation:** when configuring the Scheduler, pull the relevant
names from Infinity first (via the Management API or the admin UI)
and paste them in verbatim. Don't retype.

---

## 4. PassthroughAlias — explicit "this isn't ours"

By default, the Scheduler assumes it **owns** every alias dialed at
the Infinity deployment in front of it. Calls to unknown aliases get
the treatment configured by `global_settings.default_response_type`:

- `"REJECT"` → call dropped
- `"CONTINUE"` → handed to Infinity for resolution against its own
  alias config

`PassthroughAlias` rows are an **explicit allow-list** that pairs
with `CONTINUE` to selectively whitelist aliases the Scheduler should
ignore. Common uses:

- A permanent VMR for the executive team that's been on Infinity for
  years before the Scheduler was deployed.
- A SIP test endpoint (`test_call@example.com`).
- A gateway prefix range routed by Infinity to a partner system.

If you have a single, narrow set of unmanaged aliases, prefer
`default_response_type: REJECT` + explicit passthroughs over
`CONTINUE` everywhere (less surface area for accidental shadowing).

---

## 5. Multi-Infinity scenarios

The Scheduler is single-tenant at the API level — one Scheduler
serves one Infinity. For multi-Infinity deployments you have a few
options, none expressed in the OpenAPI spec:

- **Multiple Schedulers, one per Infinity.** Each has its own
  Portal API endpoint; your integration code multiplexes.
- **One Infinity with location-based routing.** Infinity itself
  routes calls across multiple Conferencing Node clusters — the
  Scheduler is unaware. The Encounter `vmr` becomes a single name
  globally; Infinity handles geo-routing.
- **Federation via SIP/H323.** The Scheduler provisions a VMR on
  its "home" Infinity; the other Infinity sees it as a federated
  alias. Out of scope here.

For very large customers, ask Pexip about the right shape — there's
no Portal API contract that helps you here.

---

## 6. Theme / view / language sync helper pattern

A common operational helper for field engineers is a small script that:

1. Reads the IVR themes / layouts / interpreter languages from Infinity
   via the Management API (`pexip-management-api` skill territory).
2. Diffs against the Scheduler's `/api/theme/`, `/api/view/`,
   `/api/language/`.
3. POSTs missing rows and PATCHes drifted rows.

This keeps the Scheduler in sync with Infinity-side renames. It's
worth running on a cron or before every major schedule push.

The Scheduler does **not** auto-discover Infinity's theme list —
you have to mirror it explicitly.

---

## 7. License counting

Every participant who joins a Scheduler-provisioned meeting consumes
a Pexip Infinity license, the same as any other Infinity call. The
Scheduler does not have its own license model; it just makes Infinity
do work.

`participant_limit` on an Encounter caps the **count**, but the cost
hits Infinity's port licenses, not anything Scheduler-side. If you
schedule a 200-participant town hall, make sure Infinity has 200
ports of headroom.

---

## 8. Cross-references

- The Encounter fields that propagate to Infinity → [encounters.md](encounters.md) §1
- The Scheduler's IdentityProvider rows and how they bind to Infinity's IdP config → [auth-and-identity.md](auth-and-identity.md) §3
- Theme, View, Language, RTMPStream schemas → [email-and-branding.md](email-and-branding.md)
- For the Infinity Management API itself → the sister skill `pexip-management-api`
