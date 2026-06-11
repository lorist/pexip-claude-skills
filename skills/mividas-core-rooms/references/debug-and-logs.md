# Debug and Log Surfaces

Mividas stores a lot of operational data. The `/debug/*` family exposes it.

| Path | What you'll find there |
|---|---|
| `/debug/audit_log/` | Every API request the Mividas web layer handled, plus admin-UI changes. Use for "who deleted that cospace?". |
| `/debug/error_log/` | Internal errors (Python exceptions, bridge call failures). The triage queue for things going wrong. |
| `/debug/email_log/` | Outbound emails (meeting invites, notifications). |
| `/debug/cisco/` | HTTP feedback events received from Cisco CE endpoints. |
| `/debug/cisco_provision/` | Provisioning hits from Cisco endpoints (when they fetch their config). |
| `/debug/acanocdr/` | CMS CDR records received. |
| `/debug/acanocdrspam/` | CMS CDRs that came in but were dropped as duplicates / out-of-window. |
| `/debug/pexip_event/` | Pexip event-sink callbacks received. |
| `/debug/pexip_history/` | Pexip history-API fetches. |
| `/debug/pexip_policy/` | Pexip policy callbacks (what Mividas was asked, what it answered). |
| `/debug/policy_log/` | Lower-level policy decision log (every call/participant evaluated). |
| `/debug/external_policy_log/` | License/participant-limit decisions only — has `limit` (`0` OK / `10` Soft / `20` Hard) and `action` (`0` Ignore / `5` Log / `20` Audio / `30` SD / `35` 720p / `100` Reject). |
| `/debug/vcs/` | VCS / Expressway call-history events. |
| `/debug/trace_log/` | HTTP trace log (Mividas → MCU / endpoint API). Set per-call via `active_trace_log` (below). |
| `/debug/active_participant/` | Snapshot of participants currently active across all clusters. |
| `/debug/leg/?guid=...` | Combined view of one call leg — its `legs[]`, `cdr[]`, and `history[]` records — for end-to-end debugging. |

Most list endpoints accept timestamp filters (`ts_created__gt`, `ts_created__gte`, `ts_created__lt`, `ts_created__lte`), plus resource-specific filters (`cluster_id`, `customer`, `ip`, `type`, etc.). Paginate with `limit` / `offset`.

## Capturing a per-call trace (`/debug/active_trace_log/`)

When you need to debug a specific call as it happens, an `ActiveTraceLog` tells Mividas to log every API call it makes against the target (cluster / provider / customer / endpoint) for a time window:

```python
trace = c.post("/debug/active_trace_log/", {
    "everything": False,
    "ts_start":   "2026-06-12T14:00:00Z",
    "ts_stop":    "2026-06-12T15:00:00Z",
    "endpoint":   42,                  # OR cluster / provider / customer
})

# Now reproduce the issue, then read:
traces = c.list("/debug/trace_log/", params={
    "endpoint":  42,
    "ts_created__gte": "2026-06-12T14:00:00Z",
    "ts_created__lt":  "2026-06-12T15:00:00Z",
})
```

Each `trace_log` row has `method`, `url_base`, `provider_id`, `endpoint`, `debug_session_id` and the request/response body. Scope it tightly — turning on `everything: true` cluster-wide is expensive.

## Audit log (`/debug/audit_log/`)

Two-tier audit:

- `scope: auth` — login / login-failed / logout.
- `scope: http` — API requests (`action` is `change_request` / `delete_request` / `read_request`).
- `scope: book_api` — Book-API (calendar / portal) requests.

Filter by `username`, `ip`, `path`, `type`, `scope`, `action`, `ts_created`. Use `username__startswith` for prefix matches; `path__startswith` is the most useful for "every change to this resource".

Audit-log entries don't expire automatically — they're subject to `/cleanupschedule/` retention.

## Cleanup model

Mividas has explicit retention controls under `/cleanupsettings/` (the on/off and "should we keep cospace names when redacting?" knobs) and per-type schedules under `/cleanupschedule/`. Schedule keys (`TypeKeyEnum`) include:

- `audit_log`, `error_log`, `email_log`, `trace_log`
- `acano_cdr`, `acano_cdr_spam`, `pexip_eventsink`, `pexip_history`, `pexip_policy_log`, `vcs_calls`
- `endpoint_cisco_event`, `endpoint_cisco_provision`, `endpoint_data_file`, `endpoint_tasks`
- `policy_auth_log`, `policy_auth_log_redaction`
- `meeting`, `changed_meeting`
- `statistics_invalid_legs`, `statistics_invalid_calls`, `statistics_redaction`, `statistics_full_delete`
- `sensor_data`
- `synced_mcu_data`

`CleanupSchedule.interval` is a `%d %H:%M:%S` / ISO-8601 duration ("90 days" → `"90 00:00:00"` or `"P90D"`). Empty = disabled (data is kept indefinitely).

## Queues (`/purge_queues/`)

```python
c.post("/purge_queues/", {"all_queues": True})
```

Purges every background queue (provisioning, sync, statistics, …). This is destructive — in-flight work is dropped, not cancelled gracefully. Use only when you know you have a stuck queue.

## Common pitfalls

- `/debug/trace_log/?errors/` (the `errors` action) summarises only failed traces — much cheaper than listing the full table.
- `audit_log` does not include details of *what changed* — just that a `change_request` happened. To see the diff, you have to pair it with the application's own model history (which isn't exposed via API — only via the audit log itself).
- `active_trace_log` with `everything: true` will fill the trace table quickly on a busy installation. Always scope to a `cluster` / `provider` / `customer` / `endpoint` when possible.
- The retention schedules are **per `TypeKey`** — there is no global "delete everything older than N days" knob. Configure each type explicitly.
- Pexip event-sink delivery uses Mividas's `/cluster/{id}` event-sink URL (see `ClusterAdmin.cdr_url` / `policy_url`). Lost events typically mean the cluster lost connectivity to Mividas — check the cluster's event sink config in Pexip Mgr Node and Mividas's network reachability.
