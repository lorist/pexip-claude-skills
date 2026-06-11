# Gotchas and Conventions

Read this in parallel with the topic references — it captures the cross-cutting traps.

## Paginated vs bare-list responses

The biggest API-design wart: **the shape of a list response is not consistent**. Some endpoints return a DRF-style paginated dict:

```json
{"count": 123, "next": "...", "previous": "...", "results": [...]}
```

Others return a **bare JSON array** at the top level:

```json
[ {...}, {...} ]
```

The OpenAPI distinguishes them by the response schema name:

- `PaginatedXxxList` defined as `type: object` with `count`, `next`, `previous`, `results` → paginated dict.
- `PaginatedXxxList` defined as `type: array, items: ...` → bare array. (Yes — the name still has "Paginated" even though it isn't.)

Examples of **bare array** responses you'll hit often:

- `GET /calls/`, `GET /call_legs/` (with no pagination params)
- `GET /addressbook/`, `GET /addressbook_group/`, `GET /addressbook_item/`
- `GET /endpoint/`, `GET /endpointtask/`, `GET /endpointbranding/`, `GET /endpointfirmware/`
- `GET /provider/`, `GET /provider/load/`, `GET /provider_statistics/`
- `GET /cluster/`, `GET /customer/`, `GET /customerkey/`, `GET /customer_match/`, `GET /customer_policy/`
- `GET /monitor_*/`, `GET /sensor_settings/`, `GET /themesettings/`
- `GET /ews_credential/`, `GET /ews_calendar/`, `GET /msgraph_*/`, `GET /webex_integrations/`, `GET /cucm_integrations/`
- `GET /debug/*` for fixed-size lists; the dated debug surfaces (`audit_log`, `policy_log`, `external_policy_log`, `pexip_history`, …) **are** paginated dicts.

Examples of **paginated dict** responses:

- `GET /meeting/`, `GET /meeting/in_call/`
- `GET /cospace/?` (the unified read)
- `GET /meeting/{id}/calls/` (`PaginatedCallIncludeLegsList`)
- `GET /debug/audit_log/`, `GET /debug/policy_log/`, `GET /debug/error_log/`, etc.

**Always check the spec for the specific endpoint.** A safe client helper handles both:

```python
def list_all(client, path, params=None):
    body = client.get(path, params=params)
    if isinstance(body, list):
        return body                       # bare array
    items = body.get("results", [])
    while body.get("next"):
        body = client.get_absolute(body["next"])
        items.extend(body.get("results", []))
    return items
```

(The shipped `mividas_client.py` does this.)

## Pagination params

Where pagination *is* used, two flavours appear:

- `limit` + `offset` (most endpoints).
- `page` + `limit` (a few — notably `/meeting/`, `/meeting/in_call/`, `/meeting/{id}/calls/`).

`limit` has different meanings on different endpoints — many default to 20, some to no limit. `GET /cospace/?limit=-1` is "no limit" on that specific endpoint (see the spec's `minimum: -1` on that param).

## CMS vs Pexip parallel resources

The single biggest conceptual trap. **There are two parallel CMS-vs-Pexip write paths for what looks like the same thing.** See [cospaces-meetings-and-calls.md](cospaces-meetings-and-calls.md#cms-vs-pexip-which-endpoint-to-use).

| Concept | CMS endpoint | Pexip endpoint | Unified read |
|---|---|---|---|
| Meeting space | `/cospace-acano/` | `/cospace-pexip/` | `/cospace/` (read only) |
| Member / user | `/user-acano/` | `/user-pexip/` | `/user/` |

The unified `/cospace/` and `/user/` endpoints **do not support create**. They aggregate reads across both backends. Trying to POST to them returns 405.

## Deprecated aliases

The CoSpace / Conference schemas carry historical fields kept for backward compatibility. New code should use the canonical names:

| Deprecated | Use instead | Where |
|---|---|---|
| `password` (CoSpace) | `passcode` | `CoSpaceBase`, `CoSpace`, etc. |
| `moderator_password` | `moderator_passcode` | same |
| `lobby_pin` | `moderator_passcode` | same |
| `title` | `name` | `CoSpaceBase` |
| `cospace` (on `CoSpace` itself) | `id` | `CoSpace` |
| `callId` / `callLegProfile` / `regenerateSecret` (`CoSpaceAccessMethod`) | `call_id` / `call_leg_profile` / `regenerate_secret` | snake_case |

Reads typically return *both* — write the canonical version, ignore the alias.

## Enum cheat sheet

Easy to mis-look-up, so collected here:

**Endpoint manufacturer (`ManufacturerEnum`)** — `10` CISCO_CE · `11` CISCO_WEBEX · `30` TEAMS_MTR · `90` OTHER.

**Endpoint status (`StatusA6eEnum`)** — `-2` CONNECTION_ERROR · `-1` AUTH_ERROR · `0` OFFLINE · `1` UNKNOWN · `10` ONLINE · `20` IN_CALL.

**Endpoint connection type (`ConnectionTypeEnum`)** — `-10` INCOMING · `0` PASSIVE · `1` DIRECT · `2` PROXY.

**EndpointTask status (`Status9b5Enum`)** — `-10` ERROR · `-1` CANCELLED · `0` PENDING · `5` QUEUED · `10` COMPLETED. Terminal = `{-10, -1, 10}`.

**Provider subtype (`SubtypeEnum`)** — `1` CMS Call Bridge · `2` Pexip Management Node · `4` CMS Service Node · `5` Reserved · `6` Expressway · `7` Cisco CUCM.

**Alert severity (`SeverityEnum`)** — `50` CRITICAL · `40` ERROR · `30` WARNING · `20` INFO · `10` DEBUG · `0` NOTSET. (Same shape as Python's `logging` module.)

**Call protocol (`CallStatisticsProtocolEnum`)** — `0` SIP · `1` H323 · `2` CMS · `3` Lync · `4` Cluster · `5` Stream/recording · `6` Lync SubConnection · `7` WebRTC · `8` Teams · `9` GMS (Google Meet) · `10` Spark.

**StatisticsServer type** — `0` CMS · `1` VCS · `2` Endpoints · `3` Combine · `4` Pexip.

**Policy limit (`LimitEnum`)** — `0` OK · `10` Soft Limit · `20` Hard Limit. **Policy action (`ExternalPolicyLogActionEnum`)** — `0` Ignore · `5` Log · `20` Audio-only · `30` SD · `35` 720p · `100` Reject.

**OAuthCredential type** — `0` EWS · `10` Graph · `11` Graph (Teams Devices) · `20` Webex Device · `21` Webex Meeting · `22` Webex Meeting G2G.

**Meeting status (`StatusBccEnum`)** — `future` · `ongoing` · `ended` · `ended_deprovisioned` · `cancelled` · `superseded` · `placeholder` · `unknown`.

## Mixed-type fields in responses

A few payload fields are inconsistently typed:

- `EndpointStatus.has_direct_connection`, `EndpointStatus.uptime`, `EndpointStatus.status`, `EndpointStatus.muted`, `EndpointStatus.volume` mix strings and bools — `has_direct_connection` is `"True"` / `"False"` strings, `muted` is a real bool. Don't assume.
- Some `EndpointStatus.warnings[]` entries are strings; some are richer dicts depending on the endpoint type.
- `EndpointStatus.diagnostics[]` is a list of dicts whose keys vary by Cisco vs Webex vs Teams.

When parsing endpoint status, treat values defensively (`bool(str(v).lower() == "true")` style).

## Timestamps

All datetimes are ISO-8601 with explicit timezone (typically `Z`). Empty / null is allowed on most "ts_*" fields. Required `ts_start` / `ts_stop` filters on statistics endpoints **must** include timezone — naive datetimes are rejected.

`ts_unbooked`, `ts_completed`, `ts_acknowledged`, `ts_raised`, `ts_lowered` are nullable — null means "didn't happen".

## Destructive endpoints to be careful with

| Endpoint | Effect |
|---|---|
| `DELETE /cospace-acano/{id}/` | Removes a CMS Meeting Space. |
| `DELETE /cospace-pexip/{id}/` | Removes a Pexip Conference. |
| `DELETE /calls/{id}/` | Drops an active call (every participant disconnected). |
| `DELETE /call_legs/{id}/` | Drops one participant. |
| `DELETE /endpoint/{id}/` | Removes an endpoint and its history. |
| `POST /endpoint/bulk_delete/` | Bulk-delete endpoints by ID. |
| `POST /cospace/bulk_delete/` | Bulk-delete cospaces. |
| `POST /cospace-acano/{id}/members/bulk_delete/` | Bulk-delete members. |
| `POST /purge_queues/?all_queues=true` | Purge every background queue. |
| `POST /provider/{id}/clean_unused_profiles/` | Delete CMS Call Profile / Call Leg Profile / Call Branding Profile objects that aren't referenced. **Has a `dry_run` flag — use it first.** |
| `POST /provider/{id}/remove_duplicates/` | Bulk-delete cospaces/users with duplicate URIs. |
| `POST /endpoint_attribute/remove_namespace/` | Drop every attribute in a namespace. |
| `DELETE /policy_authorization_override/{id}/` | Removes a standing security policy — pay attention. |

Always confirm before running destructive operations against a shared installation. Many of these resources have `dry_run` flags (`/provider/{id}/clean_unused_profiles/`, `/provider/{id}/rematch_deprovisioned_meetings/`, `/policy_rule/sync/`, sometimes calendar sync) — use them.

## Field naming quirks

- snake_case for almost everything (Django REST Framework default).
- A few camelCase holdovers on `CoSpaceAccessMethod`: `callId`, `callLegProfile`, `regenerateSecret` — read-only deprecated aliases of `call_id`, `call_leg_profile`, `regenerate_secret`.
- Boolean filters in query strings accept `true`/`false` (lowercase). `True`/`False` is not accepted on some endpoints.

## Auth scheme in the spec is misleading

`securitySchemes.oauth2` is the **end-user Portal** auth, not the management API. The actual auth for `/json-api/v1/` is HTTP Basic. See [auth-and-multitenancy.md](auth-and-multitenancy.md#authentication).

## Multi-language strings

Some endpoints return localised strings (e.g. some `CallStatisticsSettings.choices` labels are Swedish: "Slumpa", "Nästa i nummerfÃ¶ljd"). These come from Mividas's UI translations. Don't try to map them programmatically — match on the underlying enum value (e.g. `"random"`, `"increase"`), not the label.

The label encoding can be mojibake (`NÃ¤sta` for "Nästa") in some responses depending on installation locale — match on the value field rather than `label`.

## `customer` field in payloads is usually read-only

Most write payloads have a `customer` field — it's almost always read-only and inferred from the `X-Mividas-Customer` header. Don't try to override it.

## Provider `subtype` vs Cluster `type`

A common confusion when listing infrastructure:

- `Cluster.type` is a string (`"acano"` / `"pexip"` / `"vcs"`).
- `Provider.subtype` is an integer (`1` CMS Call Bridge / `2` Pexip MgrNode / etc).

A CMS `Cluster` may contain Call Bridge `Provider`s (subtype 1) and Service Node `Provider`s (subtype 4) — match on subtype, not on cluster type alone.
