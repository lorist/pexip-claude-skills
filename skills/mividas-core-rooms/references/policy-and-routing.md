# Policy, Routing, and Authorization (Pexip-flavoured)

Mividas Core acts as a **policy server** for Pexip Infinity — when an Infinity Conferencing Node needs to know whether to admit a call, change its layout, or grant moderator rights, it can call out to Mividas (Pexip's "External policy" feature). The resources below let you drive that decision surface from the API.

There are four related but distinct things:

| Resource | What it controls |
|---|---|
| `/policy_authorization/` | **Time-limited logins** — bookings with an explicit valid-from / valid-to window. |
| `/policy_authorization_override/` | **Predetermined logins** — long-lived rules matched by location/protocol/alias. |
| `/policy_rule/` | Pexip **Call Routing Rules**, synced both directions to/from the Pexip Mgr Node. |
| `/policy/report/` | Per-customer participant-limit / license usage reports. |

## `/policy_authorization/` — time-limited logins

Use this for "alice@example.com is allowed to host this VMR between 14:00 and 15:00 today, and the policy server should grant moderator status when she joins."

```python
auth = c.post("/policy_authorization/", {
    "cluster":         3,                                  # Pexip cluster ID
    "local_alias":     "1234@meet.example.com",            # exact alias the policy server will see
    "valid_from":      "2026-06-12T14:00:00Z",
    "valid_to":        "2026-06-12T15:00:00Z",
    "require_fields":  {"remote_display_name": "Alice"},   # additional must-match fields
    "settings_override": {                                 # what to grant on a match
        "role": "chair",
        "service_type": "conference",
    },
    "usage_limit":     1,                                  # max matches (auto-doubled to 2 for Pexip's two-step handshake)
    "external_id":     "calendar-event-AB-1234",           # your tracking ID
    "source":          "calendar-sync",                    # which system created this
})
```

Key behaviour:

- **`usage_limit` is automatically doubled** for new objects when the cluster is Pexip Infinity, because Pexip's two-step handshake (service config → participant properties) consults the policy server twice for the same logical join. The doubling is invisible — set the limit to the number of *user actions* you want to allow.
- `usage_count` increments on each policy hit; `first_use` records the timestamp of the first hit. `is_active` is computed from validity + usage.
- `timeout` (seconds, writeOnly) is an alternative to setting `valid_to` — a countdown until the authorization expires.
- `local_alias` must be **exact** — what the policy server reports. Build it carefully (full alias including domain, the way Pexip's service config sees it).
- `require_fields` is matched literal-equality against policy server fields like `remote_display_name`, `protocol`, `service_type`, etc. — a strong gate against spoofing.

Use cases: calendar-driven moderator grants, per-meeting overrides, "one-shot" guest tokens.

## `/policy_authorization_override/` — predetermined logins

Use this for standing rules: "anyone who calls from a SIP endpoint in location X to alias `123*` gets settings Y."

```python
c.post("/policy_authorization_override/", {
    "cluster":             3,
    "match_location_name": "HQ",                            # Pexip "system location" name
    "match_incoming_sip":  True,
    "match_incoming_h323": False,
    "match_incoming_webrtc": False,
    "match_incoming_skype":  False,
    "local_alias_match":   r"123.*@meet\.example\.com",     # regexp, implicit ^
    "remote_list": (
        "{\"remote_alias\": \"alice@example.org\"}\n"        # JSON match per line
        "/.*@trusted-partner\\.com/\n"                       # /regexp/ per line
        "trusted-partner.com\n"                              # plain substring per line
    ),
    "settings_override": {"role": "chair"},
})
```

Match modes inside `remote_list` (one rule per line):

| Line format | Matches |
|---|---|
| `{"remote_alias": "...", "registered": "True"}` | All key/value pairs must equal — literal JSON. |
| `/regexp/` | Regular expression. Greedy, anchored at start (implicit `^`). |
| `plaintext` | Plain substring. |

Differences from time-limited:

- No `valid_from` / `valid_to` — overrides are evergreen until deleted.
- No `usage_limit` — they apply to every match.
- Designed for security-policy use ("trust calls from these places"), not booking-driven.

Note the typo in the spec field `match_incoming_skype` (Skype) — this gates Lync / Skype for Business (MS-SIP) calls.

## `/policy_rule/` — Pexip Call Routing Rules

A Mividas-managed wrapper around Pexip's `/api/admin/configuration/v1/call_routing_rule/`. Lets you author CRRs in Mividas and have them sync to (and back from) Pexip.

```python
c.post("/policy_rule/", {
    "name":                "Route US-traffic",
    "tag":                 "internal-route",
    "enable":              True,
    "is_fallback":         False,
    "priority":            100,
    "match_incoming_calls": True,
    "match_outgoing_calls": False,
    "match_source_location": 5,                # Pexip SystemLocation.id (1-based, positive integer)
    "match_source_alias":   ".*",
    "match_source_mode":    "AND",
    "match_incoming_sip":   True,
    "match_incoming_h323":  False,
    "match_incoming_mssip": False,
    "match_incoming_webrtc": False,
    "match_incoming_only_if_registered": True,
    "match_string":         r"^([^@]+)@us\.example\.com$",
    "replace_string":       r"\1@meet.example.com",
    "match_string_full":    False,
    "call_type":            "video",            # audio | video | video-only | auto
    "max_callrate_in":      4096,
    "max_callrate_out":     4096,
    "max_pixels_per_second": "hd",              # sd | hd | fullhd
    "crypto_mode":          "besteffort",       # besteffort | on | off | blank
    "outgoing_location":    5,
    "outgoing_protocol":    "sip",
    "called_device_type":   "external",         # external | registration | mssip_* | gms_conference | teams_conference
    "sip_proxy":            7,                  # Pexip SipProxy.id
    "h323_gatekeeper":      null,
    "mssip_proxy":          null,
    "treat_as_trusted":     False,
    "sync_back":            True,                # mirror this rule back to Pexip
})
```

Sync state:

- `external_id` — the corresponding Pexip CRR ID (read-only).
- `in_sync` — true if the Mividas copy matches what's on Pexip.
- `last_external_sync` — last successful sync timestamp.
- `POST /policy_rule/sync/` — force a sync run.
- `GET /policy_rule/trace/` and `POST /policy_rule/trace/` — interactive routing trace ("what would happen if I called this alias?").

`hit_count` and `hit_count_long` track how often the rule matched (lifetime vs long-window) — useful for finding dead rules.

## Pexip routing semantics

`called_device_type` is the most important enum to get right (`CalledDeviceTypeEnum`):

| Value | Routes to |
|---|---|
| `external` | Registered device if present, else external system (SIP proxy / Lync server / H.323 gatekeeper). The catch-all. |
| `registration` | Registered devices **only** — fail if not found. |
| `mssip_conference_id` | Lync / Skype for Business meeting (Conference ID is the alias). |
| `mssip_server` | Lync / Skype for Business clients, or SfB meetings via a Virtual Reception. |
| `gms_conference` | Google Meet meeting. |
| `teams_conference` | Microsoft Teams meeting. |

`outgoing_protocol` mirrors Pexip's: `h323`, `mssip`, `sip`, `rtmp`, `gms`, `teams`.

`max_pixels_per_second`: `sd` (SD), `hd` (720p), `fullhd` (1080p). The pixel quota is per-participant.

`crypto_mode`:

| Value | Effect |
|---|---|
| `besteffort` | Encrypt if both ends support it; otherwise unencrypted. |
| `on` | Encryption required — connections without media encryption are rejected. |
| `off` | All H.323 / SIP / MS-SIP unencrypted (RTMP still encrypts where supported). |
| empty | Inherit Pexip global setting. |

## License / participant policy

Per-customer participant-count limits.

| Resource | Purpose |
|---|---|
| `/customer_policy/` | Per-customer rule: `participant_limit` (soft), `participant_hard_limit` (hard), `date_start` (effective from). |
| `/customer_policy_state/` | Current snapshot: `active_calls`, `active_participants`, `participant_status` (0 OK / 10 Soft Limit / 20 Hard Limit), `last_check`. |
| `/customer_policy/limits/` | Combined view: policy + name + state. |
| `/customer_match/` | Number-matching rules — assign a `CustomerMatch` (prefix/suffix/regexp) so calls from unknown sources are billed to the right `Customer`. |

`POST /policy/report/?ts_start=&ts_stop=` — historical Plotly graphs of soft-limit hits, soft-limit-30 (windowed), hard-limit hits, and counts.

Hard limit reached → the next participant gets `action: 100` (Reject) from the policy server. Soft limit → `action: 10` (Log) or `20`/`30` (limit to audio / lower quality), depending on configuration.

Limit action types (`ExternalPolicyLogActionEnum`): `0` Ignore · `5` Log · `20` Audio-only · `30` SD · `35` 720p · `100` Reject.

## Inspecting policy decisions

`/debug/pexip_policy/` and `/debug/policy_log/` log every policy decision. Filter by `service_tag`, `action`, `customer`, `type` (`Participant` / `Call` / `Diff`), and `level` (`Debug` / `Warning`). When a customer says "Mividas rejected my call wrongly", that's your first stop. `/debug/external_policy_log/` has `LimitEnum` (`0` OK / `10` Soft Limit / `20` Hard Limit) for license-driven actions.

## Common pitfalls

- **The `usage_limit` doubling on Pexip is silent.** If you set `usage_limit: 2` expecting two policy hits, you'll actually get four — set it to the human-meaningful count.
- `local_alias` must match what Pexip's policy server reports **exactly** (including domain). For "Virtual Reception"-routed calls, the alias the policy server sees is the VR's alias, not the user-typed one — check `/debug/pexip_policy/` to confirm what's actually being sent before authoring rules.
- `match_source_location` requires the location's Pexip-side integer ID, not its name. (The `match_source_location_name` field on `PolicyRule` is read-only and just a human label.)
- `policy_authorization_override.local_alias_match` is anchored at start (`^` implicit) but **not at end** — add `$` if you want exact-match.
- `policy_rule.priority` is checked **ascending**, range 1–200. Lower number wins, like Pexip's CRR list.
- Customer matching: if a call comes in that doesn't match any `CustomerMatch`, it's attributed to the cluster's default customer. That can hide a routing bug as a quiet bill-to-wrong-tenant.
