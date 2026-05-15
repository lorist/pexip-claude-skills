# Gotchas Expanded Reference

All 40 production-tested gotchas with description, symptom, root cause, and fix.

---

## Service Configuration Gotchas

### 1. `_json_ok()` wraps `action: "continue"` — reject responses MUST use bare `jsonify()`

**Symptom:** Reject responses never actually reject — participant is admitted anyway.

**Root cause:** `_json_ok()` wraps the result in `{"status": "success", "action": "continue", "result": {...}}`. When the result dict contains `"action": "reject"`, the outer `"action": "continue"` takes precedence.

**Fix:**
```python
# WRONG
return _json_ok({"action": "reject", "reject_reason": "Denied"})

# CORRECT
return jsonify({
    "status": "success",
    "action": "reject",
    "result": {"reject_reason": "Denied"},
})
```

### 2. `allow_guests: true` without `pin` causes silent 404

**Symptom:** Conference creation returns 404 "Neither conference nor gateway found" with no useful error detail.

**Root cause:** Pexip requires a PIN when `allow_guests` is true. Without one, the entire policy response is rejected.

**Fix:** Always set `pin` when `allow_guests` is true, or omit `allow_guests` entirely.

### 3. Demo aliases with `is_policy_server=True` must route through demo builder

**Symptom:** Policy Server's own Client API join returns 404 for demo aliases.

**Root cause:** The generic VMR branch reads `policy_server_pin` from instance config (which may be empty after setup slimming), resulting in `allow_guests: true` with no PIN.

**Fix:** Check for demo alias pattern before the generic branch. Route `is_policy_server=True` calls through the demo builder, which strips IdP groups and ADPs but preserves the demo's PIN and theme.

### 4. Breakout service config must strip `allow_guests`

**Symptom:** Breakout room creation fails with 404.

**Root cause:** Breakout rooms have no PIN. `allow_guests: true` without `pin` triggers rejection.

**Fix:**
```python
if is_breakout_room:
    result["locked"] = False
    result.pop("allow_guests", None)  # MUST pop, not set to False
```

### 5. PIN length mismatch — append `#` to BOTH

**Symptom:** Policy response rejected when host and guest PINs have different lengths.

**Root cause:** Pexip requires either matching PIN lengths or both PINs ending with `#`.

**Fix:**
```python
if pin and guest_pin and len(pin) != len(guest_pin):
    pin = pin.rstrip("#") + "#"
    guest_pin = guest_pin.rstrip("#") + "#"
```

### 6. `non_idp_participants` must be `"allow_if_trusted"` on v39+

**Symptom:** Policy response silently rejected.

**Root cause:** Pexip v39+ changed the valid values. `"allow"` is no longer accepted.

**Fix:** Always use `"allow_if_trusted"` (not `"allow"`).

### 7. Pexip caches failed policy responses for minutes

**Symptom:** After fixing a policy server bug, the same alias still returns 404 for several minutes.

**Root cause:** Pexip caches policy failures to avoid hammering a broken policy server.

**Fix:** Wait 2-3 minutes, or restart the conferencing node. No API to flush the cache.

### 29. `view` has 14 valid values — invalid rejects entire response

**Symptom:** Conference creation fails with 404 and Infinity support log shows "Invalid value for configuration item. Field=view".

**Root cause:** The view value is not in the 14-member valid set.

**Fix:** Always normalize through `_normalize_view()`. See `references/service-config-validation.md` for the full valid set.

### 32. `pin: ""` rejected but `guest_pin: ""` valid for test aliases

**Symptom:** Empty string PIN causes rejection, but empty guest_pin works for some alias types.

**Root cause:** Pexip treats empty string PIN differently from omitted PIN. `pin: ""` is treated as "PIN configured but empty" and rejected.

**Fix:** Omit the `pin` field entirely instead of setting it to empty string.

### 33. `guest_pin` with `allow_guests: false` causes rejection

**Symptom:** Policy response rejected when guest_pin is set but guests are not allowed.

**Root cause:** Pexip treats this as a contradictory configuration.

**Fix:** Only set `guest_pin` when `allow_guests` is `true`.

---

## Participant / Classification Gotchas

### 8. Each `request_token` creates a new Policy Server participant

**Symptom:** Meeting roster shows multiple "Policy Decission Point Server" entries.

**Root cause:** `request_token` always creates a new participant. Without releasing the old one, duplicates accumulate until Pexip's ~120s idle timeout removes them.

**Fix:** Always call `release_token(old_token)` before `request_token()`:
```python
_release_stale_ps_participant(conf_fqdn, alias, old_token)
new_token, err = request_token(conf_fqdn, alias, pin=pin)
```

