---
name: pexip-policy-server
description: >
  Production patterns for building and operating Pexip Infinity External
  Policy servers with participant classification, access control, and
  conference lifecycle management. Covers service_configuration response
  validation (PIN rules, view normalization, breakout room stripping,
  ADP entries), participant_properties with classification levels and
  role ladders (chair/guest/bypass_lock), avatar_request responses (JPEG
  format, Keycloak integration), conference classification via Client API
  (token lifecycle, cross-worker dedup, recalculation), event sink
  integration (admission detection, breakout migration, debounce), and
  40 production-tested gotchas. Use when: building an external policy
  server, implementing participant classification, handling
  service_configuration or participant_properties responses, serving
  avatar images, managing conference classification state, integrating
  event sinks with a policy server, debugging policy rejections or
  "Not authenticated" errors, working with PIN validation rules, or
  asking about breakout room policy handling. Also triggers for
  "policy server PIN", "classification level", "bypass_lock",
  "allow_guests", "L1 rejection", "preauthenticated_role",
  "non_idp_participants", "service_tag", "_normalize_alias",
  "avatar_request JPEG", and "cross-worker classification dedup".
---

# Pexip Policy Server — Production Patterns

## Overview

Practical knowledge for building production-grade **Pexip Infinity External Policy
servers** — the HTTP endpoints Pexip calls to decide VMR configuration, participant
roles, classification levels, and avatars. This skill goes beyond the protocol
(covered in `pexip-external-policy`) to document the implementation patterns,
validation rules, and failure modes discovered running policy servers on Pexip v39+.

> **Sourcing:** every pattern, validation rule, and gotcha below comes from a
> production policy server handling classification, breakout rooms, SIP ADP,
> IdP role ladders, and avatar serving on Pexip Infinity v39-v40b2. The PIN
> validation truth table was confirmed by Pexip support log analysis across
> 200+ test calls. For the protocol-level request/response format, see the
> sibling skill `pexip-external-policy`.

---

## Quick Decision Tree

| Goal | Read first |
|---|---|
| Validate service_configuration response fields | SS1 + `references/service-config-validation.md` |
| Understand PIN validation rules | SS1 PIN subsection |
| Implement participant classification levels | SS2 + `references/participant-role-ladder.md` |
| Serve participant avatars | SS3 + `references/avatar-requirements.md` |
| Build conference classification state | SS4 + `references/classification-lifecycle.md` |
| Integrate event sink with policy server | SS5 + `references/event-sink-patterns.md` |
| Debug policy rejection / "Not authenticated" | SS6 (gotchas) |
| See a working classification server | `examples/classification-policy-server/` |
| See a working avatar server | `examples/avatar-policy-server/` |

---

## SS1: Service Configuration Patterns

Pexip calls `/policy/v1/service/configuration` when it encounters an unknown alias.
Your response creates a virtual VMR on the fly. Getting this right means navigating
alias normalization, PIN validation, view values, and breakout room edge cases.

### Alias Normalization

SIP calls arrive with `local_alias` as `sip:meeting@conf.example.com`. Always
strip the `sip:` prefix and `@domain` suffix before matching. Apply to every
request — the raw value breaks prefix matching and breakout detection.

### Required Response Fields

Every `service_configuration` response must include:

| Field | Purpose | Example |
|---|---|---|
| `service_type` | VMR type | `"conference"` |
| `name` | Conference display name | `"pdp002-demo001"` |
| `local_alias` | Normalized alias | `"pdp002-demo001"` |
| `service_tag` | Tag for participant_properties correlation | `"pdp-pdp002"` |
| `view` | Layout — must be one of 14 valid values | `"one_main_twentyone_pips"` |

### PIN Validation Rules

Pexip applies these rules server-side. Violating any one causes the **entire policy
response** to be rejected — Pexip returns 404 "Neither conference nor gateway found"
to the client, with no useful error in the response body.

| # | Rule | Symptom |
|---|---|---|
| 1 | `allow_guests: true` without `pin` | Silent 404 |
| 2 | `pin: ""` (empty string) | Rejection |
| 3 | `guest_pin` with `allow_guests: false` | Rejection |
| 4 | `pin` and `guest_pin` must match length, OR both end with `#` | Rejection |
| 5 | If either PIN ends with `#`, both must end with `#` | Rejection |
| 6 | `pin` and `guest_pin` cannot be identical | Rejection |
| 7 | `non_idp_participants` must be `"allow_if_trusted"` on v39+ | Rejection |
| 8 | Pexip caches failed responses for minutes | Stale 404 after fix |

