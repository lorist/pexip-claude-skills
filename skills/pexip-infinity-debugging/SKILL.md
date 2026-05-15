---
name: pexip-infinity-debugging
description: >
  Debugging playbook for Pexip Infinity deployments. Problem-oriented
  decision trees mapping symptoms to log sources, search terms, error
  patterns, and fixes. Covers policy server debugging (silent 404,
  response validation, PIN rejection), event sink troubleshooting
  (delivery failures, missing events, location coverage), classification
  state issues (stuck levels, Client API 403, token lifecycle),
  authentication problems (IdP/SAML, "Not authenticated", Keycloak),
  and infrastructure debugging (config replication, ngrok, licensing).
  Use when: Pexip calls are failing, policy responses are ignored,
  event sink events are missing, classification is stuck, participants
  can't authenticate, or any Pexip Infinity system is misbehaving.
  Also triggers for "Not authenticated", "didn't match any Conference",
  "policy error", "event sink not working", "classification stuck",
  "404 on join", "Pexip logs", "support log", "developer log",
  "debug Pexip", and "why is my call failing".
---

# Pexip Infinity Debugging Playbook

This skill is a problem-oriented debugging guide for live Pexip Infinity systems.
Start with the symptom, follow the decision tree to the right log source and search
term. For post-mortem analysis of downloaded log files, use `pexip-call-rca` instead.

> **Sourcing:** every decision tree, search term, and fix below comes from
> production debugging sessions on Pexip Infinity v39-v40b2 with PDP policy
> servers, event sinks, and classification systems. Patterns marked
> **(field-tested)** were hit and resolved on live systems. Patterns marked
> **(common pattern)** are standard Pexip behavior confirmed through documentation
> and repeated observation.

---

## Master Decision Tree