### 9. Cross-worker classification dedup needs SQLite UNIQUE constraint

**Symptom:** Two Policy Server participants join simultaneously when concurrent IdP users join on different Gunicorn workers.

**Root cause:** Python threading locks (`threading.Lock`) do not work across Gunicorn worker processes.

**Fix:** Use SQLite's `INSERT` with `UNIQUE` constraint as the atomic gate:
```python
try:
    conn.execute("INSERT INTO classified_conferences (alias) VALUES (?)", (alias,))
    return True  # We won the race
except sqlite3.IntegrityError:
    return False  # Another worker already claimed this
```

### 10. Client API tokens expire at ~120s, refresh at 60s

**Symptom:** `set_classification_level` returns 403 after the token expires.

**Root cause:** Client API tokens have a ~120s TTL. Without proactive refresh, the token expires between recalculation events.

**Fix:** Background keepalive thread refreshes every 60s using `refresh_token()` (lightweight, no new participant).

### 12. Policy Server participant must get chair + bypass_lock FIRST

**Symptom:** Policy Server participant stuck in lobby, classification never starts.

**Root cause:** The role assignment logic evaluated classification rules before checking for the PS participant, assigning it "guest" role.

**Fix:** Check `remote_alias in ("Policy Server", "PDP Connectivity Test")` as the very first condition in participant_properties, before any other logic.

### 13. Non-IdP must passthrough `preauthenticated_role` — never hardcode "guest"

**Symptom:** SIP users who entered the host PIN are assigned guest role.

**Root cause:** Hardcoding `preauthenticated_role: "guest"` overrides the PIN-based role Pexip assigned. SIP users who entered the host PIN should get chair.

**Fix:** For non-IdP, non-SIP-endpoint participants, do not set `preauthenticated_role` at all. Let Pexip's PIN-based assignment stand.

### 14. `guest_pin` causes SIP IVR prompt before participant_properties

**Symptom:** SIP callers hear an IVR menu asking for PIN before policy runs.

**Root cause:** When `guest_pin` is set in service_configuration, Pexip's IVR intercepts SIP calls before forwarding to participant_properties. The policy server never sees the participant.

**Fix:** Omit `guest_pin` from service_configuration for conferences that handle SIP participants via policy. Use `preauthenticated_role` in participant_properties instead.

### 15. SIP `local_alias` arrives as `sip:name@domain` — normalize

**Symptom:** Alias prefix matching fails, instance lookup returns None.

**Root cause:** SIP calls include the full URI in `local_alias`. WebRTC calls send bare alias.

**Fix:** Always run `_normalize_alias()` on `local_alias`.

### 18. L1 rejection uses stored `classification_level`, not `min(tracked)`

**Symptom:** Race condition where a participant is admitted despite the meeting being classified above their level.

**Root cause:** Computing `min(tracked_levels)` at rejection time can return a stale value if the previous recalculation hasn't completed yet.

**Fix:** Read `classification_level` from conference state (set during the last successful `set_classification_level` call):
```python
meeting_state = get_conference(alias)
current_level = meeting_state.get("classification_level")
if participant_level < current_level:
    return reject_response()
```

### 22. Client API `request_token` fails 403 on locked+IdP conferences

**Symptom:** Classification fails to start for locked conferences with IdP authentication.

**Root cause:** The Client API `request_token` endpoint requires the conference PIN when the conference is locked, even when the policy server participant should bypass it.

**Fix:** Always pass the PIN when calling `request_token`:
```python
token, err = request_token(conf_fqdn, alias, pin=policy_server_pin)
```

### 23. ADP excluded when `is_policy_server=True`

**Symptom:** SIP endpoints try to join the Policy Server's test call instead of the actual conference.

**Root cause:** ADP entries in the service config cause dial-outs when the Policy Server joins via Client API.

**Fix:** Gate ADP behind `not is_policy_server`:
```python
if sip_rows and not is_policy_server and not is_breakout_room:
    result["automatic_participants"] = [...]
```

### 24. Test aliases skip early classification

**Symptom:** Classification runs on test VMRs (plugintest, macrotest, themetest), wasting Client API tokens.

**Root cause:** The early classification trigger fires for any IdP participant, including test aliases.

**Fix:** Check alias suffix before triggering classification:
```python
is_test = alias.endswith("-macrotest") or alias.endswith("-plugintest") or \
          bool(re.match(r'^.+-themetest\d{3}$', alias))
if not is_test and try_mark_classified(alias):
    # Trigger classification
```

### 25. `__create_keycloak_idp__` sentinel must be filtered

**Symptom:** Pexip receives a sentinel string as the IdP group name.

**Root cause:** The UI uses `__create_keycloak_idp__` as a sentinel value meaning "create IdP during setup." If this value reaches the policy server, it gets passed through to Pexip.

