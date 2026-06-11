# Statistics and Monitoring

Three roughly-parallel statistics surfaces and two monitoring surfaces:

| Surface | What it answers | Path |
|---|---|---|
| **Call statistics** | "Who called who, when, on which MCU?" | `/call_statistics/...` |
| **Room statistics** | "How are my physical rooms being used?" | `/room_statistics/...` |
| **Meeting statistics** | "Were scheduled meetings actually held?" | `/meeting_statistics/...` |
| **Provider statistics** | "How loaded are my MCUs?" | `/provider_statistics/...`, `/provider/load/` |
| **Endpoint alerts** | "Which rooms have problems?" | `/monitor_endpoint/...` |
| **MCU alerts** | "Which providers have problems?" | `/monitor_mcu/...` |

## Statistics inputs

Mividas does not host the MCUs — it pulls CDR/event data from them. Each input source is a `StatisticsServer` (`/callstatistics_server/`):

| `type` | Source |
|---|---|
| `0` | Cisco Meeting Server (CMS CDR + events) |
| `4` | Pexip (event sink + history API) |
| `1` | Cisco VCS / Expressway (CDR) |
| `2` | Endpoints (HTTP feedback from individual Cisco rooms) |
| `3` | Combine (logical aggregator across multiple of the above — appears as a unified tab in Insights) |

`POST /callstatistics_server/{id}/rematch_stats/` and `reparse_logs/` reprocess historical data (e.g. after a customer-match rule change). `reparse_api_history/` re-fetches from the source.

## Call statistics (`/call_statistics/`)

The flagship statistics endpoint. **Every call requires `ts_start` and `ts_stop` (ISO datetime). Both are required query params.**

### Shape of the result (`CallStatisticsData`)

```json
{
  "calls":   [Call, ...],
  "legs":    [Leg, ...],
  "errors":  {...},
  "summary": {...},
  "graphs":  {...},
  "defer_load":           false,
  "loaded":               true,
  "has_data":             true,
  "pdf_report_url":       "...",
  "excel_report_url":     "...",
  "excel_debug_report_url": "...",
  "choices":              {"server": [{label: id}], "tenant": [[id, label]]}
}
```

| Field | Use |
|---|---|
| `calls` / `legs` | Raw rows. Each `Leg.debug_url` links to a debug surface. |
| `summary` | Pre-aggregated totals. |
| `graphs.per_day` / `graphs.sametime` | Plotly figure JSON (`data` + `layout`) ready to render. |
| `pdf_report_url`, `excel_report_url` | Direct downloads. |
| `choices` | Discovered filter values — useful for populating filter UIs. |

### Filters

| Param | Meaning |
|---|---|
| `tenant` | CMS tenant ID or Pexip tenant string. |
| `server` | `StatisticsServer.id` (positive integer). The pattern allows `-1` to mean "all". |
| `cospace`, `member`, `ou` | Free-text filters (substring matches). |
| `protocol` | Enum 0–10 — see `CallStatisticsProtocolEnum` below. |
| `multitenant` | Boolean — treat the data as multi-tenant or single-tenant. |
| `only_gateway` | Boolean — only Pexip gateway calls. |
| `organization` | `OrganizationUnit.id`. |
| `endpoints[]` | Filter to legs involving these endpoints. |

`CallStatisticsProtocolEnum`: `0`=SIP, `1`=H323, `2`=CMS, `3`=Lync, `4`=Cluster, `5`=Stream/recording, `6`=Lync SubConnection, `7`=WebRTC, `8`=Teams, `9`=GMS (Google Meet), `10`=Spark.

### Sub-endpoints

| Path | Returns |
|---|---|
| `GET /call_statistics/` | Full `CallStatisticsData`. |
| `GET /call_statistics/dashboard/` | Same shape but optimised for dashboard use. |
| `GET /call_statistics/graphs/` | `CallStatisticsGraphs` only (`per_day` + `sametime` Plotly). |
| `GET /call_statistics/debug/` | `CallStatisticsDebugResponse` — raw call/leg dump for troubleshooting. |
| `GET /call_statistics/call_debug/` | Detailed single-call debug (no body — UI download). |
| `POST /call_statistics/rewrite_data/?server=...&force_rematch=...` | Background job: rewrite historical data for one server. |
| `GET /call_statistics/settings/` / `POST /call_statistics/settings/` | Per-customer settings (choices, defaults). |

### Sub-stats for "in this conference"

The same filter family also exists on the call resource: `/cospace/{id}/latest_calls/`, `/cospace/{id}/active_call/`, `/meeting/{id}/calls/`.

## Room statistics (`/room_statistics/`)

Same shape as `/call_statistics/`, but the analysis is room-centric (per `Endpoint`). Adds:

- `GET /room_statistics/head_count/` — head-count totals (people in the room). Accepts `as_percent` (vs room capacity), `ignore_empty`, `fill_gaps`, `only_hours`, `only_days` filters and returns `HeadCountStatisticsResponse` (Plotly per-hour / per-day / per-date graphs, plus `now`).
- `GET /room_statistics/missing_endpoints/` — legs that we couldn't match to a known endpoint (helps complete the inventory).
- `GET /room_statistics/sensors_csv/?sensor=<x>` — raw sensor data CSV. `sensor` enum: `head_count`, `presence`, `humidity`, `air_quality`, `temperature`, `ambient_noise`, `sound_level`.
- `GET /room_statistics/endpoint_status/` — current per-endpoint status snapshot.

