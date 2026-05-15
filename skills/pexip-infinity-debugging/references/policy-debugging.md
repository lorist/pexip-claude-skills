# Policy Debugging — Expanded Reference

Detailed decision trees, validation checklists, and the full PIN truth table
for debugging Pexip Infinity External Policy issues.

---

## Decision Tree: Policy Response Rejected

```
Symptom: "Alias didn't match any Conference or Gateway rule"
  |
  +-- Is the policy server URL correct on Pexip?
  |     GET /api/admin/configuration/v1/policy_server/
  |     Check: URL points to current PDP instance (not stale ngrok)
  |     |
  |     +-- URL is stale/wrong → UPDATE the URL, wait 30s for replication
  |     |
  |     +-- URL is correct → Are requests arriving at PDP?
  |           |
  |           +-- No requests in PDP logs → connectivity issue
  |           |     Check: firewall rules, TLS cert, DNS resolution
  |           |     Test: curl -k https://<pdp-url>/rbac-idp/policy/v1/service/configuration
  |           |
  |           +-- Requests arriving → Is the response valid JSON?
  |                 |
  |                 +-- Check support log: q=externalpolicy
  |                 +-- Check response format (see checklist below)
  |                 +-- Check PIN rules (see truth table below)
  |                 +-- Check view value is one of the 14 valid layouts
```

---

## Decision Tree: Policy Server Not Receiving Requests

```
Symptom: PDP logs show zero /policy/v1/service/configuration hits
  |
  +-- Is the policy server resource enabled?
  |     GET /api/admin/configuration/v1/policy_server/
  |     Check: resource exists and is not disabled
  |     |
  |     +-- No policy server resource → CREATE one with correct URL
  |     |
  |     +-- Resource exists → Is the URL current?
  |           |
  |           +-- Stale ngrok URL → update URL  **(field-tested, #1 cause)**
  |           |
  |           +-- URL correct → Is the policy server assigned to the right location?
  |                 |
  |                 +-- Wrong location → calls land on nodes not covered by this policy server
  |                 |
  |                 +-- Correct location → Can the conferencing node reach PDP?
  |                       |
  |                       +-- Firewall blocking? TLS cert issue? DNS not resolving?
  |                       +-- Test from the conferencing node's network
```

---

## Response Format Validation Checklist

Every `service_configuration` response MUST include these fields or the entire response is rejected silently:

### Required envelope
```json
{
  "status": "success",
  "action": "continue",
  "result": { ... }
}
```

### Required result fields
- `service_type` — must be `"conference"` or `"gateway"` (string)
- `name` — conference/gateway name (string, non-empty)
- `local_alias` — the alias that was dialed (string, must match or Pexip ignores)

### Validated result fields (invalid value rejects entire response)

**`view`** — must be exactly one of these 14 values:
| API value | Layout name |
|---|---|
| `one_main_zero_pips` | Speaker only |
| `one_main_seven_pips` | 1+7 |
| `one_main_twentyone_pips` | 1+21 |
| `two_mains_twentyone_pips` | 2+21 |
| `one_main_thirtythree_pips` | 1+33 |
| `four_mains_zero_pips` | 2x2 |
| `nine_mains_zero_pips` | 3x3 |
| `sixteen_mains_zero_pips` | 4x4 |
| `twentyfive_mains_zero_pips` | 5x5 |
| `five_mains_seven_pips` | Adaptive Composition |
| `one_main_twelve_pips` | 1+12 |
| `four_mains_eight_pips` | 4+8 |
| `two_mains_zero_pips` | Side by side |
| `three_mains_zero_pips` | 1x3 |

**Common mistake:** Using `"adaptive_composition"` or `"ac"` instead of `"five_mains_seven_pips"` **(field-tested)**

**`allow_guests`** — boolean. If `true`, `pin` MUST be set (non-empty string).

**`guest_pin`** — if set, `allow_guests` must be `true` AND `pin` must also be set.

---

## PIN Validation Truth Table

Pexip validates PIN fields strictly. Any violation causes `"Invalid service configuration"` in the support log and the call fails.

