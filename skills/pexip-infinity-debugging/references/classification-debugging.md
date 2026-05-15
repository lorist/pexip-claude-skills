# Classification Debugging — Expanded Reference

Detailed debugging steps for Pexip Infinity conference classification systems:
level calculation, Client API token lifecycle, cross-worker state, and
the gap between PDP state and actual Infinity state.

---

## Classification Architecture Overview

Classification flows through three systems:

1. **Policy Server** (`participant_properties`) — assigns classification level to each participant via `overlay_text`
2. **Client API** — sets the conference-wide classification level on Infinity via `set_classification_level`
3. **Event Sink** — notifies PDP of participant changes that trigger recalculation

The chain is: participant joins → policy assigns level → PDP tracks level → PDP recalculates conference level → Client API pushes to Infinity.

---

## Client API Token Lifecycle

### Token acquisition
- PDP requests a Client API token using the Policy Server's participant credentials
- The Policy Server participant is created during `service_configuration` and must be `chair` with `bypass_lock` **(field-tested)**
- Token endpoint: Client API on the conferencing FQDN

### Token expiry
- Tokens expire at approximately **120 seconds** **(field-tested)**
- `_refresh_token_if_needed()` proactively refreshes at **90 seconds** to prevent 403 errors mid-operation **(field-tested)**
- Token age is tracked via `token_time` in `conference_state.db`

### Token refresh flow
```
1. Check token age > 90s
2. If expired → call _refresh_token_if_needed()
3. If refresh fails with 403 → request entirely new token
4. If new token fails → conference may be locked+IdP (cannot get token)
   → Fall back to stored Policy Server token  **(field-tested)**
```

### Stale tokens across server restarts
- `conference_state.db` persists at `/tmp/conference_state.db` across server restarts **(field-tested)**
- Tokens from before the restart are stale (>120s old)
- `_refresh_token_if_needed()` catches this via `token_time` age check
- Stale entries are cleared on `conference_ended` events
- If no `conference_ended` fires (e.g., server was down when conference ended), stale entries accumulate
- Manual fix: clear entries from `conference_state.db` for conferences that no longer exist

---

## Token Failure Decision Tree

```
Client API returns 403
  |
  +-- "Invalid role"
  |     Policy Server participant not yet admitted as chair
  |     Wait 1.5s after token request before using  **(field-tested)**
  |     Check: service_configuration response has preauthenticated_role="chair"
  |
  +-- "Invalid token"
  |     Token expired (>120s) or invalidated by Pexip
  |     Action: refresh or request new token
  |     Check: token_time in conference_state.db
  |
  +-- 403 on request_token itself
  |     Conference is locked + IdP-authenticated  **(field-tested)**
  |     Client API rejects unauthenticated token requests
  |     Fix: use stored Policy Server token (already has chair + bypass_lock)
  |
  +-- 403 after successful token request
        Token was valid but became invalid between request and use
        Race condition: another worker may have refreshed the token
        Fix: retry with fresh token from DB
```

---

## Cross-Worker Dedup

When running multiple Gunicorn workers, classification state must be in a shared store:

### SQLite-based state (current pattern)
- All classification state lives in `/tmp/conference_state.db` (WAL mode) **(field-tested)**
- Multiple workers can read/write safely with WAL
- Each worker sees the same state

### Dedup for recalculation
- Multiple event sink events can trigger recalculation simultaneously
- Use `_admission_debounce` set with conference+participant key
- Debounce set is stored in `conference_state.db`, shared across workers
- Clear debounce entries on `conference_ended` to prevent stale entries **(field-tested)**

### Verification
```sql
-- Check for stale conference entries
SELECT * FROM conference_participants WHERE conference_alias NOT IN (
    SELECT alias FROM conference_state WHERE ended_at IS NULL
);

-- Check token freshness
SELECT conference_alias,
       token_time,
       (strftime('%s', 'now') - token_time) AS age_seconds
FROM conference_state
WHERE ended_at IS NULL;
```

---

## Level Calculation Chain

Classification level is calculated with three priority tiers:

### Priority 1: Explicit API override
- Admin sets level via Client API `set_classification_level`
- This overrides all participant-based calculations
- Rare in normal operation

### Priority 2: Admitted IdP participants
- Only **admitted** participants with IdP classification levels are considered
- `min(admitted_idp_levels)` = conference level
- Participants in lobby (not yet admitted) are excluded from calculation

### Priority 3: All IdP participants
- If no participants are admitted yet, consider all IdP participants
- This handles the "early classification" case where the first IdP user joins

