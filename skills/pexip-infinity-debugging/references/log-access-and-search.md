# Log Access and Search

How to access, search, and download Pexip Infinity logs for debugging.

---

## Log Types

Pexip Infinity has five log types, each showing different information:

| Log type | What it shows | When to use |
|---|---|---|
| **Support log** | High-signal call lifecycle events: policy decisions, participant joins/leaves, conference creation/destruction, errors | First stop for most debugging — policy rejections, participant failures, event sink issues |
| **Developer log** | Low-level protocol traces: full SIP signaling, ICE negotiation, TLS handshakes, media setup | SIP call failures, codec issues, certificate problems, network-level debugging |
| **Administrator log** | Configuration changes: resource create/update/delete, service restarts, replication events | When changes aren't taking effect, tracking who changed what |
| **Connectivity log** | Network/firewall test results from Pexip's built-in connectivity checks | Firewall rules, NAT traversal, TURN server reachability |
| **Audit log** | Admin UI and API actions with user attribution | Security review, tracking admin actions |

---

## Django Admin Access

Pexip Infinity logs are accessed through the Django admin interface on the management node.

### URLs

```
https://<management-fqdn>/admin/logview/log/support/
https://<management-fqdn>/admin/logview/log/developer/
https://<management-fqdn>/admin/logview/log/administrator/
```

The connectivity and audit logs are at:
```
https://<management-fqdn>/admin/logview/log/connectivity/
https://<management-fqdn>/admin/platform/auditlog/
```

### Authentication

Log access requires a Django admin session. The standard login flow:

1. GET the login page at `https://<management-fqdn>/admin/login/`
2. Extract the `csrfmiddlewaretoken` from the form (hidden input)
3. POST credentials with the CSRF token to the same URL
4. Use the session cookie for subsequent requests

**Important:** This is Django admin auth, separate from the Management API Basic Auth. The same username/password may work for both, but the session mechanism is different.

### Programmatic access

```python
import requests

session = requests.Session()
session.verify = False  # Self-signed certs common on Pexip

# Get CSRF token
login_page = session.get(f"https://{mgmt_fqdn}/admin/login/")
csrf = session.cookies.get("csrftoken")

# Login
session.post(f"https://{mgmt_fqdn}/admin/login/", data={
    "csrfmiddlewaretoken": csrf,
    "username": username,
    "password": password,
    "next": "/admin/"
}, headers={"Referer": f"https://{mgmt_fqdn}/admin/login/"})

# Access support log with search
resp = session.get(f"https://{mgmt_fqdn}/admin/logview/log/support/", params={"q": "externalpolicy"})
```

---

## Search Syntax

Pexip log search is simple but effective:

- **Single term only** — no AND/OR operators, no boolean logic **(common pattern)**
- **Case-insensitive** — `externalpolicy` matches `ExternalPolicy`
- **Searches across all pages** — even for large paginated logs, search filters the full dataset
- **URL parameter:** `?q=search_term` — use `+` for spaces (e.g., `?q=Invalid+service+configuration`)

### Effective search terms by problem

| Problem | Search term | Why this term |
|---|---|---|
| Policy response issues | `externalpolicy` | Pexip logs all external policy interactions under this keyword |
| Invalid PIN configuration | `Invalid service configuration` | Exact error message Pexip logs |
| Participant join failures | `participant` | Catches all participant lifecycle events |
| Specific alias | The alias itself (e.g., `pdp001-demo001`) | Filters to one conference |
| Event sink issues | `event_sink` or `eventsink` | Both forms appear in logs |
| SIP failures | `sip` | Broad but catches all SIP signaling |
| Authentication | `idp` or `authentication` | IdP-related events |
| Alias matching | `Alias didn't match` | Exact error prefix |

### Tips

- Use the most **specific** keyword available — `externalpolicy` is better than `policy`
- If searching by alias, use just the alias name without `sip:` prefix or `@domain` suffix
- For time-based investigation, note that all log timestamps are **UTC** — convert local time before correlating events

---

## Timestamps

All Pexip Infinity log timestamps are in **UTC**, regardless of the management node's timezone setting.

When debugging a reported issue:
1. Get the reported time in the user's local timezone
2. Convert to UTC
3. Search the logs in that UTC time range

Log entries typically include timestamps in the format: `YYYY-MM-DD HH:MM:SS,mmm`

---

## Pagination and Large Logs

- Large logs (5MB+) are paginated in the Django admin UI **(common pattern)**
- The search function (`?q=`) filters across ALL pages, not just the current page
- To navigate pages manually, use `?p=N` (0-indexed page number)
- Combining search and pagination: `?q=externalpolicy&p=2`

---

## Downloading Logs

To download a raw log file:

1. Navigate to the log page in Django admin
2. Submit the download form (POST with `download` input field)
3. The response is a raw text file

Programmatic download:
```python
resp = session.post(f"https://{mgmt_fqdn}/admin/logview/log/support/", data={
    "csrfmiddlewaretoken": session.cookies.get("csrftoken"),
    "download": "Download"
}, headers={"Referer": f"https://{mgmt_fqdn}/admin/logview/log/support/"})

with open("support.log", "wb") as f:
    f.write(resp.content)
```

---

## HTML Encoding in Log Entries

Log entries displayed in Django admin are HTML-encoded. When parsing programmatically, decode:

| Encoded | Decoded |
|---|---|
| `&quot;` | `"` |
| `&#x27;` | `'` |
| `&amp;` | `&` |
| `&lt;` | `<` |
| `&gt;` | `>` |

Python: `import html; decoded = html.unescape(raw_entry)`

---

## Log Level Configuration via Management API

### List current log levels
```
GET /api/admin/configuration/v1/log_level/
```
Returns log levels by component name. Each component can be independently set.

### Set a log level
```
PATCH /api/admin/configuration/v1/log_level/<id>/
{"level": "DEBUG"}
```
Valid levels: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`

**Warning:** Setting components to DEBUG generates massive log volumes. Use sparingly and revert after debugging.

### Remote syslog configuration
```
GET /api/admin/configuration/v1/syslog_server/
```
Configure remote syslog forwarding for persistent log storage beyond Pexip's built-in retention.

---

## Quick Reference: Which Log for Which Problem

| Symptom | Check this log first | Then check |
|---|---|---|
| "Alias didn't match" | Support | Developer (for raw HTTP) |
| SIP 488 error | Developer | Support (for context) |
| Participant can't join | Support | Developer (for protocol detail) |
| Event sink not firing | Support | Administrator (for config changes) |
| Changes not taking effect | Administrator | Support (for replication errors) |
| ICE/TURN failure | Support | Connectivity |
| License exhaustion | Support | — |
| Who changed config | Audit | Administrator |
