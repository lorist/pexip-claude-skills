# Event Sink Patterns Reference

Implementation patterns for integrating a Pexip Infinity Event Sink with a
policy server's classification system. The event sink provides the
participant lifecycle events needed to trigger classification recalculation.

---

## Event Body Format

Pexip POSTs JSON to your event sink endpoint:

```json
{
  "event": "participant_connected",
  "node": "10.0.1.5",
  "data": {
    "conference": "meeting-001",
    "display_name": "Heidi Smith | General (L6)",
    "destination_alias": "sip:meeting-001@conf.example.com",
    "remote_alias": "sip:heidi@example.com",
    "source_alias": "sip:heidi@example.com",
    "has_media": true,
    "connect_time": "2026-05-15T10:30:00Z",
    "service_type": "conference",
    "role": "chair",
    "protocol": "webrtc"
  }
}
```

Key fields for classification:
- `event`: `participant_connected`, `participant_updated`, `participant_disconnected`, `conference_ended`
- `data.has_media`: true when participant has active media streams
- `data.connect_time`: non-null when participant is connected (not just signaling)
- `data.service_type`: `"conference"`, `"waiting_room"`, `"connecting"`, etc.

---

## Admission Detection

A participant is "admitted" (moved from lobby to conference) when ALL conditions hold:

```python
def _is_admitted(data):
    has_media = data.get("has_media", False)
    connect_time = data.get("connect_time")
    service_type = data.get("service_type", "") or data.get("current_service_type", "")

    is_connected = connect_time is not None
    is_in_conference = service_type not in ("waiting_room", "connecting", "")

    return has_media and is_connected and is_in_conference
```

This fires on both `participant_connected` and `participant_updated` events.
The `participant_updated` case handles the lobby-to-conference transition when
a host admits a participant.

---

## Un-Admission on waiting_room

When a participant is sent back to the lobby (e.g., via the host's "Send to lobby"
button), the event sink receives `service_type == "waiting_room"`. This must
reverse the admission:

```python
if not is_admitted and service_type == "waiting_room":
    participants = get_participants(conference_alias)
    for key, p in participants.items():
        if key == remote_alias or (display_name and p["name"] and
                                    p["name"].split(" (L")[0] in display_name):
            if p.get("admitted"):
                update_participant(conference_alias, key, admitted=False)
                # Recalculate -- the low-ranking participant just left
                recalculate_classification(conference_alias)
            break
```

---

## Breakout Migration

When Pexip moves a participant into a breakout room (via "Edit rooms" > Save),
it fires `participant_connected` in the breakout but does NOT call
`participant_properties` again. The event sink must migrate participant state
from the parent conference:

```python
def _migrate_to_breakout(conference_alias, data):
    """Migrate a parent-conference participant to breakout state."""
    display_name = data.get("display_name", "")
    remote_alias = data.get("destination_alias", "") or data.get("remote_alias", "")

    parent = _parent_alias(conference_alias)
    parent_participants = get_participants(parent)

    for pkey, pp in parent_participants.items():
        pname = pp.get("name") or ""
        matched = (
            pkey == remote_alias
            or (display_name and pname == display_name)
            or (display_name and pname and pname.split(" (L")[0] in display_name)
        )
        if matched:
            # MUST track with admitted=False
            # If admitted=True, the "already admitted?" guard returns early
            # and recalculation never fires
            track_participant(
                conference_alias, pkey, pp.get("level", 0), pname,
                admitted=False,
                in_main_vmr=False,
                conf_fqdn=pp.get("conf_fqdn", ""),
                pin=pp.get("pin", ""),
            )
            return pkey

    return None
```