| # | `allow_guests` | `pin` | `guest_pin` | Result |
|---|---|---|---|---|
| 1 | `false` | not set | not set | OK — no PINs, host-only conference |
| 2 | `false` | `"1234"` | not set | OK — PIN-protected, host-only |
| 3 | `false` | not set | `"5678"` | **REJECTED** — guest_pin without allow_guests **(field-tested)** |
| 4 | `true` | not set | not set | **REJECTED** — allow_guests requires pin **(field-tested)** |
| 5 | `true` | `"1234"` | not set | OK — guests enter without PIN, hosts use 1234 |
| 6 | `true` | `"1234"` | `"5678"` | OK if lengths match — hosts use 1234, guests use 5678 |
| 7 | `true` | `"1234"` | `"56789"` | **REJECTED** — PIN lengths must match **(field-tested)** |
| 8 | `true` | `"1234"` | `"1234"` | **REJECTED** — pin must not equal guest_pin **(field-tested)** |

### PIN length fix

When PINs have different lengths, append `#` to BOTH:
- `pin: "1234#"`, `guest_pin: "56789#"` → both are 6 characters → **accepted** **(field-tested)**

### Empty string PIN trap

- `pin: ""` is treated as "no PIN" by Pexip, NOT as a valid empty PIN
- This triggers the same failure as rule #4 when `allow_guests: true`

---

## Decision Tree: Participant Rejection Not Working

```
Symptom: participant_properties returns reject but participant still joins
  |
  +-- Is the response using the correct format?
  |     Must be: {"status":"success", "action":"continue", "result":{"reject":true}}
  |     |
  |     +-- Using _json_ok() wrapper?
  |     |     _json_ok() sets action:"continue" at the top level which
  |     |     OVERRIDES any reject in the result  **(field-tested)**
  |     |     Fix: use bare jsonify() for reject responses
  |     |
  |     +-- Using action:"reject" in envelope?
  |           action:"reject" is NOT the correct way to reject
  |           Use action:"continue" with result.reject=true
  |
  +-- Is the policy server handling participant_properties?
  |     Some policy servers only handle service_configuration
  |     Check policy server config on Pexip
  |
  +-- Is the rejection being logged?
        Search support log: q=reject
        If no entries → response not reaching Pexip
        If entries present → check exact response format
```

---

## The `_json_ok()` Trap

This is a subtle and dangerous pattern **(field-tested)**:

```python
# WRONG — _json_ok wraps with action:"continue" which overrides reject
def participant_properties():
    if should_reject:
        return _json_ok({"reject": True})
    # The participant is NOT rejected because the envelope says "continue"

# CORRECT — bare response with explicit action
def participant_properties():
    if should_reject:
        return jsonify({
            "status": "success",
            "action": "continue",
            "result": {"reject": True}
        })
```

The `action: "continue"` in the envelope means "continue processing this response" — it does NOT mean "allow the participant to continue." The `reject: true` in the result is what actually rejects.

---

## Decision Tree: Service Configuration Response Ignored

```
Symptom: policy response sent but Pexip uses default/different config
  |
  +-- Is the response being cached?
  |     Pexip caches FAILED responses for several minutes  **(field-tested)**
  |     Previous bad response may still be cached
  |     Fix: wait 3-5 minutes, or start a new conference
  |
  +-- Is local_alias in the response matching the dialed alias?
  |     Pexip ignores responses where local_alias doesn't match
  |     Check: strip sip: prefix and @domain from the alias
  |
  +-- Is the view value valid?
  |     Invalid view → entire response rejected silently
  |     Check against the 14 valid values above
  |
  +-- Are PIN fields valid?
  |     Invalid PIN combo → "Invalid service configuration" in support log
  |     Check against truth table above
  |
  +-- Is service_type correct?
        Must be "conference" or "gateway" (lowercase string)
        Wrong type → response ignored
```

---

## Debugging with Support Log Entries

### What a successful policy call looks like

In the support log, search for `externalpolicy`. A successful flow shows:
1. `ExternalPolicy: Sending request to <url>` — Pexip is calling your server
2. `ExternalPolicy: Received response` — your server responded
3. Conference creation with the policy-specified settings

### What a failed policy call looks like

- `ExternalPolicy: Error contacting policy server` → connectivity failure (timeout, DNS, TLS)
- `ExternalPolicy: Invalid response` → response was not valid JSON or missing required fields
- `Invalid service configuration` → PIN validation failed (see truth table)
- No ExternalPolicy entries at all → policy server not configured or not assigned to the location

### Useful log correlation

When debugging a specific call:
1. Search for the dialed alias (e.g., `q=pdp001-demo001`)
2. Note the timestamp of the call attempt
3. Search for `externalpolicy` in the same time window
4. Check if the policy response appears and what Pexip did with it
