# Address Books and External Integrations

## The address-book model

```
AddressBook ──┬── Source ──── (external system; defines how to populate the book)
              ├── Group ───── (folder)
              └── Item ────── (entry: SIP / H.323 / phone / email)
```

- `AddressBook` is the top-level book. Endpoints pull a book to populate their on-screen directory.
- A book can have one or more **Sources** — each Source defines an automatic feed (CMS users, Pexip spaces, VCS registrations, a CSV upload, etc.). Items from a source are **read-only** to humans; sync overwrites them.
- A book can additionally hold **manual** `Item`s (`Item.is_editable: true`) that humans add directly.
- `Group`s organise items into nested folders.

### AddressBook fields

| Field | Use |
|---|---|
| `title` | Display name. |
| `type` | `0` Mividas-managed · `1` External (an external URL is the source of truth, Mividas just proxies). |
| `external_url` | For `type=1` — where to fetch from. |
| `external_edit_url` | UI link humans click to edit at the source. |
| `external_type` | `CUCM` if the external source is Cisco CUCM; null for generic TMS-style. |
| `soap_search_url` | Read-only — the SOAP endpoint each Cisco endpoint will hit to search this book. |

## Source types (`CreateSourceTypeEnum`)

What each Source pulls from:

| `type` | Source |
|---|---|
| `epm` | Registered endpoints in Mividas Rooms (auto-built directory of every room). |
| `cms_user` | CMS End Users. |
| `cms_spaces` | CMS CoSpaces. |
| `pexip_spaces` | Pexip Conferences. |
| `vcs` | VCS/Expressway registrations. |
| `tms` | Cisco TMS via SOAP. |
| `seevia` | Seevia (Norwegian directory service). |
| `csv` | One-off CSV / Excel upload. |
| `manual_link` | Copy of items from another book (one-way clone). |
| `merge_address_book` | Copy of another address book (merged in). |
| `ldap` | Generic LDAP. |

Each source can have a `prefix` — added to every item's name on display (e.g. `"CMS / "` to disambiguate sources in the directory).

## Working with Sources

```python
# Create a source feed (CMS spaces) on book 4:
src = c.post("/addressbook/4/source/", {
    "title":  "CMS spaces — engineering",
    "type":   "cms_spaces",
    "prefix": "Eng / ",
})

# Trigger a manual sync:
c.post("/addressbook/4/sync/", {})

# Read what links this source has produced:
items = c.list("/addressbook/4/source_links/", params={})
```

| Endpoint | Use |
|---|---|
| `POST /addressbook/{id}/source/` | Add a source feed. |
| `GET /addressbook/{id}/source/{source_id}/` | Inspect. |
| `PUT/PATCH .../source/{source_id}/` | Update. |
| `POST /addressbook/{id}/remove_source/` | Remove. Body: `{id: <source_id>}`. |
| `POST /addressbook/{id}/check_source_links/` | Get currently-linked source items. |
| `POST /addressbook/{id}/make_source_editable/` | Convert a sourced sub-tree to manually-editable items. Body: `{id: <source_id>}`. One-way. |
| `POST /addressbook/{id}/sync/` | Force a sync of every source. |

For CSV/Excel sources, the upload flow is:

1. `POST /addressbook/{id}/parse_csv_excel_headers/` with `{url: <signed URL>}` or `{file: <upload>}`. Returns `headers[]` — the columns in the file.
2. Map those columns to address-book fields client-side.
3. `POST /addressbook/{id}/source/` with `type: csv` + the mapping.

## Items (`/addressbook_item/`)

```python
c.post("/addressbook_item/", {
    "group":  42,                        # Group.id
    "type":   10,                        # 0 VirtualRoom · 10 PhysicalRoom · 20 Person
    "title":  "Conference Room B",
    "sip":    "confroom-b@example.com",
    "h323":   "confroom-b",
    "tel":    "+1-555-0123",
    "email":  "confroom-b@example.com",
    "description": "Building 2, floor 3",
})
```

Bulk create:

```python
c.post("/addressbook_item/bulk_create/", {
    "group":       42,
    "overwrite":   True,            # delete-then-recreate the group's items
    "items":       [
        {"title": "...", "sip": "...", "type": 10},
        # ...
    ],
})
```

## Groups (`/addressbook_group/`)

Nested folders within a book. `parent` is null at the root. Each group has its own `is_editable` reflecting whether the *book's* manual items can live there (sourced items are usually read-only).

## Providers / probes for sources

`GET /addressbook/providers/` returns `ProvidersResponse` — discovered CMS, VCS, manual, and LDAP providers visible to the current customer. Use this to populate "which CMS Call Bridge to source from" UIs.

## Default address books per customer

`CustomerSettings`:

- `default_address_book` — the customer-wide default.
- `default_portal_address_book` — used by the Portal end-user booking interface.
- `default_core_address_book` — used by Core search ("find a room to dial").

`POST /addressbook/search_in_default/?group=&q=` is the search endpoint that hits the customer's `default_core_address_book`.

## Endpoint default book

`Endpoint.default_address_book` overrides the customer default for a specific room. `Endpoint.hide_from_addressbook` keeps a room out of every book even when its EPM source would normally include it.

---

# Calendar / Webex / CUCM integrations

These are the credential records that authorise Mividas to reach external systems for endpoint management or calendar sync.

