---
name: mividas-core-rooms
description: Expert knowledge for building, debugging, and operating against the **Mividas Core + Rooms** REST API — the third-party management platform that sits above Pexip Infinity, Cisco Meeting Server (CMS), VCS/Expressway, and individual video endpoints (Cisco CE, Cisco Webex Devices, Microsoft Teams Rooms) and exposes a unified booking, call-control, endpoint-provisioning, statistics, monitoring, and policy API at `/json-api/v1/`. Use this skill whenever the user is writing code, scripts, or integrations against a Mividas host, working with HTTP Basic Auth + the `X-Mividas-Customer` multi-tenant header, the parallel `/cospace-acano/` (CMS) vs `/cospace-pexip/` (Pexip) vs unified `/cospace/` write/read split, the `/calls/...` + `/call_legs/...` live-call control surface (lock, mute, layout, send-notice, set-importance, send-DTMF, move-to-call, dial-out), the endpoint provisioning task queue (`/endpoint/provision/` → `/endpointtask/?provision=<id>` poll loop), call/room/meeting/provider statistics (`/call_statistics/`, `/room_statistics/`, `/meeting_statistics/`, `/provider_statistics/`), Mividas-managed Pexip policy authorization (time-limited `/policy_authorization/`, predetermined `/policy_authorization_override/`), Pexip Call Routing Rule sync via `/policy_rule/`, license/participant policy reports (`/policy/report/`), endpoint/MCU alerts (`/monitor_endpoint/`, `/monitor_mcu/`, `/monitor_action/`, `/monitor_user_rule/`), address-book sync from external sources (CMS users/spaces, Pexip spaces, VCS, TMS, Seevia, CSV/Excel, manual links, LDAP), calendar integrations (EWS, MS Graph, Webex Devices, CUCM), or the `/debug/...` log surfaces (CDR, audit, error, trace, policy log, Pexip event sink). Also triggers for questions about list-shape variance across endpoints (DRF `{count, next, previous, results}` vs bare array), provider subtype semantics (CMS Call Bridge vs CMS Service Node vs Pexip Management Node vs Expressway vs CUCM), Mividas Rooms endpoint manufacturers (Cisco CE, Cisco Webex, Teams MTR, Other), status codes (-2 CONNECTION_ERROR, -1 AUTH_ERROR, 0 OFFLINE, 1 UNKNOWN, 10 ONLINE, 20 IN_CALL), connection types (-10 INCOMING, 0 PASSIVE, 1 DIRECT, 2 PROXY), or the `cospace` vs `conference` terminology. Use this skill — the API is wide and has several subtle splits the OpenAPI doc alone doesn't make obvious.
---

# Mividas Core + Rooms API

**Mividas Core + Rooms** is a third-party management platform that sits above Pexip Infinity, Cisco Meeting Server (CMS), Cisco VCS/Expressway, and individual video endpoints (Cisco CE, Cisco Webex Devices, Microsoft Teams Rooms, generic SIP/H.323). It exposes a unified REST surface at `/json-api/v1/` covering:

- **Conferencing** — CMS cospaces, Pexip conferences, scheduled meetings, active-call control
- **Rooms** — endpoint inventory, provisioning, firmware, room controls, branding, sensor analytics
- **Operations** — statistics, alerts, monitor rules, debug logs, license/policy reports
- **Integrations** — address books, calendar (EWS / MS Graph), Webex Device API, CUCM, LDAP

The full OpenAPI document is shipped under [references/openapi-spec.yaml](references/openapi-spec.yaml) — consult it for exact field-level details. The topic references below capture the parts that don't sit nicely in the spec: the conceptual model, lifecycle flows, the parallel-resource splits, and the gotchas.

## When to load which reference

Start with the smallest reference that fits the task — don't load everything.

