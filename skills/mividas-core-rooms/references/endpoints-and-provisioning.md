# Endpoints and Provisioning (Mividas Rooms)

The "Rooms" half of Mividas manages individual video endpoints — Cisco CE-OS rooms (TelePresence / Webex Room / Codec Pro / DX / SX), Cisco-Webex-registered devices, Microsoft Teams Rooms (MTR), and generic "other" SIP/H.323 endpoints.

## The Endpoint resource

`GET /endpoint/` and `POST /endpoint/` — list/create. Filters on list:

- `manufacturer=10` Cisco CE · `=11` Cisco Webex · `=30` Teams MTR · `=90` Other (`ManufacturerEnum`).
- `status=10` ONLINE · `=20` IN_CALL · `=0` OFFLINE · `=-1` AUTH_ERROR · `=-2` CONNECTION_ERROR · `=1` UNKNOWN (`StatusA6eEnum`).
- `connection_type=1` DIRECT · `=2` PROXY · `=0` PASSIVE · `=-10` INCOMING (`ConnectionTypeEnum`).
- `firmware=`, `serial_number=`, `mac_address=`, `ip=`, `product_name=`, `location=`, `org_unit=` exact-match filters.
- `has_warnings`, `is_online`, `only_new` boolean filters.

### Connection types (key concept)

| Type | What Mividas does |
|---|---|
| **DIRECT (1)** | Mividas reaches the endpoint over HTTPS at `hostname` / `ip` + `api_port`. Requires network reachability and credentials. Used for normal LAN endpoints. |
| **PROXY (2)** | The endpoint connects *out* to a Mividas proxy (`EndpointProxy`); Mividas talks to it through the proxy tunnel. Used when endpoints are behind NAT / on isolated networks. The proxy is the per-network helper running on the customer LAN. |
| **PASSIVE (0)** | Mividas only receives events (HTTP feedback) — no outbound polling, no provisioning push. Used for "telemetry only" rooms. |
| **INCOMING (-10)** | A registration-style endpoint that hasn't been fully claimed yet — appears in the "new endpoints" inbox at `/endpoint/incoming/`. |

### Per-manufacturer fields

- **Cisco CE / Webex** — `hostname`, `username`, `password` (via separate set-password flow), `api_port` (default 443), `verify_certificate`. The full Cisco xAPI is exposed through Mividas via `set_configuration/`, `run_command/`, room controls.
- **Teams MTR** — owned via Graph API. `device_id` is the Microsoft Graph teamworkDeviceId; `credential_source` is the `MSGraphCredentials.id` to use. Provisioning options are restricted to what Graph supports.
- **Cisco Webex registered** — `device_id` is the Webex Device ID; `credential_source` points at a `WebexCredentials` row.
- **Other** — telemetry only; no provisioning.

### Useful read endpoints

| Endpoint | Use |
|---|---|
| `GET /endpoint/incoming/` | Endpoints that auto-registered but aren't claimed. |
| `GET /endpoint/{id}/status/?cached=true` | Cached live status (`EndpointStatus`). `cached=force` for cache-only; `cached=false` to fetch fresh. `refresh=true` queues a background refresh. |
| `GET /endpoint/{id}/configuration_data/?cached=true` | Full xConfiguration tree. Same cache flags. |
| `GET /endpoint/{id}/status_data/?cached=true` | Full xStatus tree. |
| `GET /endpoint/{id}/valuespace_data/` | Valuespace definitions for the configuration tree. |
| `GET /endpoint/{id}/dial_info/` | SIP / H.323 dial info. |
| `GET /endpoint/{id}/call_history/` | Call history from the endpoint itself (not from CDR servers). |
| `GET /endpoint/{id}/calls/` | Live legs the endpoint is currently in. |
| `GET /endpoint/{id}/active_meeting_details/` | The current meeting tied to this endpoint, if any. |
| `GET /endpoint/{id}/bookings/` | Local-calendar bookings for the room (from EWS / Graph). |
| `GET /endpoint/all_bookings/` | Tenant-wide aggregate of room bookings. |
| `GET /endpoint/availability/` | Free/busy across `endpoints[]` over `ts_start`/`ts_stop`. |
| `GET /endpoint/{id}/is_up/` | Lightweight "is this endpoint up?" check. |
| `GET /endpoint/{id}/head_count/` | Current head-count sensor reading. |
| `GET /endpoint/filters/` | Lists distinct values present in the inventory — useful for building filter UIs. |

