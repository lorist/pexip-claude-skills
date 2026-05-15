# Participant Role Ladder Reference

Complete role assignment logic for `/policy/v1/participant/properties` responses.
The role ladder determines which participants get `chair` (host), `guest`, lobby
bypass, or outright rejection based on their identity and classification level.

---

## Role Assignment Flowchart

Evaluate these in order. The first match wins:

```
1. Is remote_alias "Policy Server" or "PDP Connectivity Test"?
   YES -> chair + bypass_lock: True
   (Must be first -- PS participant must never be rejected or sent to lobby)

2. Is this a breakout room participant?
   YES -> bypass_lock: True (keep whatever role was assigned)
   (Breakout participants were already authenticated in parent conference)

3. Does the participant have IdP attributes?
   YES -> Extract title, compute classification level
     3a. Level >= auto_admit_min AND l6_auto_chair?
         YES -> chair + bypass_lock: True
     3b. Level > 0 but below threshold?
         -> guest (lands in lobby, host admits)
     3c. Level <= l1_rejection_threshold AND meeting classified above?
         -> REJECT with reason message
   NO -> Go to step 4

4. Non-IdP participant (SIP, PSTN, unregistered):
   4a. Is there a matching SIP endpoint in the endpoint map?
       YES -> Use configured level, apply same tier rules as IdP
   4b. No match:
       -> Passthrough preauthenticated_role (NEVER hardcode "guest")
```

---

## IdP Attribute Extraction

Pexip sends IdP attributes in both query string and POST body. The POST body is
the primary source; query string is a fallback.

```python
# POST body (JSON)
body = request.get_json(silent=True) or {}
idp_attributes = body.get("idp_attributes", {})
if not isinstance(idp_attributes, dict):
    idp_attributes = {}

# Title (primary classification attribute)
title = idp_attributes.get("title", "") or idp_attributes.get("Title", "")
if isinstance(title, list):
    title = title[0] if title else ""
title = str(title).strip()

# Fallback: query string idp_attribute_* parameters
if not title:
    for key in request.args:
        if key.startswith("idp_attribute_") and "title" in key.lower():
            title = request.args.get(key, "")
            break

# Display name components
first_name = idp_attributes.get("firstName", "") or idp_attributes.get("firstname", "")
if isinstance(first_name, list):
    first_name = first_name[0] if first_name else ""

last_name = idp_attributes.get("lastName", "") or idp_attributes.get("lastname", "")
if isinstance(last_name, list):
    last_name = last_name[0] if last_name else ""
```

**Key patterns:**
- Values may be list-wrapped: `{"title": ["General"]}` instead of `{"title": "General"}`
- Key casing varies: `firstName` vs `firstname`, `Title` vs `title`
- Always `str().strip()` the final value

---

## Classification Map Lookup

```python
# Map format: {lowercase_rank_name: integer_level}
classification_map = {
    "private": 1,
    "corporal": 2,
    "sergeant": 3,
    "captain": 4,
    "colonel": 5,
    "general": 6,
}

# Lookup
title_lower = title.lower().strip()
participant_level = classification_map.get(title_lower, 0)
```

The map format may vary between implementations. Some use a list of dicts:
```python
# List-of-dicts format
[{"rank_name": "Private", "level": 1}, {"rank_name": "General", "level": 6}]
```

Always normalize to `{name_lower: int_level}` before lookup:
```python
if isinstance(class_map_raw, list):
    class_map = {r["rank_name"].lower(): int(r["level"]) for r in class_map_raw}
```

---

## SIP Endpoint Matching

For non-IdP participants, try to match `remote_alias` against configured SIP endpoints:

```python
# Try exact match first
sip_match = db.execute(
    "SELECT display_name, level FROM sip_endpoint_map "
    "WHERE instance_id = ? AND meeting_name = ?",
    (instance_id, remote_alias)
).fetchone()

# Try without sip: prefix
if not sip_match:
    clean_alias = remote_alias.replace("sip:", "").strip()
    sip_match = db.execute(
        "SELECT display_name, level FROM sip_endpoint_map "
        "WHERE instance_id = ? AND (meeting_name = ? OR meeting_name LIKE ?)",
        (instance_id, clean_alias, f"%{clean_alias}")
    ).fetchone()

if sip_match:
    participant_level = int(sip_match["level"])
    # Apply same tier rules as IdP participants
```

Three-stage lookup: exact remote_alias, stripped `sip:` prefix, LIKE pattern match.

---

## Rejection Response

When rejecting a participant, NEVER use `_json_ok()`. The `action: "continue"` in
the envelope wrapping overrides the `action: "reject"` in the result:

```python
# CORRECT: bare jsonify
return jsonify({
    "status": "success",
    "action": "reject",
    "result": {
        "reject_reason": "You are not authorized to join this meeting"
    },
})

# WRONG: _json_ok wraps action: "continue" which overrides reject
return _json_ok({
    "action": "reject",  # Silently ignored -- continue wins
    "reject_reason": "...",
})
```

---

## Denial Notification

When rejecting a participant from a classified meeting, notify the hosts:

```python
# Build notification message
participant_name = remote_display_name or remote_alias or "Unknown"
rank_name = title.title() if title else f"L{level}"
meeting_class_name = _level_to_rank_name(class_map, current_meeting_level)

notify_msg = (
    f"{participant_name} with rank {rank_name} (L{level}) attempted to join "
    f"Classified meeting running at {meeting_class_name} (L{current_meeting_level})"
)

# Send via Client API in background thread
def _bg_notify():
    from services.client_api import send_message
    ok = send_message(conf_fqdn, conference_alias, notify_msg, ps_token)
    if not ok:
        # Retry with fresh token
        new_token, _ = request_token(conf_fqdn, conference_alias)
        if new_token:
            send_message(conf_fqdn, conference_alias, notify_msg, new_token)

threading.Thread(target=_bg_notify, daemon=True).start()
```

The `send_message` call MUST use `Content-Type: text/plain` for plugin delivery.

---

## Display Name Formatting

Build enriched display names that include rank and level:

```python
display_parts = []

# Name component
if first_name or last_name:
    display_parts.append(f"{first_name} {last_name}".strip())
elif remote_display_name:
    display_parts.append(remote_display_name)

# Rank + level component
if title and participant_level > 0:
    display_parts.append(f"{title} (L{participant_level})")
elif participant_level > 0:
    display_parts.append(f"L{participant_level}")

result["remote_display_name"] = " | ".join(display_parts)
# Example: "Heidi Smith | General (L6)"
```

For SIP endpoints:
```python
if rank_name:
    sip_display = f"{display_name} | {rank_name} (L{participant_level})"
else:
    sip_display = f"{display_name} | L{participant_level}"
```

---

## Additional Response Fields

```python
result = {
    "preauthenticated_role": "chair",       # or "guest"
    "bypass_lock": True,                     # Skip lobby
    "remote_display_name": "Name | Rank (L6)",
    "overlay_text": f"L{participant_level}", # Classification overlay
    "service_tag": f"level-{participant_level}",
}
```

The `service_tag` field on the participant response is separate from the
`service_tag` on the service configuration response. The participant-level tag
is used for per-participant tracking.

---

## Reverse Rank Lookup

When you have a level and need the rank name (for display or notification):

```python
def _level_to_rank_name(class_map, level):
    """Reverse-lookup: find the rank name for a given classification level."""
    for rank_name, rank_level in class_map.items():
        if rank_level == level:
            return rank_name.title()
    return f"L{level}"
```