| Reference | Load when… |
|---|---|
| [auth-and-multitenancy.md](references/auth-and-multitenancy.md) | Setting up an HTTP client, dealing with Basic Auth, the `X-Mividas-Customer` header, customer lookup, or per-customer shared keys. |
| [cospaces-meetings-and-calls.md](references/cospaces-meetings-and-calls.md) | Creating/updating CMS cospaces or Pexip conferences, scheduled meetings, listing/controlling active calls, or any of the `/calls/{id}/...` / `/call_legs/{id}/...` action endpoints. |
| [endpoints-and-provisioning.md](references/endpoints-and-provisioning.md) | CRUD on endpoints, pushing configuration, installing firmware, deploying room controls, taking/restoring backups, or driving the `/endpoint/provision/` → `/endpointtask/` task-queue flow. |
| [statistics-and-monitoring.md](references/statistics-and-monitoring.md) | Pulling call/room/meeting/provider statistics, head-count / sensor analytics, or querying / acknowledging endpoint/MCU alerts. |
| [policy-and-routing.md](references/policy-and-routing.md) | Time-limited or predetermined Pexip policy logins, Pexip Call Routing Rule sync, policy/license reports, or the participant-limit model. |
| [addressbooks-and-integrations.md](references/addressbooks-and-integrations.md) | Building or syncing address books from CMS, Pexip, VCS, TMS, CSV, LDAP, Seevia. EWS / MS Graph / Webex Device / CUCM integrations and calendar sync. |
| [debug-and-logs.md](references/debug-and-logs.md) | Inspecting CDR, error, audit, trace, policy logs or capturing a per-call trace via `/debug/active_trace_log/`. |
| [gotchas-and-conventions.md](references/gotchas-and-conventions.md) | Read alongside any task — covers list-shape variance, parallel CMS/Pexip endpoints, deprecated aliases, enum semantics, and destructive-call hazards. |
| [openapi-spec.yaml](references/openapi-spec.yaml) | Exact request/response schemas, every custom action, every enum. The references above point into this file by tag. |

A stdlib-only Python client lives at [scripts/mividas_client.py](scripts/mividas_client.py) — Basic Auth, customer header, both pagination shapes, and a polling helper for endpoint tasks.

## Quickstart

Base URL: `https://<mividas-host>/json-api/v1/`. Auth: HTTP **Basic** (admin user or service account). The OpenAPI declares an `oauth2` scheme but that's for the end-user Portal — the management API documented here uses Basic.

```bash
curl -u "$USER:$PASS" \
  -H "X-Mividas-Customer: 7" \
  "https://mividas.example.com/json-api/v1/customer/"
```

The `X-Mividas-Customer: <id>` header is required only if the authenticated user has access to more than one customer (multi-tenant installation). Look up customer IDs via `GET /customer/`. The spec description mentions `/customers/` — that's a doc typo; the path is `/customer/` (singular).

See [auth-and-multitenancy.md](references/auth-and-multitenancy.md) for the full picture including `/customerkey/` (per-customer API keys distinct from user Basic Auth).

## End-to-end recipes

### Find the active call for a cospace and mute everyone

```python
from scripts.mividas_client import MividasClient

c = MividasClient("https://mividas.example.com", user, pwd, customer_id=7)

calls = c.get("/calls/")                              # bare JSON array, NOT paginated
for call in calls:
    if call["cospace"] == "engineering-standup":
        c.post(f"/calls/{call['id']}/set_all_mute/", {"value": True})
        break
```

`/calls/` returns a bare array. Several endpoints do; several others wrap in `{count, next, previous, results}`. The client's `list()` helper normalises both — see [gotchas-and-conventions.md](references/gotchas-and-conventions.md#paginated-vs-bare-list-responses).

### Push a setting to ten Cisco endpoints and wait for completion

```python
provision = c.post("/endpoint/provision/", {
    "endpoints": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
    "configuration": [
        {"key": ["SystemUnit", "Notifications", "Mode"], "value": "On"},
    ],
})

# wait_for_tasks polls /endpointtask/?provision=<id> until every task reaches a terminal state
tasks = c.wait_for_tasks(provision["id"])
for t in tasks:
    if t["status"] == -10:                            # ERROR
        print(f"failed on {t['endpoint_title']}: {t['error']}")
```

