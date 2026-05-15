# Common Error Messages — Lookup Reference

Quick lookup table mapping Pexip Infinity error messages to causes and fixes.
Sorted by where the error is typically seen.

---

## Support Log Errors

| Error message | Cause | Fix |
|---|---|---|
| `Alias didn't match any Conference or Gateway rule` | Policy server unreachable, response invalid, or no policy server configured | Check policy server URL (stale ngrok?), validate response JSON format, verify policy server assigned to location **(field-tested)** |
| `Invalid service configuration` | PIN validation rules violated in policy response | Check PIN truth table: `pin` required when `allow_guests=true`, PINs must match length, `pin != guest_pin` **(field-tested)** |
| `ExternalPolicy: Error contacting policy server` | Pexip cannot reach the policy server URL | Check connectivity: firewall, DNS, TLS cert, ngrok tunnel status **(field-tested)** |
| `ExternalPolicy: Invalid response` | Policy response is not valid JSON or missing required fields | Validate response has `action`, `status`, `result` with `service_type`, `name`, `local_alias` |
| `ExternalPolicy: Timeout` | Policy server took too long to respond (default: 5s) | Optimize policy server response time; check for blocking calls in request handler |
| `Neither conference nor gateway found` | Client-facing version of "Alias didn't match" | Same fixes as "Alias didn't match" above |
| `Not authenticated` | Participant failed IdP authentication or IdP not configured correctly | Check IdP group config, `non_idp_participants` setting, Keycloak SAML client setup **(field-tested)** |
| `Authentication failed` | Credentials rejected during PIN entry or API auth | Check PIN values, Basic Auth credentials, token validity |
| `Conference is locked` | Participant tried to join a locked conference without bypass | Check `bypass_lock` in participant_properties response; Policy Server needs chair + bypass_lock **(field-tested)** |
| `License capacity exceeded` | All Pexip licenses in use | Wait for licenses to free up; check for leaked conferences consuming licenses |
| `event_sink delivery failed` | Event sink URL unreachable from conferencing node | Check URL, firewall, TLS; restart event sink if stuck **(field-tested)** |
| `Invalid PIN` | Participant entered wrong PIN | Verify PIN values in service_configuration response match expectations |
| `Maximum participants reached` | Conference hit its participant limit | Check `max_callrate_in` / `max_callrate_out` in service config |

---

## Client API Errors (HTTP 403)

| Error message | Cause | Fix |
|---|---|---|
| `Invalid role` | Token's participant does not have chair role yet | Wait 1.5s after token request before using; ensure `preauthenticated_role=chair` in service config **(field-tested)** |
| `Invalid token` | Token expired (>120s) or was invalidated | Refresh token or request new one; check `token_time` age **(field-tested)** |
| `Forbidden` (generic) | Token invalid for this operation | Check token was issued for correct conference; verify participant is still connected |
| `Not found` | Conference no longer exists or wrong conference reference | Check conference is still active; verify conference ID/alias |

---

## Client-Side Errors (Browser / WebRTC)

| Error message | Cause | Fix |
|---|---|---|
| `404` on join attempt | Policy response invalid (same as "Alias didn't match") | Check policy server URL and response format **(field-tested)** |
| `ICE connection failed` | TURN/STUN server unreachable or firewall blocking UDP | Check TURN server config, open UDP ports 40000-49999 |
| `Camera/microphone permission denied` | Browser permissions or CSP blocking | Check iframe `allow` attribute for `camera; microphone`; check `Permissions-Policy` header **(field-tested)** |
| `Popup blocked` | Keycloak login popup blocked by browser | Disable popup blocker for the conferencing domain **(field-tested)** |
| `Mixed content blocked` | HTTP page trying to load HTTPS resource (or vice versa) | Use HTTPS everywhere; ngrok provides HTTPS for local dev **(field-tested)** |

---

## OAuth2 Token Endpoint Errors

| Error message | Cause | Fix |
|---|---|---|
| `invalid_client: invalid_claim` | JWT `aud` doesn't match internal management FQDN | Use `management_vm.name` (internal), not external CNAME **(field-tested)** |
| `invalid_client: unknown client` | `client_id` not registered on Pexip | Create oauth2_client via Management API |
| `invalid_grant` | JWT assertion malformed, wrong algorithm, or expired | Check ES256 signing, `exp`/`iat` claims, key pair |
| `invalid_scope` | Requested scope not allowed for this client | Check client's allowed scopes in oauth2_client config |

---

## Management API Errors

| Error message | Cause | Fix |
|---|---|---|
| `401 Unauthorized` | Bad Basic Auth credentials | Check username/password; update `api_password` in PDP if rotated **(field-tested)** |
| `404 Not Found` on DELETE | Using wrong ID type for oauth2_client (alphanumeric vs integer) | Use integer `id` for API URLs, not alphanumeric `client_id` **(field-tested)** |
| `400 Bad Request` on branding upload | Empty or malformed ZIP file | Clone default branding instead of uploading blank ZIP **(field-tested)** |
| `409 Conflict` | Resource already exists with that name/alias | Check for existing resource; delete or update instead of create |
| `500 Internal Server Error` | Server-side error on Pexip | Check administrator log for details; may be a bug or resource issue |

---

## Pexip Policy Server (PDP) Errors