| Symptom | Go to |
|---|---|
| Policy response ignored / "Alias didn't match" | [S1 Policy Debugging](#s1-policy-server-debugging) |
| Event sink not delivering events | [S2 Event Sink](#s2-event-sink-debugging) |
| Classification level stuck or wrong | [S3 Classification](#s3-classification-debugging) |
| "Not authenticated" or participant can't join | [S4 Authentication](#s4-authentication-debugging) |
| SIP or WebRTC calls failing | [S5 Call Failures](#s5-call-failure-quick-checks) |
| Config changes not taking effect | [S6 Infrastructure](#s6-infrastructure--timing) |
| Need to access Infinity logs | `references/log-access-and-search.md` |
| Looking for a specific error message | `references/common-error-messages.md` |

---

## S1: Policy Server Debugging

For the external policy protocol format, see `pexip-external-policy`.
For implementation patterns, see `pexip-policy-server`.
Expanded decision trees with full examples: `references/policy-debugging.md`.

### "Alias didn't match any Conference or Gateway rule"

**Check first: Is the external policy server URL correct on Pexip?** **(field-tested)**
- Fetch: `GET /api/admin/configuration/v1/policy_server/` on Pexip Management API
- Verify the URL points to the correct PDP instance (not a stale ngrok URL)
- **Stale ngrok URL is the #1 cause of this error** — confirmed across dozens of incidents
- If URL is correct, check PDP logs for incoming `service_configuration` requests
- If ZERO requests appear in PDP logs, it is a connectivity issue — not a policy logic problem
- Check that conferencing nodes can reach the policy URL (firewall rules, TLS)

**Check second: Is the policy response valid JSON?** **(field-tested)**
- Search support log: `q=externalpolicy`
- Common causes of silent rejection:
  - `allow_guests: true` without a `pin` field (Pexip returns silent 404 to the caller)
  - Empty string PIN (`""`) — treated as invalid
  - `guest_pin` set with `allow_guests: false` — Pexip rejects the entire config
  - PINs of different lengths — both must match length or both append `#`
- **Pexip caches FAILED policy responses** for several minutes — you may need to wait after fixing

**Check third: Is the response format correct?** **(common pattern)**
- Must have `"action": "continue"` in the envelope
- Must have `service_type`, `name`, `local_alias` in the result object
- `view` must be one of the 14 valid Pexip layout values — invalid view silently rejects the entire response
- Valid views: `one_main_zero_pips`, `one_main_seven_pips`, `one_main_twentyone_pips`, `two_mains_twentyone_pips`, `one_main_thirtythree_pips`, `four_mains_zero_pips`, `nine_mains_zero_pips`, `sixteen_mains_zero_pips`, `twentyfive_mains_zero_pips`, `five_mains_seven_pips` (Adaptive Composition), `one_main_twelve_pips`, `four_mains_eight_pips`, `two_mains_zero_pips`, `three_mains_zero_pips`

### Policy server not receiving requests

1. Check PDP logs for any `/policy/v1/service/configuration` hits
2. If none → check policy server URL on Pexip (stale ngrok?) **(field-tested)**
3. If URL correct → check conferencing node can reach PDP (firewall, TLS cert issues)
4. Test connectivity from outside: `curl -k https://<pdp-url>/rbac-idp/policy/v1/service/configuration`
5. Check that the policy server resource is enabled in Pexip Management API
6. Check policy server location assignments — policy server must be assigned to the location(s) where calls land

### PIN validation failures

- Search support log: `q=Invalid+service+configuration` **(field-tested)**
- PIN rules are strict and non-obvious — see full truth table in `references/policy-debugging.md`
- Quick fix: append `#` to BOTH `pin` and `guest_pin` if their lengths differ **(field-tested)**
- `pin` must be set when `allow_guests: true` — otherwise silent rejection **(field-tested)**
- `pin` must not equal `guest_pin` — Infinity rejects with logged error **(field-tested)**

### Participant rejection not working

- Verify `participant_properties` response has `"reject": true` in the result
- The result must be inside an `"action": "continue"` envelope **(field-tested)**
- **NEVER** use `_json_ok()` for reject responses — `action: "continue"` from `_json_ok` overrides the rejection **(field-tested)**
- Search support log: `q=participant_properties` to verify Pexip received the response
- Check that the policy server is assigned to handle `participant_properties` requests (not just `service_configuration`)

---

## S2: Event Sink Debugging

For event sink protocol and payload details, see `pexip-event-sink`.
Expanded troubleshooting: `references/event-sink-debugging.md`.

### Events not being delivered

1. Verify event sink exists: `GET /api/admin/configuration/v1/event_sink/` **(common pattern)**
2. Verify event sink URL is reachable from Pexip conferencing nodes
3. **Location matters:** Event sink location must contain TRANSCODING nodes — proxy-only locations reject event sinks **(field-tested)**
4. Restart the event sink instance from Pexip admin if stuck — `DELETE` existing + `POST` new one **(field-tested)**
5. Use ngrok inspector (`http://127.0.0.1:4040`) to verify events are arriving during dev **(field-tested)**
6. Check that the event sink resource ID is correct — IDs change on delete+recreate, always look up by name **(field-tested)**

### Missing specific event types

- `participant_connected` fires for every participant including ADP SIP legs **(common pattern)**
- `participant_updated` fires on state changes: admitted from lobby, role change, media change **(common pattern)**
- `conference_ended` fires once when the last participant leaves **(common pattern)**
- `participant_disconnected` fires per participant — includes `disconnect_reason`
- **Event sink delivery is unreliable for timing-critical operations** — trigger recalculation directly on `/admit` instead of waiting for events **(field-tested)**

### Debounce and duplicate events

- Pexip sends `participant_connected` + `participant_updated` pairs for a single admission **(common pattern)**
- Use debounce key: `conference_alias:participant_uuid` with 5-30s TTL
- `conference_ended` can fire multiple times if participants rejoin rapidly — use idempotent handlers
- Clear debounce state on `conference_ended` to prevent stale entries across conference cycles **(field-tested)**

---

## S3: Classification Debugging

For classification implementation patterns, see `pexip-policy-server`.
Expanded debugging steps: `references/classification-debugging.md`.

### Classification level stuck

1. Check PDP debug state: `/debug/states` endpoint shows current level per conference **(field-tested)**
2. **PDP debug state current_level does NOT equal actual Infinity classification** — always verify visually in the meeting **(field-tested)**
3. Check Client API token is valid — tokens expire at ~120s **(field-tested)**
4. Check event sink is delivering `participant_updated` events (admission triggers recalculation)
5. Check `_refresh_token_if_needed()` is working — it should proactively refresh at 90s **(field-tested)**
6. Check `conference_state.db` (at `/tmp/conference_state.db`) for stale entries from previous test runs **(field-tested)**

### Client API returning 403

- **"Invalid role"** → new token's Policy Server participant not yet admitted as chair. Wait 1.5s after token request. **(field-tested)**
- **"Invalid token"** → token expired or was invalidated by Pexip. Refresh or request a new one. **(common pattern)**
- **Locked + IdP conference** → Client API rejects unauthenticated tokens. Policy Server must be chair with `bypass_lock`. **(field-tested)**
- `request_token` itself can fail with 403 on locked+IdP conferences — always use stored Policy Server token **(field-tested)**

### All participants showing same level

- Check IdP title attribute is being sent in the SAML assertion **(field-tested)**
- Check `classification_map` maps the title value to the correct level
- Check `participant_properties` response includes `classification_level` in `overlay_text`
- Check Keycloak v26+ — custom attributes must be defined in User Profile schema BEFORE API use; silently ignores unmapped attributes **(field-tested)**

### L1 rejection not triggering

- `l1_rejection_threshold=N` means levels 1 through N are rejected, not just L1 **(field-tested)**
- Check the rejection logic uses stored `classification_level`, not `min(tracked_participants)` **(field-tested)**
- Search support log: `q=reject` to verify rejection responses are being sent
- Check that the conference actually has participants at different levels

---

## S4: Authentication Debugging

For SAML attribute mapping and IdP configuration, see `references/authentication-debugging.md`.

### "Not authenticated" error

1. **Check policy server URL first** — stale ngrok is the #1 cause **(field-tested)**
2. Check IdP group is configured on the VMR or in the policy response
3. Check `non_idp_participants` is `"allow_if_trusted"` not `"allow"` on Pexip v39+ **(field-tested)**
4. Check Keycloak SAML client has correct redirect URIs
5. Check that the conferencing FQDN is accessible from the browser (WebRTC) or from the SIP endpoint

### SAML attributes not appearing in participant_properties

- Keycloak v26+ requires custom attributes defined in User Profile schema BEFORE API use — **silently ignores** unmapped attributes **(field-tested)**
- Check mapper chain: `title` attribute in KC User Profile → SAML `title` attribute mapper → `title` in IdP custom attributes on Pexip
- IdP custom attributes MUST be registered on the Identity Provider in Management API: `GET /api/admin/configuration/v1/identity_provider_attribute/` **(field-tested)**
- Pexip silently ignores unregistered IdP attributes — no error in any log **(field-tested)**

### Keycloak popup login failures

- Pexip webapp opens Keycloak login in a popup window (not navigation) — popup blockers can kill it silently **(field-tested)**
- SAML `role_list` mapper must set `single=true` to avoid duplicate Role attribute error **(field-tested)**
- KC SAML client needs BOTH hostname variants in redirectUris: `localhost` AND `127.0.0.1` **(field-tested)**
- Keycloak redirect URI wildcards only work in the path segment, not in hostname **(field-tested)**

### OAuth2 token endpoint failures

- JWT `aud` claim must use the internal management FQDN (`management_vm.name`), NOT the external CNAME **(field-tested)**
- Error message is generic `"invalid_client: invalid_claim"` with no detail about which claim **(field-tested)**
- `oauth2_client` has TWO IDs: alphanumeric `client_id` (used in JWT) and integer `id` (used in API URLs) — mixing them causes DELETE 404 **(field-tested)**

---

## S5: Call Failure Quick Checks

For detailed call RCA from downloaded log files, use `pexip-call-rca`.
These are the first checks to run on a live system.

### SIP calls failing

- Search developer log: `q=sip` for SIP signaling traces **(common pattern)**
- `488 Not Acceptable Here` = codec mismatch between endpoints **(common pattern)**
- ADP not dialing = missing `local_alias` in service config AND in each ADP entry **(field-tested)**
- SIP aliases need `sip:` prefix stripping and `@domain` stripping for alias matching **(field-tested)**
- Service config must NOT include `automatic_participants` when `is_policy_server=True` — otherwise ADP gets dialed during connectivity test **(field-tested)**

### WebRTC calls failing

- Search support log: `q=ice` for ICE candidate gathering issues **(common pattern)**
- Check TURN server accessibility from conferencing nodes
- Embedded React iframe (`@pexip/infinity`) does NOT support webapp3 plugins — use "Join with Browser" **(field-tested)**
- Check browser console for CSP violations — iframe camera needs `frame-src`, `X-Frame-Options`, `Permissions-Policy` alignment **(field-tested)**

### Call connects but no media

- Search developer log: `q=media` or `q=rtp`
- Check firewall rules allow UDP on media ports (default range: 40000-49999)
- Check that conferencing node is not at license capacity — `License-Type="None"` on disconnect is normal for API legs **(common pattern)**

---

## S6: Infrastructure & Timing

### Changes not taking effect

- **Config replication:** Infinity takes ~30s to replicate config changes across the cluster (fires only when URL changes, not on content changes at the same URL) **(field-tested)**
- **Policy cache:** Pexip caches FAILED policy responses for several minutes. Wait or create a new conference to test. **(field-tested)**
- **Branding cache:** Clear Infinity API cache after branding mutations (clone/install/delete). Stale UUIDs cause 404. **(field-tested)**
- **Server not running:** After Python edits, Flask must be restarted manually (`use_reloader=False`). Check `docker logs --tail 10 pdp-dev` for import errors. **(field-tested)**
- **Theme replication:** Branding theme changes require ~30s replication. Downloading immediately after upload may return the old version.

### ngrok issues

- ngrok tunnel down → all external policy and event sink calls fail **(field-tested)**
- Check active tunnels: `curl http://127.0.0.1:4040/api/tunnels`
- After ngrok restart, update BOTH: policy server URL on Pexip AND event sink URL **(field-tested)**
- Free tier blocks TCP tunnels; HTTP tunnels are fine **(field-tested)**
- Infinity can take 30s+ to pick up the new URL due to config replication

### Licensing

- Search support log: `q=license` for license exhaustion events **(common pattern)**
- `License-Type="None"` on participant disconnect is normal for API-created legs — do not flag **(common pattern)**
- License exhaustion causes new calls to fail with no clear error to the caller

---

## S7: Log Search Quick Reference

| Problem | Log type | Search term |
|---|---|---|
| Policy response rejected | Support | `externalpolicy` |
| Service config invalid | Support | `Invalid service configuration` |
| Participant join failure | Support | `participant` |
| SIP signaling traces | Developer | `sip` |
| Event sink delivery | Support | `event_sink` or `eventsink` |
| ICE / media failures | Support | `ice` |
| License issues | Support | `license` |
| Config changes | Administrator | `configuration` |
| Authentication failures | Support | `authentication` or `idp` |
| Alias matching failures | Support | `Alias didn't match` |
| PIN validation | Support | `Invalid service configuration` |
| Participant rejection | Support | `reject` |
| TURN issues | Support | `turn` |
| TLS / certificate | Support | `tls` or `certificate` |

For detailed log access procedures, see `references/log-access-and-search.md`.

---

## Reference Index

| Reference file | Contents |
|---|---|
| `references/log-access-and-search.md` | Log types, Django admin access, search syntax, download, HTML parsing, log level config |
| `references/policy-debugging.md` | Full decision trees, PIN truth table, response validation checklist, `_json_ok` trap |
| `references/event-sink-debugging.md` | Configuration verification, location requirements, event type reference, timing, polling fallback |
| `references/classification-debugging.md` | Token lifecycle, cross-worker dedup, level calculation chain, debug endpoints, timing |
| `references/authentication-debugging.md` | SAML chain, KC User Profile schema, IdP attribute registration, OAuth2 JWT aud, certificates |
| `references/common-error-messages.md` | 25+ error messages with log source, cause, and fix |

---

## When NOT to Use This Skill

| Topic | Use instead |
|---|---|
| Post-mortem RCA from downloaded log files | `pexip-call-rca` |
| External policy protocol format (request/response fields) | `pexip-external-policy` |
| Policy server implementation patterns | `pexip-policy-server` |
| Management API endpoint reference | `pexip-management-api` |
| Webapp3 plugin development issues | `pexip-webapp3-plugin` |
| Event sink payload schema and receiver design | `pexip-event-sink` |
| Client API token management and calls | `pexip-client-api` |