The safe pattern for mismatched PIN lengths: append `#` to BOTH PINs.

```python
if pin and guest_pin and len(pin) != len(guest_pin):
    if not pin.endswith("#"):
        pin += "#"
    if not guest_pin.endswith("#"):
        guest_pin += "#"
```

### View Normalization

Pexip accepts exactly 14 `view` values. An invalid value rejects the **entire**
response. Always normalize through a validation function that maps aliases
(`"ac"` -> `"five_mains_seven_pips"`) and falls back to `"one_main_twentyone_pips"`.
See `references/service-config-validation.md` for the full valid set and alias map.

### Breakout Room Stripping

Breakout rooms have no PIN. You MUST strip `allow_guests` from the response
(`result.pop("allow_guests", None)`) and set `locked: False`. Also omit PIN,
IdP group, and ADP entries.

### ADP Entry Format

Automatic Dial-out Participants require: `remote_alias`, `local_alias` (stripped),
`local_display_name`, `protocol` ("sip"), `role` ("guest"),
`keep_conference_alive` ("keep_conference_alive_never"). Exclude when
`is_policy_server=True` and in breakout rooms. See
`references/service-config-validation.md` for the full dict example.

### Response Helpers

`_json_ok(result)` wraps in `{"status":"success","action":"continue","result":...}`.
`_json_passthrough()` returns an empty result (Pexip uses local config).

**Critical:** NEVER use `_json_ok()` for rejections. `action: "continue"` in the
envelope overrides `action: "reject"` in the result. Use bare `jsonify()` instead.

---

## SS2: Participant Properties Patterns

Pexip calls `/policy/v1/participant/properties` when each participant joins. Your
response controls role assignment, classification overlay, lobby bypass, and rejection.

### IdP Attribute Extraction

IdP attributes arrive in the POST body as `idp_attributes` dict. Values may be
list-wrapped (`{"title": ["General"]}`). Key casing varies (`firstName` vs
`firstname`). Always unwrap lists and `str().strip()` the result. Also extract
`firstName`/`lastName` for display name formatting.

### Classification Level Determination

Map the IdP `title` to a numeric level via a classification map:
`classification_map.get(title.lower().strip(), 0)`. The map format may vary
(list-of-dicts vs flat dict) -- always normalize to `{name_lower: int_level}`.

### Role Assignment Ladder

Four tiers, evaluated in order:

1. **Policy Server participant** (remote_alias is "Policy Server"): always
   `chair` + `bypass_lock: True`. Must be checked FIRST — before any IdP or
   classification logic.

2. **High-level IdP** (level >= auto_admit_min): `chair` + `bypass_lock: True`.
   These users skip the lobby entirely.

3. **IdP below threshold**: `guest`. Lands in lobby, host must admit.

4. **Non-IdP** (SIP, PSTN): passthrough `preauthenticated_role` from the request.
   NEVER hardcode `"guest"` — the PIN-based role from Pexip must be preserved.

### L1 Rejection Pattern

Use bare `jsonify()` with `action: "reject"` (NEVER `_json_ok()`). Read the
current meeting level from conference state (the STORED `classification_level`),
not `min(currently_tracked)` -- prevents race conditions between recalculations.

### Breakout Participants and Display

All breakout participants get `bypass_lock: True` regardless of level. Format
display names as `"Heidi Smith | General (L6)"`, set `overlay_text: "L{level}"`,
and `service_tag: "level-{level}"`.

---

## SS3: Avatar Responses

Pexip v40+ calls `/policy/v1/participant/avatar/<alias>` to fetch participant photos.
The response requirements are strict and poorly documented.

### Requirements

- **MUST** return JPEG (not PNG) -- Pexip silently falls back to initials
- **MUST** match exact requested `width` x `height` from query params
- **MUST** use RGB color space (not RGBA) via `img.convert("RGB")`
- Content-Type: `image/jpeg`, Cache-Control: `public, max-age=300`
- KC `avatarBase64` attribute needs `maxLength: 65536` in User Profile schema
- **404 caching:** Pexip caches 404s per session -- no retry until full disconnect+rejoin

See `references/avatar-requirements.md` for the full endpoint, user lookup chain,
and PIL processing pipeline.

---

## SS4: Classification System