Task status codes: `-10` ERROR · `-1` CANCELLED · `0` PENDING · `5` QUEUED · `10` COMPLETED. See [endpoints-and-provisioning.md](references/endpoints-and-provisioning.md#the-provisioning-task-queue).

### Create a CMS cospace with host + guest access methods

```python
cospace = c.post("/cospace-acano/", {
    "name": "QA Standup",
    "uri": "qa-standup",
    "call_id_generation_method": "increase",
    "owner_jid": "alice@example.com",
    "access_methods": [
        {"name": "Host",  "scope": "private", "uri_method": "call_id"},
        {"name": "Guest", "scope": "public",  "uri_method": "call_id"},
    ],
})
```

For a Pexip Infinity conference instead, POST to `/cospace-pexip/` with a `Conference` payload (different schema). The unified `/cospace/` endpoint reads from both clusters but does not create — see [cospaces-meetings-and-calls.md](references/cospaces-meetings-and-calls.md#cms-vs-pexip-which-endpoint-to-use).

### Pull a call-statistics dashboard for the last 24 h

```python
from datetime import datetime, timedelta, timezone

now = datetime.now(timezone.utc)
dash = c.get("/call_statistics/dashboard/", params={
    "ts_start": (now - timedelta(days=1)).isoformat(),
    "ts_stop":  now.isoformat(),
})
print(dash["summary"], dash["graphs"])
```

`ts_start` and `ts_stop` are **required** on most statistics endpoints; omitting them returns an error. Filters (`protocol`, `tenant`, `endpoints[]`, `organization`, `multitenant`) further scope the result. See [statistics-and-monitoring.md](references/statistics-and-monitoring.md).

## Safety

This is a **management API for production conferencing infrastructure**. Destructive operations are common:

- `DELETE /cospace-acano/{id}/` removes a CMS space (and its history of members).
- `DELETE /calls/{id}/` drops an active call (kicks every participant).
- `DELETE /endpoint/{id}/` removes an endpoint, its tasks, alerts, and history.
- `POST /purge_queues/` with `all_queues: true` purges every background queue.
- `POST /endpoint/bulk_delete/`, `POST /cospace/bulk_delete/`, `POST /cospace-acano/{id}/members/bulk_delete/` — bulk deletes by ID list.

Always confirm before running destructive operations against a shared installation. The Mividas server has its own audit log (`/debug/audit_log/`), but that's discovery-after-the-fact.

## Mividas terminology cheat sheet

| Mividas term | What it actually is |
|---|---|
| **Cluster** | A logical group of MCU `Provider`s — CMS Call Bridges sharing a database, or Pexip Conferencing Nodes in one deployment. |
| **Provider** | One MCU node. Subtypes: 1=CMS Call Bridge, 2=Pexip Management Node, 4=CMS Service Node, 6=Expressway, 7=Cisco CUCM. |
| **Customer** | A Mividas-level tenant (multi-tenant installations). Identified by `X-Mividas-Customer: <id>`. Maps to a CMS tenant or Pexip tenant via `acano_tenant_id` / `pexip_tenant_id`. |
| **CoSpace** | CMS Meeting Space. The unified `/cospace/` endpoint also surfaces Pexip Conferences using the same word. |
| **Conference** | Pexip-Infinity-flavoured CoSpace. Use `/cospace-pexip/` to create/update. |
| **Endpoint** | A video room/device (Cisco CE, Cisco Webex registered, Teams MTR, other). |
| **Provider load** | Per-MCU live capacity / call count / bandwidth snapshot. `/provider/load/`, `/provider_statistics/`. |
| **Meeting** | Mividas-managed scheduled instance (driven by `/meeting/` or via calendar sync). Distinct from `Call` (live) and `CoSpace` (room). |