### Recalculation trigger points
1. New participant joins with an IdP classification level
2. Participant is admitted from lobby (level now counts for priority 2)
3. Participant leaves (level removed from calculation)
4. Event sink delivers `participant_updated` with state change

---

## Debug Endpoint Usage

### `/debug/states`

Returns the current PDP classification state per conference:
```json
{
  "pdp001-demo001": {
    "current_level": 3,
    "participants": {
      "participant-uuid-1": {"level": 3, "admitted": true, "name": "Alice"},
      "participant-uuid-2": {"level": 2, "admitted": true, "name": "Bob"}
    },
    "token": "...",
    "token_time": 1716000000
  }
}
```

### Critical warning

**PDP debug state `current_level` does NOT reflect the actual Infinity classification.** **(field-tested)**

The debug endpoint shows what PDP *computed* as the level and what it *attempted* to set via Client API. It does NOT confirm that `set_classification_level` succeeded on Infinity.

To verify actual classification:
1. Check the debug endpoint for what PDP thinks the level is
2. Look at the meeting visually — the classification banner shows the actual Infinity level
3. If they differ, the Client API call failed silently (token issue, network issue, or race condition)

---

## PDP State vs Actual Infinity State

### Why they diverge

| Cause | PDP shows | Infinity shows | Fix |
|---|---|---|---|
| Client API token expired | Correct level | Stale level | Force token refresh |
| Client API call failed (network) | Correct level | Stale level | Retry recalculation |
| Race condition (two workers) | Correct level | Different level | Last writer wins; retry |
| Server restarted mid-conference | State from DB | May be correct | Trigger full recalculation |
| Conference ended but no event | Stale state | Conference gone | Clear stale entries |

### Forcing reconciliation

1. Trigger a recalculation by admitting a participant or calling the `/admit` endpoint
2. Check debug endpoint after recalculation completes
3. Verify visually in the meeting

---

## Early Classification Timing

"Early classification" is when the first IdP participant joins and triggers a Client API call
before they are fully admitted.

### Timing sequence
```
1. Participant connects → service_configuration fires (t=0)
2. Policy Server joins as participant → gets token (t=0.1s)
3. IdP participant joins → participant_properties fires (t=0.5s)
4. PDP tracks participant level → triggers recalculation (t=0.5s)
5. Client API set_classification_level → needs valid token (t=0.5s)
   → Token may not be ready if step 2 hasn't completed
   → Wait 1.5s after token request before using  **(field-tested)**
```

### Failure mode: token not ready
- If `set_classification_level` is called before the token is valid, it returns 403 "Invalid role"
- The Policy Server participant needs to be admitted as chair first
- Fix: add a 1.5s delay between token acquisition and first Client API call

---

## Event-Sink-Triggered vs Direct Classification

### Event-sink-triggered (secondary path)
- Event sink delivers `participant_updated` → PDP checks if admission state changed → triggers recalculation
- Lag: 1-30 seconds depending on load **(common pattern)**
- Unreliable in dev with ngrok **(field-tested)**

### Direct classification (primary path)
- `/admit` endpoint admits participant → immediately triggers recalculation
- No event sink dependency
- Recommended for timing-critical operations **(field-tested)**

### Skip classification for test VMRs
- `-macrotest` and `-plugintest` aliases skip early classification **(field-tested)**
- Prevents Policy Server join/leave spam during automated testing
- Detected via alias suffix pattern matching in `participant_properties`

---

## Common Classification Issues Checklist

When classification is not working, check in order:

1. **Is the IdP title attribute being sent?**
   - Check SAML assertion for `title` attribute
   - Check Keycloak User Profile schema includes `title` (v26+) **(field-tested)**

2. **Is the classification_map configured?**
   - Check PDP config: maps IdP title → classification level number

3. **Is participant_properties returning the level?**
   - Check response includes `overlay_text` with classification level
   - Search support log: `q=participant_properties`

4. **Is the Client API token valid?**
   - Check token age in `conference_state.db`
   - Check for 403 errors in PDP logs

5. **Is event sink delivering events?**
   - Check ngrok inspector for `participant_updated` events
   - If not, recalculation only triggers on `/admit`

6. **Is `l1_rejection_threshold` set correctly?**
   - `threshold=N` rejects levels 1..N, not just level N **(field-tested)**

7. **Does the conference have mixed-level participants?**
   - Same-level participants → level is trivially correct
   - All at level 1 → threshold check applies