| Resource | Drives |
|---|---|
| `/ews_credential/` | EWS Basic / OAuth — calendar polling against Exchange / Office 365. |
| `/ews_calendar/` | One specific room mailbox bound to one specific endpoint. |
| `/msgraph_credential/` | Microsoft Graph (calendar + Teams Devices). |
| `/msgraph_oauth/` | OAuth credential record (`OAuthCredential`) for Graph. |
| `/webex_integrations/` | Webex Device API — for cloud-registered Cisco Webex endpoints. |
| `/cucm_integrations/` | Cisco Unified CM — sync endpoints from CUCM device pool. |

## OAuth model

`OAuthCredential` is shared across EWS / Graph / Webex:

| Field | Notes |
|---|---|
| `type` | `0` EWS · `10` Graph · `11` Graph (Teams Devices) · `20` Webex Device · `21` Webex Meeting · `22` Webex Meeting G2G-tenant. |
| `client_id`, `tenant_id`, `secret` | From the IdP application registration. |
| `use_app_authorization` | App-only auth vs delegated. |
| `callback_url` | Returned at create time; redirect URI to add to the IdP app config. |
| `has_secret` | Read-only — has the secret been stored. |

Typical flow:

1. Create the `OAuthCredential` via POST.
2. Read back `callback_url` and configure it in Azure AD / Webex's admin console.
3. Either drive the user-consent flow (the spec doesn't expose this — happens in the Mividas UI), or for app-only set `use_app_authorization: true` and confirm with a test sync.
4. Use the credential ID on the integration record (`EWSCredentials.oauth_credential.id`, `MSGraphCredentials.oauth_credential.id`, etc.).

`has_secret` tells you whether the credential is "configured but unsynced" vs "ready". `last_sync_error` on each integration record surfaces the failure mode.

## EWS — calendar sync

```python
ews = c.post("/ews_credential/", {
    "username":         "rooms@example.com",
    "oauth_credential": {"id": 12},                    # or use "password" for Basic
    "server":           "outlook.office365.com",       # blank → auto-discover
    "enable_sync":      True,
})

# Add specific room calendars:
c.post("/ews_calendar/", {
    "credentials": ews["id"],
    "username":    "boardroom@example.com",
    "endpoint":    42,                                  # which Mividas Endpoint to tie this room to
})

# Force a one-off sync:
c.post(f"/ews_calendar/{cal['id']}/sync_calendar/", {
    "username":  "boardroom@example.com",
    "ts_start":  "2026-06-12T00:00:00Z",
    "ts_stop":   "2026-06-13T00:00:00Z",
    "dry_run":   True,
})
```

`SyncCalendarResponse` returns `{new, changed, removed, video_meetings, non_video_meetings}` counters. `dry_run: true` returns the same shape without writing.

`EWSCredentials.is_working` reflects whether the last sync succeeded. `EWSCredentials.token_update_url` is where a re-auth flow can land tokens (handled in the UI).

## MS Graph — calendar + Teams MTR

Same shape but talks to Graph API. `MSGraphCredentials.integration_type`: `0` EWS · `10` MS Graph · `11` Graph Teams Devices · `20` Webex API · `30` CUCM. Each one means a different Graph API surface is used.

For Teams MTR provisioning, use `integration_type: 11` (Graph Teams Devices).

## Webex Device API

```python
webex = c.post("/webex_integrations/", {
    "title":            "Customer Webex tenant",
    "oauth_credential": {"id": 19},
    "enable_sync":      True,
})

c.get(f"/webex_integrations/{webex['id']}/pending_devices/")
c.get(f"/webex_integrations/{webex['id']}/all_devices/")
# Sync brings devices in as Endpoints:
c.post(f"/webex_integrations/{webex['id']}/sync/", {})
```

After sync, devices appear as `Endpoint` rows with `connections[]` containing a `WebexCredentials` connection.

## CUCM integration

```python
cucm = c.post("/cucm_integrations/", {
    "title":    "Site-A CUCM",
    "hostname": "cucm.example.com",
    "username": "mividas-api",
    "password": "...",
    "enable_sync": True,
})
c.post(f"/cucm_integrations/{cucm['id']}/sync/", {})
```

Returns a paginated list of `Endpoint` rows for the devices brought across. `pending_devices/` shows devices in CUCM that haven't been claimed yet.

## Common pitfalls

- **Address-book sync** runs on a Mividas-side schedule (configured at the Source level — not exposed in the OpenAPI). `POST /addressbook/{id}/sync/` triggers an immediate sync but a future-scheduled sync still runs on top — don't expect "manual sync" to disable the cadence.
- A source `prefix` is applied **at display** — the underlying items still carry the source's clean name. Don't try to "strip" the prefix on read.
- Calendar sync requires the room mailbox's UPN/SMTP address. If a customer has `room1@onmicrosoft.com` aliased to `room1@example.com`, use the UPN.
- For Cisco CUCM endpoints, the device's authentication (CUCM phone username/password) is separate from CUCM's API auth (the `CucmCredentials`). Claiming a device via sync **doesn't** automatically give Mividas the per-device credentials to provision it.
- `OAuthCredential.type` is mutable but rarely should be changed after credentials are bound — different types use different scopes.
- `EWSCredentials.password` is used only for Basic auth. If you supply both `password` and `oauth_credential`, OAuth wins.