Conference classification tracks the security clearance level of a live meeting
by joining a "Policy Server" participant via the Client API and setting the
classification level visible to all participants.

### Token Lifecycle

1. `request_token` -- creates a visible "Policy Server" participant. Returns a token.
2. `refresh_token` (every 60s) -- lightweight renewal, no new participant.
3. `release_token` -- disconnects the PS participant cleanly.

Each `request_token` creates a NEW participant. Always release the old token first
to avoid duplicate roster entries.

### Cross-Worker Dedup

With multiple Gunicorn workers, use SQLite `INSERT` with a `UNIQUE` constraint as
the atomic gate. Python threading locks do not work across processes. The first
worker to insert wins; others get `IntegrityError` and skip classification.

### Recalculation

When admitted participants change: collect `admitted_levels` (main_vmr only for
main conference, all for breakout), compute `min(admitted_levels)`, call
`set_classification_level()` via Client API.

### Token Keepalive

A background daemon thread refreshes all active conference tokens every 60s using
`refresh_token()`. Start it after the first successful `apply_classification()`.

See `references/classification-lifecycle.md` for complete code patterns.

---

## SS5: Event Sink Integration

The event sink receives participant lifecycle events and triggers classification
recalculation when participants move between lobby, conference, and breakout rooms.

### Admission Detection

A participant is "admitted" when ALL hold: `has_media` is true, `connect_time`
is non-null, and `service_type` is not `"waiting_room"`, `"connecting"`, or empty.

### Un-Admission

When `service_type == "waiting_room"`, reverse the participant's admission and
trigger recalculation -- they were sent back to lobby.

### Breakout Migration

Pexip fires `participant_connected` in the breakout but does NOT call
`participant_properties` again. Migrate participant state from parent conference
and track with `admitted=False` (intentional -- if True, the "already admitted?"
guard skips recalculation).

### Debounce and Reorganization

Use per-participant debounce keys (`f"{alias}:{key}"`) to prevent duplicate
recalculation. When breakout rooms are reorganized via "Edit rooms," Pexip does
NOT fire `participant_disconnected` -- prune stale entries on next join.

See `references/event-sink-patterns.md` for complete code patterns.

---

## SS6: Gotchas

40 production-tested gotchas, grouped by category. Each is expanded with symptoms,
root cause, and fix in `references/gotchas-expanded.md`.

### Service Configuration

| # | Gotcha | Symptom | Fix |
|---|---|---|---|
| 1 | `_json_ok()` wraps `action: "continue"` | Reject never works | Bare `jsonify()` for rejections |
| 2 | `allow_guests: true` without `pin` | Silent 404 | Always set `pin` or omit `allow_guests` |
| 3 | Demo aliases with `is_policy_server=True` must route through demo builder | PS join 404s | Check alias pattern before generic branch |
| 4 | Breakout service config must strip `allow_guests` | Breakout 404 | `result.pop("allow_guests", None)` |
| 5 | PIN length mismatch | Rejection | Append `#` to BOTH PINs |
| 6 | `non_idp_participants` must be `"allow_if_trusted"` | Rejection | Never use `"allow"` on v39+ |
| 7 | Pexip caches failed policy responses for minutes | Stale 404 after fix | Wait or restart conferencing node |
| 29 | `view` has 14 valid values | Entire response rejected | Always use `_normalize_view()` |
| 32 | `pin: ""` rejected but `guest_pin: ""` valid for test aliases | Inconsistent behavior | Omit empty PINs entirely |
| 33 | `guest_pin` with `allow_guests: false` | Rejection | Only set `guest_pin` when guests enabled |

### Participant / Classification