## The provisioning task queue

This is the workflow you'll use most.

```
POST /endpoint/provision/         ────► returns { id }      (the provision_id)
       │
       └── creates one EndpointTask per (endpoint × action)
                │
                └── /endpointtask/?provision=<id>            ◄──── poll here
                          │
                          └── each task: status 0 PENDING → 5 QUEUED → 10 COMPLETED / -10 ERROR / -1 CANCELLED
```

### Submitting a provision

`POST /endpoint/provision/` with `PatchedProvisionBody`. All fields are optional; include only the actions you want:

```python
c.post("/endpoint/provision/", {
    "endpoints": [42, 43, 44],
    "schedule": "2026-06-12T22:00:00Z",            # omit for "do it now"
    "configuration": [                              # xConfiguration push (Cisco CE)
        {"key": ["SystemUnit", "Notifications", "Mode"], "value": "On"},
    ],
    "commands": [                                   # xCommand calls
        {"command": ["Standby", "Deactivate"], "arguments": {}},
    ],
    "firmware": 17,                                 # EndpointFirmware.id
    "addressbook": 4,                               # AddressBook.id
    "branding_profile": 2,                          # BrandingProfile.id
    "room_controls": [11, 12],                      # RoomControl IDs
    "room_control_templates": [3],                  # RoomControlTemplate IDs
    "clear_room_controls": False,                   # wipe existing macros/panels first
    "room_controls_delete_operation": False,        # mark these files as removals
    "head_count": True,                             # enable head-count sensors
    "presence": True,
    "allow_personal_room_analytics": True,
    "passive": False,                               # toggle PASSIVE connection mode
    "events": True,                                 # subscribe to HTTP feedback
    "statistics": True,                             # call statistics push
    "set_password": True,                           # rotate the endpoint password
    "password": "new-pa55w0rd",                     # explicit new password
    "standard_password": False,                     # OR set to True to use the customer's standard pwd
    "dial_info": {                                  # set SIP/H.323 identity
        "name": "Room 12",
        "sip": "room12@example.com",
        "h323": "room12",
        "sip_proxy": "sip.example.com",
        "register": True,
    },
    "constraint": "night",                          # only execute during the customer's night window
    "repeat": False,                                # re-run on a cadence
    "xapi_text": "xConfiguration ...",              # raw xAPI text (free-form Cisco)
    "backup": True,                                 # take a backup snapshot first
    "webex": {                                      # for Webex/Teams endpoints
        "action": "register",                       # or "reset"
        "credentials": 7,                           # WebexCredentials.id
    },
})
# → returns {"status": "OK", "id": 1234}
```

### Polling tasks

```python
tasks = c.list("/endpointtask/", params={"provision": 1234})

# Wait until every task is terminal:
TERMINAL = {-10, -1, 10}
while not all(t["status"] in TERMINAL for t in tasks):
    time.sleep(2)
    tasks = c.list("/endpointtask/", params={"provision": 1234})

failures = [t for t in tasks if t["status"] == -10]
```

Task status codes (`Status9b5Enum`):

| Code | Meaning |
|---|---|
| `0` | PENDING (scheduled, not yet picked up) |
| `5` | QUEUED (worker has it) |
| `10` | COMPLETED |
| `-1` | CANCELLED |
| `-10` | ERROR — read `task.error` for the message |