**Fix:**
```python
if idp_group and idp_group != "__create_keycloak_idp__":
    result["host_identity_provider_group"] = idp_group
```

### 26. KC user update must merge attributes, not replace

**Symptom:** Updating one Keycloak user attribute wipes all others.

**Root cause:** The KC Admin API `PUT /users/{id}` replaces the entire attributes dict.

**Fix:** Read existing attributes, merge the new value, then write:
```python
existing = user.get("attributes", {})
existing["avatarBase64"] = [new_value]
kc_request("PUT", f"admin/realms/{realm}/users/{user_id}", json={"attributes": existing})
```

### 28. Classification map format varies (list-of-dicts or flat dict)

**Symptom:** `KeyError` or `TypeError` when looking up classification level.

**Root cause:** Different storage formats in different parts of the system.

**Fix:** Normalize to `{name_lower: int_level}` before use:
```python
if isinstance(class_map_raw, list):
    class_map = {r["rank_name"].lower(): int(r["level"]) for r in class_map_raw}
elif isinstance(class_map_raw, dict):
    class_map = {k.lower(): int(v) for k, v in class_map_raw.items()}
```

---

## Avatar Gotchas

### 11. Avatar MUST be JPEG, exact dimensions, RGB color space

**Symptom:** Participant shows initials instead of avatar photo, no error logged.

**Root cause:** Pexip silently rejects non-JPEG images, wrong dimensions, or RGBA color space. Falls back to initials with no indication.

**Fix:**
```python
img = Image.open(io.BytesIO(raw_bytes))
img = img.convert("RGB")  # Not RGBA
img = img.resize((width, height), Image.LANCZOS)  # Exact dimensions
img.save(buf, format="JPEG", quality=90)  # Not PNG
```

### 27. `enable_avatar_lookup` lives on `policy_server` resource

**Symptom:** Avatar endpoint is never called despite being implemented and reachable.

**Root cause:** The avatar lookup toggle is on the Pexip admin's Policy Server configuration, not on the conference or VMR.

**Fix:** In Pexip admin, navigate to Policy Server configuration and enable `enable_avatar_lookup`.

---

## Event Sink Gotchas

### 16. No `participant_disconnected` on breakout room reorganization

**Symptom:** Stale participants in breakout state after rooms are reorganized via "Edit rooms."

**Root cause:** When a host uses "Edit rooms" to move participants between breakout rooms, Pexip reorganizes them without firing disconnect events for the source room.

**Fix:** Prune stale entries when a new participant joins a breakout room:
```python
# Check if breakout participants are actually back in main VMR
parent_participants = get_participants(parent_alias)
for key, p in breakout_participants.items():
    for pk, pp in parent_participants.items():
        if names_match(p, pp) and pp.get("in_main_vmr", True):
            remove_participant(breakout_alias, key)
            break
```

### 17. Event sink breakout migration must track `admitted=False`

**Symptom:** Classification stays stuck at L6 (highest level) when lower-level participants migrate to breakout.

**Root cause:** Setting `admitted=True` during migration causes the "already admitted?" guard to return early, skipping recalculation. The breakout never sees the lower level.

**Fix:** Always track migrated participants with `admitted=False`:
```python
track_participant(breakout_alias, key, level, name, admitted=False, ...)
# The normal admission flow then marks them as admitted and triggers recalc
```

---

## Operational Gotchas

### 19. `on_completion` is JSON-encoded, not bare alias

**Symptom:** Conference transfer after disconnect fails.

**Root cause:** The `on_completion` field from Pexip is a JSON-encoded string, not a bare alias.

**Fix:** `json.loads(on_completion)` before using as an alias.

### 20. SAML auth preserved across `on_completion` transfers

**Symptom:** Participants are not re-prompted for SAML auth when transferred between conferences.

**Root cause:** This is expected Pexip behavior. SAML authentication state persists across `on_completion` conference transfers.

**Fix:** No fix needed — this is by design. Be aware that classification attributes from the original auth apply to the new conference.

### 21. Check policy server URL on Pexip before debugging

**Symptom:** Policy server code looks correct but Pexip never calls it.

**Root cause:** The policy server URL configured in Pexip Infinity admin points to the wrong server (e.g., a stale ngrok URL).

**Fix:** Always verify the URL first:
1. Pexip admin > External Policy Server > URL
2. Check PDP logs for `service_configuration` requests — if NONE appear, it is a connectivity issue, not policy logic
3. For dev/ngrok setups, the URL changes every tunnel restart

### 30. Conference state in `/tmp/conference_state.db`, not main DB

**Symptom:** Querying the main application database for conference state returns nothing.