| # | Gotcha | Symptom | Fix |
|---|---|---|---|
| 8 | Each `request_token` creates a new PS participant | Duplicate roster entries | Release old token before requesting new |
| 9 | Cross-worker dedup needs SQLite INSERT OR IGNORE | Double classification | Atomic DB gate, not Python locks |
| 10 | Client API tokens expire at ~120s | Stale token 403 | Refresh at 60s proactively |
| 12 | PS participant must get chair + bypass_lock first | PS stuck in lobby | Check remote_alias before other logic |
| 13 | Non-IdP must passthrough preauthenticated_role | SIP users always guest | Never hardcode "guest" for non-IdP |
| 14 | `guest_pin` causes SIP IVR prompt | SIP users hear PIN menu | Omit `guest_pin` for SIP-only conferences |
| 15 | SIP `local_alias` arrives as `sip:name@domain` | Alias mismatch | Always normalize |
| 18 | L1 rejection uses stored classification_level | Race condition | Read from conference state, not min(tracked) |
| 22 | Client API `request_token` fails 403 on locked+IdP | Classification fails | Use policy server PIN, not IdP |
| 23 | ADP excluded when `is_policy_server=True` | SIP endpoints join PS call | Gate ADP behind `not is_policy_server` |
| 24 | Test aliases skip early classification | No classification on test VMRs | Check alias suffix before classify |
| 25 | `__create_keycloak_idp__` sentinel must be filtered | Sentinel sent as IdP group | Skip sentinel values in IdP config |
| 26 | KC user update must merge attributes, not replace | Attributes wiped | Read existing, merge, then write |
| 28 | Classification map format varies | KeyError | Normalize to `{name_lower: int}` |

### Avatar

| # | Gotcha | Symptom | Fix |
|---|---|---|---|
| 11 | Avatar MUST be JPEG, exact dimensions, RGB | Initials shown instead | PIL convert("RGB") + JPEG save |
| 27 | `enable_avatar_lookup` lives on `policy_server` resource | Avatars never requested | Enable on the policy_server config in Pexip admin |

### Event Sink

| # | Gotcha | Symptom | Fix |
|---|---|---|---|
| 16 | No `participant_disconnected` on breakout reorganization | Stale breakout state | Prune on next participant join |
| 17 | Event sink breakout migration must track `admitted=False` | Recalc never fires | Intentional False triggers admission flow |

### Operational

| # | Gotcha | Symptom | Fix |
|---|---|---|---|
| 19 | `on_completion` is JSON-encoded, not bare alias | Transfer fails | `json.loads(on_completion)` |
| 20 | SAML auth preserved across `on_completion` transfers | Unexpected re-auth | Expected behavior, no fix needed |
| 21 | Check policy server URL on Pexip before debugging | Wrong server queried | Verify URL in Pexip admin first |
| 30 | Conference state in `/tmp/conference_state.db` | Wrong DB queried | Separate from main app DB |
| 31 | Client API `send_message` must use `text/plain` | Message not delivered | Set Content-Type explicitly |
| 34 | `demo_branding.py` helpers use `*args` | kwargs silently break | Use positional args only |
| 35 | Duplicate PS cascade | Disconnecting PS creates 403→token→duplicate loop | Never disconnect PS participants; they clean up at conference end |
| 36 | New token 403 "Invalid role" | `set_classification_level` fails right after new token | Wait 1.5s for PS participant to be admitted before API calls |
| 37 | Breakout return alias contamination | Participant remote_alias becomes conference alias | Strip destination_alias when it matches conference/parent alias |
| 38 | Conference restart clears caches | Cleanup thread from old conference wipes new conference data | Use SQLite generation counter; abort cleanup if generation changed |
| 39 | `service_type` field name varies | Admission check fails on some Pexip versions | Check both `service_type` and `current_service_type` with OR fallback |
| 40 | New token during conference teardown | Ghost PS participant keeps conference alive | Block new token requests with `_ending_conferences` set during cleanup |

---

## SS7: Reference Index

| Reference | Lines | Covers |
|---|---|---|
| `references/service-config-validation.md` | ~200 | Full view set, PIN truth table, ADP format, response examples |
| `references/participant-role-ladder.md` | ~200 | Role flowchart, IdP extraction, SIP matching, rejection code |
| `references/avatar-requirements.md` | ~120 | User lookup chain, PIL pipeline, KC schema, full endpoint |
| `references/classification-lifecycle.md` | ~410 | Token lifecycle, refresh fallback chain, early classification, generation counter, apply/mark/refresh/release, recalc flow |
| `references/event-sink-patterns.md` | ~250 | Admission detection conditions, breakout alias decontamination, breakout migration, debounce, polling |
| `references/gotchas-expanded.md` | ~500 | All 40 gotchas with description, symptom, root cause, fix |

### When NOT to Use This Skill

| Need | Use instead |
|---|---|
| Protocol-level request/response format | `pexip-external-policy` |
| Event sink receiver (without policy server) | `pexip-event-sink` |
| Webapp3 plugin development | `pexip-webapp3-plugin` |
| Management API CRUD operations | `pexip-management-api` |
| Client API call control | `pexip-client-api` |
| Call quality / RCA investigation | `pexip-call-rca` |