Sensor thresholds for alerts (`/sensor_settings/`) define what counts as "too hot", "too noisy", etc. The customer level keeps `temperature_max/min`, `humidity_max/min`, etc.

## Meeting statistics (`/meeting_statistics/`)

Scheduled-meeting analytics — answered against `Meeting`s, not raw calls.

- `GET /meeting_statistics/graphs/?ts_start=&ts_stop=&meeting_types[]=&organization=&graphs_based_on_hours=` returns `MeetingStatisticsGraphs` (pie chart, per_day, per_hour, diurnal_hours Plotly figures + `excel_report_url`).
- `GET /meeting_statistics/export/` returns Excel directly.
- `meeting_types[]` filters by `MeetingType` keys.

## Provider statistics (`/provider_statistics/`)

How busy each MCU is over time.

- `GET /provider_statistics/?` — paginated `ProviderAgg` rows with per-cluster, per-provider time-bucketed load/calls/participants/bandwidth.
- `GET /provider_statistics/graphs/?ts_start=&ts_stop=` — Plotly graphs of load / alarms / participant_count / calls_count / bandwidth_in / bandwidth_out keyed by `clusters[]`.
- `GET /provider_statistics/load/?ts_start=&ts_stop=` — `ProviderAgg` aggregate over the window.
- `GET /provider/load/` — paginated raw `ProviderLoad` rows (one per provider per sample).

## Policy / license reports (`/policy/report/`)

Per-customer reports on whether they're hitting their `CustomerPolicy.participant_limit` / `participant_hard_limit`. See [policy-and-routing.md](policy-and-routing.md#license--participant-policy) for the model.

## Endpoint monitoring (`/monitor_endpoint/`)

Active and historical alerts about individual endpoints.

### Listing alerts (`EndpointAlert`)

```python
alerts = c.list("/monitor_endpoint/", params={
    "endpoint":          42,
    "is_active":         True,
    "acknowledged":      False,
    "severity":          40,            # ERROR
    "ts_raised__gte":    "2026-06-01T00:00:00Z",
})
```

Useful filters: `code` (a stable string ID), `title` text, `severity` (`SeverityEnum`: 50 CRITICAL · 40 ERROR · 30 WARNING · 20 INFO · 10 DEBUG · 0 NOTSET), `is_active`, `persistent`, `acknowledged`, `ts_raised(__gte/__lte)`, `ts_lowered(__gte/__lte)`.

### Acknowledge / unacknowledge

```python
c.post("/monitor_endpoint/acknowledge/", {
    "alert":    "OFFLINE_TOO_LONG",   # code
    "endpoint": 42,
})
c.post("/monitor_endpoint/unacknowledge/", {"alert": "OFFLINE_TOO_LONG", "endpoint": 42})
```

### Summary endpoints

- `GET /monitor_endpoint/summary/?only_active=true&include_acknowledged=false` — `EndpointAlertSummaryResponse` (groups by title/severity, lists affected endpoint IDs).
- `GET /monitor_endpoint/acknowledged_summary/` — only acknowledged alerts.

## MCU monitoring (`/monitor_mcu/`)

Same shape, different target: `ProviderAlert` against `Provider`s rather than endpoints. Same `acknowledge` / `unacknowledge` / `summary` / `acknowledged_summary` sub-paths.

## Auto-ignore rules (`/monitor_action/`)

`AlertActionRule.action: 0` = "Ignore". Use this to silence noisy alerts.

| Endpoint | Use |
|---|---|
| `POST /monitor_action/` | Create a rule (title + code + endpoint list + apply_to_all flag). |
| `POST /monitor_action/ignore_endpoint/` | Quick path: ignore alert `code` for one `endpoint`. |
| `POST /monitor_action/ignore_apply_for_all/` | Ignore alert `code` for *all* endpoints (one global toggle). |
| `POST /monitor_action/{id}/remove_endpoint/` | Lift the ignore for one endpoint. |

## Custom alert rules (`/monitor_user_rule/`)

Per-customer alert thresholds Mividas evaluates against endpoint status/configuration/metadata:

```python
c.post("/monitor_user_rule/", {
    "value_type": "status",                  # "status" | "configuration" | "meta"
    "key":        "Video/Output/Connector/1/ConnectedDevice/Name",
    "operator":   "=",                       # =, !=, <, <=, >, >=, added, removed
    "limit":      "Sony Bravia",
    "ignore_unset": True,
    "persistent": False,
    "message":    "Display swapped",
    "severity":   30,                        # WARNING
})
```

`operator: "added"` / `"removed"` fire on the first sample after a transition — useful for "endpoint started reporting head count" style events.

## Common pitfalls

- `ts_start` / `ts_stop` are **required** on most stats endpoints (the spec marks them required). The error response is unhelpful — double-check both are present and ISO-formatted with timezone.
- Statistics endpoints return Plotly JSON, not images. Render client-side with `plotly.js`, or use the `excel_report_url` / `pdf_report_url` for static output.
- Alerts have **stable `code` strings** (e.g. `OFFLINE_TOO_LONG`, `AUTH_FAILED`) — those are what you key automation off, not the human `title`.
- `ProviderLoad.percent` is `null` if `max_load` isn't set on the provider — set `Provider.max_load` to get a meaningful percentage.
- `head_count` is `null` when the sensor isn't present (cheap Cisco endpoints don't have people-counting). Don't conflate "0 people" with "no sensor".
- Sensor data is only retained for endpoints with `allow_sensor_data: true` (GDPR knob).