Useful task-level endpoints:

- `POST /endpointtask/{id}/retry/` — re-run one failed task.
- `POST /endpointtask/{id}/cancel/` — cancel a pending task.
- `POST /endpointtask/bulk_retry/` and `bulk_cancel/` — bulk versions; return `EndpointTaskListWithErrors` (per-task success/failure breakdown).
- `GET /endpointtask/latest/` — only the latest task per endpoint.
- Filters: `endpoint`, `endpoints[]`, `status`, `provision`, `changed_since` (timestamp), `order_by` (`created` | `change`).

### Inline endpoint actions (skip the provision queue)

Some operations have direct endpoints that execute synchronously:

| Direct action | Notes |
|---|---|
| `POST /endpoint/{id}/call_control/` | dial / answer / disconnect / mute / reboot / volume / presentation / dtmf — runs immediately and returns the endpoint's response. |
| `POST /endpoint/{id}/run_command/` | One-off xCommand (`RunCommand`). |
| `POST /endpoint/{id}/set_configuration/` | One-off xConfiguration set. |
| `POST /endpoint/{id}/set_sip_aliases/` | Replace SIP alias list. |
| `POST /endpoint/{id}/install_firmware/` | Quick firmware install (no Provision wrapper). |
| `POST /endpoint/{id}/backup/` | Trigger an `EndpointBackup`. |
| `POST /endpoint/{id}/commands_data/` | Upload xCommand/xConfiguration JSON files (used to seed valuespace info). |

When you don't need batching or scheduling, these are simpler than `provision/`. When you do (multiple endpoints, scheduled time, repeat cadence, multi-action), use `provision/`.

## Firmware (`/endpointfirmware/`)

Upload once, deploy many times:

```python
fw = c.post("/endpointfirmware/", data_multipart={
    "file":         open("ce9.15.13.pkg", "rb"),
    "manufacturer": 10,
    "models":       ["Cisco Webex Room Kit", "Cisco Webex Codec Pro"],
    "version":      "ce9.15.13",
    "is_global":    True,
})
```

