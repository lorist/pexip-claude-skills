# Service Configuration Validation Reference

Detailed validation rules for `/policy/v1/service/configuration` responses.
Every field value is validated server-side by Pexip Infinity — an invalid value
in any field causes the **entire** response to be silently rejected.

---

## Valid View Values

Pexip Infinity accepts exactly these 14 values for the `view` field. Any other
value (including typos, legacy names, or empty string) causes the entire policy
response to be rejected with 404 "Neither conference nor gateway found."

```python
_INFINITY_VALID_VIEWS = frozenset({
    "one_main_zero_pips",          # Speaker only
    "one_main_seven_pips",         # Speaker + 7 thumbnails
    "one_main_twentyone_pips",     # Speaker + 21 thumbnails (default)
    "two_mains_twentyone_pips",    # 2 speakers + 21 thumbnails
    "four_mains_zero_pips",        # 2x2 grid
    "nine_mains_zero_pips",        # 3x3 grid
    "sixteen_mains_zero_pips",     # 4x4 grid
    "twentyfive_mains_zero_pips",  # 5x5 grid
    "one_main_thirtythree_pips",   # Speaker + 33 thumbnails
    "one_main_twelve_around",      # Speaker + 12 around
    "two_mains_eight_around",      # 2 speakers + 8 around
    "one_main_nine_around",        # Speaker + 9 around
    "one_main_twentyone_around",   # Speaker + 21 around
    "five_mains_seven_pips",       # Adaptive Composition (5 + 7)
})
```

## View Alias Map

Legacy and commonly mistyped view names mapped to valid values:

```python
_VIEW_ALIAS_MAP = {
    # Common aliases
    "ac": "five_mains_seven_pips",            # Adaptive Composition
    "carousel": "one_main_twentyone_pips",     # Active speaker + carousel
    "speaker": "one_main_zero_pips",           # Speaker only

    # Typos: underscore between "twenty" and "one"
    "two_mains_twenty_one_pips": "two_mains_twentyone_pips",
    "one_main_twenty_one_pips": "one_main_twentyone_pips",

    # Wrong suffix: _pips vs _around
    "one_main_nine_pips": "one_main_nine_around",
    "one_main_twelve_pips": "one_main_twelve_around",
    "two_mains_eight_pips": "two_mains_eight_around",

    # Nonexistent grid sizes mapped to nearest valid
    "two_mains_zero_pips": "four_mains_zero_pips",
    "three_mains_zero_pips": "four_mains_zero_pips",
}

_VIEW_DEFAULT = "one_main_twentyone_pips"
```

## Complete Normalization Function

```python
def _normalize_view(view):
    """Map any incoming view value to one Infinity accepts.

    Returns a safe default for blank/None/unknown values so the policy
    response is never rejected for a bad view field.
    """
    if not view:
        return _VIEW_DEFAULT
    if view in _INFINITY_VALID_VIEWS:
        return view
    mapped = _VIEW_ALIAS_MAP.get(view)
    if mapped:
        return mapped
    logger.warning("Unknown VMR view %r -- falling back to %s", view, _VIEW_DEFAULT)
    return _VIEW_DEFAULT
```

---

## PIN Validation Truth Table

Pexip validates PINs server-side. These combinations have been tested:

| `pin` | `guest_pin` | `allow_guests` | Result |
|---|---|---|---|
| `"1234"` | (omitted) | `true` | OK (all guests use host PIN) |
| (omitted) | (omitted) | `true` | **REJECTED** (rule #1) |
| `""` | (omitted) | `true` | **REJECTED** (rule #2) |
| `"1234"` | `"5678"` | `false` | **REJECTED** (rule #3) |
| `"1234"` | `"56789"` | `true` | **REJECTED** (rule #4, length mismatch) |
| `"1234#"` | `"56789#"` | `true` | OK (both end with `#`) |
| `"1234#"` | `"5678"` | `true` | **REJECTED** (rule #5, mixed `#`) |
| `"1234"` | `"1234"` | `true` | **REJECTED** (rule #6, identical) |
| `"1234"` | `"5678"` | `true` | OK |
| `"1234"` | (omitted) | `false` | OK (locked, host only) |

### Safe PIN Patterns

```python
# Pattern 1: Single-PIN locked conference (all users enter as host)
result["allow_guests"] = True
result["locked"] = True
result["pin"] = "1234"
# No guest_pin -- everyone uses host PIN, enters as chair

# Pattern 2: Host + Guest with different lengths
pin = "1234"
guest_pin = "56789"
# Append # to both to satisfy length rule
result["pin"] = pin + "#"
result["guest_pin"] = guest_pin + "#"

# Pattern 3: Breakout room (no PIN, no allow_guests)
result["locked"] = False
result.pop("allow_guests", None)  # MUST remove, not set to False
```

---

## SIP Alias Normalization

```python
def _normalize_alias(alias):
    """Strip SIP URI components: 'sip:name@domain' -> 'name'."""
    a = alias
    if a.startswith("sip:"):
        a = a[4:]
    if "@" in a:
        a = a.split("@")[0]
    return a
```

Always call on `local_alias` from the request. SIP calls send the full URI;
WebRTC/API calls send the bare name. Normalization must be idempotent.

---

## Breakout Room Detection

```python
def _is_breakout(alias):
    """Return True if alias looks like a breakout room."""
    if not alias:
        return False
    s = str(alias).lower()
    return "_breakout_" in s or s.startswith("breakout_") or s.endswith("_breakout")

def _parent_alias(breakout_alias):
    """Extract the parent conference alias from a breakout room alias."""
    if "_breakout_" in str(breakout_alias):
        return str(breakout_alias).split("_breakout_")[0]
    return breakout_alias
```

Check both `local_alias` AND `unique_service_name` — during a breakout,
`local_alias` stays as the parent alias while `unique_service_name` has the
breakout identifier.

---

## ADP Entry Format

Each automatic participant entry requires these fields:

```python
adp_entry = {
    "remote_alias": "sip:boardroom@domain.com",   # Full SIP URI
    "local_alias": "boardroom",                     # Stripped for display
    "local_display_name": "Board Room A",           # Human name
    "description": "ADP to Board Room A",           # Optional description
    "protocol": "sip",                              # "sip", "h323", "mssip"
    "role": "guest",                                # Always "guest" for ADP
    "keep_conference_alive": "keep_conference_alive_never",  # Required
}

# Optional: location routing
if adp_location:
    adp_entry["system_location_name"] = adp_location
```

ADP entries are placed in `result["automatic_participants"]` as a list.

**Exclusion rules:**
- Exclude when `is_policy_server=True` (Policy Server's own join)
- Exclude in breakout rooms
- Deduplicate by normalized remote alias

---

## Response Format Examples

### Successful VMR creation

```python
return jsonify({
    "status": "success",
    "action": "continue",
    "result": {
        "service_type": "conference",
        "name": "meeting-001",
        "local_alias": "meeting-001",
        "service_tag": "pdp-prefix",
        "allow_guests": True,
        "locked": True,
        "pin": "1234",
        "non_idp_participants": "allow_if_trusted",
        "view": "one_main_twentyone_pips",
        "host_identity_provider_group": "Keycloak - MyRealm",
        "guest_identity_provider_group": "Keycloak - MyRealm",
        "enable_overlay_text": True,
    }
})
```

### Passthrough (let Pexip use local config)

```python
return jsonify({
    "status": "success",
    "action": "continue",
    "result": {}
})
```

### Breakout room

```python
return jsonify({
    "status": "success",
    "action": "continue",
    "result": {
        "service_type": "conference",
        "name": "meeting-001_breakout_abc123",
        "local_alias": "meeting-001_breakout_abc123",
        "service_tag": "pdp-prefix",
        "locked": False,
        # No allow_guests, no pin, no IdP group
        "view": "one_main_twentyone_pips",
        "enable_overlay_text": True,
    }
})
```

**Never** include `allow_guests` in a breakout response. Even `allow_guests: false`
is safe, but removing it entirely prevents any future PIN-related validation issues.