| Error message | Cause | Fix |
|---|---|---|
| `Theme upload needs demo_id` | Save-chain step ran before demo was created | Reorder chain: steps needing `demo_id` must run AFTER `/demos` POST **(field-tested)** |
| `tuple index out of range` in demo_branding | Using kwargs instead of positional args | `demo_branding.py` helpers use `*args` unpacking; pass positional args **(field-tested)** |
| `Classification level stuck` | Client API token expired or event sink not delivering | Check token age, event sink delivery, force recalculation via `/admit` **(field-tested)** |
| `CSRF token missing` | JS fetch POST without X-CSRFToken header | Use `window.PDP.api()` (adds CSRF automatically) or add `X-CSRFToken` header from `<meta name="csrf-token">` **(field-tested)** |

---

## SIP-Specific Errors

| Error message | Cause | Fix |
|---|---|---|
| `488 Not Acceptable Here` | Codec mismatch between endpoints | Check supported codecs on both sides; add common codec **(common pattern)** |
| `403 Forbidden` | Call rejected by policy or ACL | Check participant_properties for reject; check allow list |
| `408 Request Timeout` | Remote endpoint not responding | Check endpoint reachability, DNS, firewall |
| `503 Service Unavailable` | Pexip node overloaded or not ready | Check node health, license capacity |
| ADP not dialing (no error) | Missing `local_alias` in ADP entry | `local_alias` required in service config AND in each `automatic_participants` entry **(field-tested)** |

---

## Keycloak-Specific Errors

| Error message | Cause | Fix |
|---|---|---|
| `Duplicate Role attribute` | SAML role_list mapper sending multi-valued attribute | Set `single=true` on role_list mapper **(field-tested)** |
| `Invalid redirect_uri` | Redirect URI not in Keycloak client's allowed list | Add exact URI; wildcards only work in path, not hostname **(field-tested)** |
| `User not found` | Attribute set via API but not in User Profile schema (KC v26+) | Add attribute to User Profile schema first **(field-tested)** |
| `403` on Keycloak admin API | IP not in admin allowlist or token expired | Check admin API access rules; refresh admin token |

---

## Infrastructure Errors

| Error message | Cause | Fix |
|---|---|---|
| `Connection refused` on policy URL | PDP server not running | Restart Flask: `lsof -ti:5555 \| xargs kill -9; python3 run-local.py &` **(field-tested)** |
| `ERR_NGROK_3200` | ngrok tunnel expired (free tier 2h limit) | Restart ngrok; update policy server URL and event sink URL on Pexip **(field-tested)** |
| `ImportError` in docker logs | Python file has syntax/import error after edit | Check `docker logs --tail 20 pdp-dev` for the specific error; fix and restart **(field-tested)** |
| `Config replication timeout` | Pexip cluster nodes not syncing | Wait 30s+ for replication; if persistent, check node health **(common pattern)** |
| `TLS handshake failed` | Self-signed cert rejected or cert chain incomplete | Use `verify=False` for self-signed Pexip certs; check intermediate CA certs **(field-tested)** |
| `DNS resolution failed` | Conferencing node cannot resolve policy/event sink hostname | Check DNS config on Pexip nodes; use IP address as workaround |

---

## Event Sink Delivery Errors

| Error message | Cause | Fix |
|---|---|---|
| `event_sink: connection refused` | Receiver not running or firewall blocking | Start receiver; check firewall rules from conferencing node network |
| `event_sink: timeout` | Receiver too slow to respond (must be <5s) | ACK immediately with 200, process async **(common pattern)** |
| `event_sink: SSL error` | TLS certificate issue on receiver | Check cert validity; use HTTP for dev (ngrok handles TLS) |
| No error (events simply missing) | Event sink assigned to proxy-only location | Reassign to location with transcoding nodes **(field-tested)** |
| Events stop after working | ngrok tunnel expired or event sink stuck | Restart ngrok + update URL, or DELETE+POST event sink **(field-tested)** |

---

## Branding and Theme Errors

| Error message | Cause | Fix |
|---|---|---|
| `400` on branding upload | Empty or malformed ZIP file | Clone default branding instead of creating blank; validate ZIP structure **(field-tested)** |
| `404` on branding download | Stale UUID after branding mutation | Clear Infinity API cache after clone/install/delete operations **(field-tested)** |
| `Branding not found` | Branding was deleted but references remain | Check for stale `source_uuid` references; update or remove **(field-tested)** |
| Theme appears old after upload | Branding replication lag (~30s) | Wait for replication; re-download to verify **(common pattern)** |

---

## Conference State Errors

| Error message | Cause | Fix |
|---|---|---|
| `Conference not found` in debug state | Conference ended but state not cleaned up | Clear stale entries from `conference_state.db`; `conference_ended` event may have been missed **(field-tested)** |
| `set_classification_level failed` (silent) | Client API call failed but PDP didn't log clearly | Check PDP debug state vs visual meeting level; force recalculation via `/admit` **(field-tested)** |
| Duplicate participant entries | Multiple event sink events for same admission | Debounce with `conference_alias:participant_uuid` key **(field-tested)** |
| `waiting_room` event for SIP ADP | ADP participant gets `service_type=conference` before lobby | Must reverse admission on `waiting_room` event; SIP ADP timing differs from WebRTC **(field-tested)** |