- `file` is the actual firmware binary (Cisco `.pkg` / `.sgn` / `.cop` / `.sha512`).
- Or `external_url` — Mividas fetches from a URL instead.
- `models` is a list of `product_name` strings the firmware is valid for.
- `is_global` means this firmware appears for every customer (otherwise it's scoped to the current customer).

`POST /endpointfirmware/{id}/copy/` clones one firmware to additional `models[]`. `GET /endpointfirmware/{id}/download/` re-downloads the file.

## Endpoint backups (`/endpointbackup/`)

A backup snapshots the endpoint's running configuration. `POST /endpoint/{id}/backup/` triggers one. `POST /endpointbackup/{id}/restore/` pushes the backup back to the same (or another) endpoint via the provision queue.

## Room controls (`/roomcontrol/`)

Cisco CE macros and UI panels:

- A `RoomControl` is a folder of `RoomControlFile`s. Each file has `name`, `content` (the macro JS / panel XML), `transpile` flag, `activate` flag (auto-activate on the endpoint), and `is_removal` (a tombstone — when provisioned, the endpoint *deletes* the corresponding macro/panel).
- A `RoomControlTemplate` bundles multiple `RoomControl`s and is the unit endpoints subscribe to.
- `POST /roomcontrol/{id}/add_files/`, `add_attributes/` to extend; `POST /roomcontrol/{id}/export/?files=…` to download a manifest for sharing.
- `require_software_version` / `require_state` gate provisioning when the endpoint doesn't meet preconditions.

To deploy: include `room_controls: [<id>]` and/or `room_control_templates: [<id>]` in a `/endpoint/provision/` call.

## Endpoint attributes (`/endpoint_attribute/` and `/endpoint_attribute_value/`)

Custom metadata on top of the built-in fields. Useful when the customer wants to tag every room with e.g. "building", "floor", "leased-to-team":

- `EndpointAttribute` defines the schema (name, type, default, choices, valuespace).
- `EndpointAttributeValue` is the per-endpoint assignment.
- `POST /endpoint_attribute/remove_namespace/` is a bulk-delete by `namespace` (useful for cleaning up a removed integration).

## Branding profiles (`/endpointbranding/`)

Logos and background images pushed to Cisco endpoints' wallpaper / halfwake / scheduler screens. Each `BrandingFile.type` is an enum (`1` Background, `2` Branding, `3` HalfwakeBackground, `4` HalfwakeBranding, `5` CameraBackground1, `7` SchedulerBranding, `8` SchedulerBackground); the `file` is a base64-encoded image data URL.

## Endpoint settings, domains, IP nets, passwords (`/endpointsettings/`)

Customer-level defaults for the Rooms feature: the default address book, branding profile, dial protocol, SIP/H.323 proxies, the `provision_domain` and `provision_path` (used for endpoints to auto-provision into Mividas), the customer's "standard passwords" list (rotated through when claiming new endpoints), and night-time-window hours for `constraint: "night"` provisions.

`/endpointsettings/passwords/`, `/endpointsettings/domains/`, `/endpointsettings/ip_nets/` are read-only listings of the configured values; `set_passwords/`, `set_domains/`, `set_ip_nets/` are the bulk-replace endpoints.

## Endpoint proxies (`/endpointproxy/`)

A small helper service customers deploy on their own network when endpoints can't be reached directly from Mividas. Each proxy has its own `ip_nets[]` (subnets it covers). `/endpointproxy/status/` and `/endpointproxy/{id}/activate/` are the lifecycle endpoints.

## Endpoint templates (`/endpointtemplate/`)

A canned set of `settings[]` and `commands[]` you can apply to multiple endpoints — different from `RoomControlTemplate` which is for macros/panels.

## Cisco webex / Teams device integrations

- `WebexCredentials` (`/webex_integrations/`) — connects Mividas to the Webex Device API.
- `MSGraphCredentials` (`/msgraph_credential/`) — Graph API connection for Teams MTR.
- `CucmCredentials` (`/cucm_integrations/`) — Cisco Unified Communications Manager (for "CUCM sync" claiming endpoints from CUCM device pool).
- `OAuthCredential` (`/msgraph_oauth/`) — base OAuth record shared across the above where applicable.

Each has `GET .../{id}/pending_devices/` and `.../{id}/all_devices/` to list what the credentials see, plus `POST .../{id}/sync/` to import devices as `Endpoint` rows. These integrations typically run a scheduled sync in the background as well.

## Reports (`/endpointreporttemplate/`)

Predefined report definitions. `POST /endpointreporttemplate/report/` runs a one-off; `POST /endpointreporttemplate/export_report/` returns Excel.

## Common pitfalls

- The `EndpointTask.status` enum is **negative for failures** (`-10` ERROR, `-1` CANCELLED) — not a string. Don't treat `status > 0` as "good".
- Setting a configuration via `set_configuration/` goes immediately; via `/endpoint/provision/` it queues. Don't mix the two for a single change — pick one.
- `room_controls_delete_operation: true` *together with* `clear_room_controls: true` is redundant. Use one: `clear_room_controls` wipes everything first, the delete-operation flag marks individual files as tombstones.
- `firmware_id` in a provision is `EndpointFirmware.id`, not a model-name string. Look it up first.
- Cisco endpoint **passwords** can only be reset, not read. To set a new one, send `set_password: true` plus `password: "..."` (explicit) or `standard_password: true` (use the customer's configured list).
- `EndpointStatus.has_direct_connection` is a string `"True"` / `"False"`, not a bool. The status payload mixes formats.
- For Teams MTR / Webex endpoints, **provisioning is limited** to what the respective cloud API supports — most fields are no-ops.