**Critical:** `admitted=False` is intentional. The normal admission flow
(detected on the next event or the same event's later processing) then
marks the participant as admitted and triggers recalculation. Setting
`admitted=True` during migration skips the recalculation entirely.

---

## Breakout Alias Decontamination

When participants return from breakout rooms, Pexip sets `destination_alias`
to the **conference alias** (the room they're joining), not the participant's
actual remote alias. Using this contaminated value would:

1. Overwrite the stored `remote_alias` with the conference alias
2. Cause `delete_duplicates_by_remote_alias` to match unrelated participants

Strip it before storing:

```python
def _decontaminate_alias(remote_alias, conference_alias):
    """Strip conference alias from destination_alias on breakout return."""
    if not remote_alias:
        return ""
    normalized_ra = _normalize_alias(remote_alias)
    normalized_conf = _normalize_alias(conference_alias)
    parent_alias = conference_alias.split("_breakout_")[0] if "_breakout_" in conference_alias else conference_alias
    normalized_parent = _normalize_alias(parent_alias)
    if normalized_ra == normalized_conf or normalized_ra == normalized_parent:
        return ""  # Discard contaminated alias
    return remote_alias

def _normalize_alias(alias):
    return str(alias).lower().replace("sip:", "").strip()
```

**(field-tested)** — Without this, participants returning from breakout rooms
contaminate each other's cache entries.

---

## Participant Matching

Matching event sink participants to tracked state requires multiple strategies
because display names get modified (appended `(Ln)` by the policy server):

```python
def _find_participant(conference_alias, remote_alias, display_name):
    """Match event sink participant to tracked state."""
    participants = get_participants(conference_alias)

    for key, p in participants.items():
        # Exact key match
        if key == remote_alias:
            return key
        # Exact name match
        if p["name"] and p["name"] == display_name:
            return key
        # Partial match (display names have " | Rank (Ln)" appended)
        if display_name and p["name"] and p["name"].split(" (L")[0] in display_name:
            return key

    return None
```

---

## Admission Detection Conditions

Admission is a multi-condition check. The primary check requires all five:

```python
is_actually_connected = connect_time is not None
is_not_in_waiting_room = service_type not in ("waiting_room", "connecting")

# IVR: null means "no IVR" — treat as complete
is_ivr_complete = True
if call_direction == "in" and ivr_video_complete is not None:
    is_ivr_complete = ivr_video_complete

is_admitted = (has_media and is_actually_connected and is_not_in_waiting_room
               and is_ivr_complete and conference_alias and participant_uuid)
```

**Fallback for lobby → conference transition** (when `has_media` lags behind
`service_type` in event data):

```python
if not is_admitted and is_actually_connected and is_not_in_waiting_room:
    existing = participants.get(conference_alias, participant_uuid)
    if existing and existing.get("level") is not None and not existing.get("is_admitted"):
        is_admitted = True  # Lobby-to-conference transition detected
```

**Pexip version compatibility:** check both `service_type` and
`current_service_type` — the field name varies:

```python
service_type = data.get("service_type", "") or data.get("current_service_type", "")
```

**(field-tested)**

---

## Debounce Implementation

Prevent duplicate recalculation when Pexip sends multiple events for the same
admission (common during `participant_connected` + `participant_updated` pairs):

```python
# In conference state module:
_debounce_set = set()
_debounce_lock = threading.Lock()

def is_debounced(key):
    with _debounce_lock:
        return key in _debounce_set

def add_debounce(key, ttl=5.0):
    with _debounce_lock:
        _debounce_set.add(key)

    def _clear():
        time.sleep(ttl)
        with _debounce_lock:
            _debounce_set.discard(key)

    threading.Thread(target=_clear, daemon=True).start()

def clear_debounce(prefix):
    """Clear all debounce entries matching a prefix (conference cleanup)."""
    with _debounce_lock:
        to_remove = {k for k in _debounce_set if k.startswith(prefix)}
        _debounce_set -= to_remove
```

**Single-worker only:** This in-memory debounce uses `threading.Lock`, which does
NOT work across Gunicorn worker processes. For multi-worker deployments, use
SQLite-backed debounce (same pattern as cross-worker dedup in
`classification-lifecycle.md`) or accept that each worker debounces independently.

Usage in the event handler:
```python
debounce_key = f"{conference_alias}:{matched_key}"
if is_debounced(debounce_key):
    return
add_debounce(debounce_key)
```

---

## Management API Polling Fallback

Some deployments use Management API polling instead of event sink for
classification events. The same admission detection and recalculation logic
applies, just with a different event source:

```python
# Configuration per instance
event_source = get_event_source(instance_id)  # "event_sink" or "management_api"

# In event sink handler:
if event_source == "management_api":
    return  # Skip -- polling handles classification for this instance

# Polling runs on a timer:
def _poll_participants(instance_id, conference_alias):
    """Poll Management API for participant status changes."""
    participants = fetch_from_infinity(
        mgmt_fqdn, user, password,
        f"/api/admin/status/v1/participant/?conference__name={conference_alias}"
    )
    for p in participants:
        if _is_admitted(p):
            _handle_admission(conference_alias, p)
```

---

## Cisco Auto-Bind Pattern

When a SIP participant connects, correlate the source SIP URI against registered
Cisco endpoints to enable chat relay:

```python
def _bind_cisco_endpoint(conference_alias, source_alias):
    """Auto-bind Cisco endpoint xAPI credentials for chat relay."""
    needle = normalize_sip_uri(source_alias)
    if not needle:
        return

    row = db.execute(
        "SELECT hostname, username, password FROM cisco_endpoints WHERE LOWER(sip_uri) = ?",
        (needle,)
    ).fetchone()

    if row and row["hostname"]:
        register_cisco_endpoint(
            conference_alias, row["hostname"],
            username=row["username"] or "admin",
            password=row["password"] or "",
        )
```

Triggered on `participant_connected` when `protocol == "sip"`.

---

## Connectivity Probe Pattern

Use the event sink to verify bidirectional connectivity between Pexip and the
policy server. Encode a probe identifier in the event sink description:

```python
# Format: "PDP connectivity probe <prefix> <unix_ms> <hex_nonce>"
_PROBE_DESC_RE = re.compile(r"^PDP connectivity probe \S+ \d+ [0-9a-f]{6}$")

# In event sink handler:
if event_type == "eventsink_updated":
    desc = data.get("description", "")
    if _PROBE_DESC_RE.match(desc):
        node_ip = body.get("node", "")
        db.execute(
            "INSERT OR REPLACE INTO event_sink_probe_result "
            "(probe_id, received_at, node_ip) VALUES (?, ?, ?)",
            (desc, int(time.time()), node_ip),
        )
```

The dashboard initiates the probe by updating the event sink description via
Management API, then polls the probe_result table for the response.

---

## Key Gotchas for Event Sink + Policy Server

1. **No `participant_disconnected` on breakout reorganization** -- when rooms are
   edited via "Edit rooms" and participants move, no disconnect event fires.
   Prune stale entries when new participants join a breakout.

2. **Always return 200** -- event sink handlers must respond quickly with a 2xx.
   Run recalculation in background threads.

3. **Skip Policy Server participants** -- filter by display_name containing
   "Policy" or "PDP" to avoid recalculating when the PS participant itself
   connects.

4. **Event ordering is not guaranteed** -- `participant_updated` may arrive
   before `participant_connected`. The admission detection logic handles both.