**Root cause:** Conference state (tokens, participants, classification levels) is stored in a separate volatile SQLite database to isolate it from persistent configuration.

**Fix:** Use the conference state module's API (`get_conference()`, `get_participants()`) which connects to the correct database.

### 31. Client API `send_message` must use `text/plain`

**Symptom:** Messages sent via Client API are not delivered to webapp3 plugins.

**Root cause:** The Client API message endpoint requires `Content-Type: text/plain` for plugin delivery. JSON content type causes silent delivery failure.

**Fix:** Set Content-Type explicitly when calling the Client API message endpoint.

### 34. `demo_branding.py` helpers use `*args` — kwargs silently break

**Symptom:** `TypeError: tuple index out of range` when calling demo branding helpers.

**Root cause:** The helpers use positional `*args` unpacking internally. Passing keyword arguments creates a tuple that doesn't match the expected positional layout.

**Fix:** Always use positional arguments:
```python
# WRONG
build_demo_branding(theme_name=name, instance_id=iid)

# CORRECT
build_demo_branding(name, iid)
```

---

## Token / Classification Lifecycle Gotchas

### 35. Disconnecting duplicate Policy Server participants causes token cascade

**Symptom:** After disconnecting a duplicate PS participant, a rapid cycle of 403 → new token → new PS → disconnect → 403 repeats until the conference ends.

**Root cause:** Each Client API token is bound to a specific PS participant. Disconnecting that participant invalidates the token. The next API call gets 403, triggers a new token request (creating yet another PS), and if that duplicate is also disconnected, the cycle repeats.

**Fix:** Never disconnect PS participants after token operations. Duplicates are harmless — they occupy no media resources and are automatically cleaned up when the conference ends.

### 36. "Invalid role" 403 after requesting a new Client API token

**Symptom:** `set_classification_level` returns 403 "Invalid role" immediately after obtaining a fresh token.

**Root cause:** A new token creates a new Policy Server participant in the conference. This participant needs ~1-2 seconds to be fully admitted and assigned the chair role. API calls made before admission complete fail with "Invalid role".

**Fix:** Wait 1.5 seconds after requesting a new token before making API calls:
```python
if not was_cached:
    time.sleep(1.5)
```
Use different backoff strategies: 0.5s increments for token errors (transient), 1.5s increments for role errors (PS still joining).

### 37. Breakout return contaminates participant remote_alias

**Symptom:** After participants return from a breakout room, their cached `remote_alias` is overwritten with the conference alias, and `delete_duplicates_by_remote_alias` deletes unrelated participants.

**Root cause:** When returning from breakout, Pexip sets `destination_alias` to the conference alias (the room being joined), not the participant's actual remote address.

**Fix:** Before storing `remote_alias`, check if it matches the conference alias or parent alias (strip `_breakout_` suffix). If it matches, discard it:
```python
normalized_ra = _normalize_alias(remote_alias)
normalized_conf = _normalize_alias(conference_alias)
if normalized_ra == normalized_conf:
    remote_alias = ""  # Contaminated
```

### 38. Conference restart cleanup race

**Symptom:** A conference ends and restarts with the same alias. The cleanup thread from the old conference clears caches that the new conference is actively using.

**Root cause:** Background cleanup threads use `conference_alias` as their key. If a conference restarts before cleanup completes, both the old cleanup thread and the new conference reference the same alias.

**Fix:** Use a SQLite-backed generation counter. Increment on `conference_started`, capture the value, and abort cleanup if the generation has changed:
```python
generation_at_end = get_generation(conference_alias)
# ... in cleanup thread:
if get_generation(conference_alias) != generation_at_end:
    return  # Conference restarted
```

### 39. Event sink service_type field name varies by Pexip version

**Symptom:** Admission detection fails silently — participants are never detected as admitted on certain Pexip versions.

**Root cause:** Some Pexip versions send `service_type` in event sink data, others send `current_service_type`. Code checking only one field name misses the other.

**Fix:** Check both with OR fallback:
```python
service_type = data.get("service_type", "") or data.get("current_service_type", "")
```

### 40. New token request during conference teardown creates ghost participant

**Symptom:** After conference ends, a new Policy Server participant appears briefly in Pexip admin, keeping the conference technically alive.

**Root cause:** Cleanup operations (cache clearing, classification reset) can trigger `get_or_refresh()`, which requests a new token → creates a new PS participant → keeps the conference from fully ending.

**Fix:** Track ending conferences in a set. Block new token requests (but still return cached tokens for cleanup reads):
```python
if conference_alias in _ending_conferences:
    return cached_token  # No new PS during teardown
```
Clear the flag on `conference_started` (new conference) or after cleanup completes.
