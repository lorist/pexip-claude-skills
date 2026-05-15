# Event Sink Debugging — Expanded Reference

Detailed troubleshooting for Pexip Infinity Event Sink delivery failures,
missing events, configuration issues, and timing problems.

---

## Configuration Verification

### Step 1: Check event sink exists

```
GET /api/admin/configuration/v1/event_sink/
```

Verify:
- Event sink resource exists and is not deleted
- URL points to your receiver (check for stale ngrok URLs)
- Event sink is assigned to the correct location(s)

### Step 2: Check location coverage

**Critical:** Event sink location must contain **transcoding** nodes — proxy-only locations reject event sinks silently. **(field-tested)**

```
GET /api/admin/configuration/v1/conference_node/
```

For each node in the event sink's location:
- `role` must include transcoding (not proxy-only)
- Node must be online and healthy

### Step 3: Test reachability

From a network that can reach the conferencing nodes:
```bash
curl -k -X POST https://<event-sink-url>/ \
  -H "Content-Type: application/json" \
  -d '{"test": true}'
```

Your receiver should return `200 OK` for any POST.

### Step 4: Check resource ID stability

Event sink resource IDs change on delete+recreate. If your code references a specific event sink ID, it may be stale. Always look up by name. **(field-tested)**

```python
# WRONG — hardcoded ID
event_sink = fetch("/api/admin/configuration/v1/event_sink/42/")

# CORRECT — lookup by name
sinks = fetch("/api/admin/configuration/v1/event_sink/?name=PDP+Event+Sink")
event_sink = sinks["objects"][0] if sinks["objects"] else None
```

---

## Event Type Reference

### Conference lifecycle events

| Event | When it fires | Key fields |
|---|---|---|
| `conference_started` | First participant joins | `conference_id`, `conference_alias`, `start_time` |
| `conference_updated` | Conference properties change (lock, name) | `conference_id`, changed fields |
| `conference_ended` | Last participant leaves | `conference_id`, `end_time`, `duration` |

### Participant lifecycle events

| Event | When it fires | Key fields |
|---|---|---|
| `participant_connected` | Participant joins the conference | `participant_id`, `conference_id`, `display_name`, `role`, `call_direction` |
| `participant_updated` | State change: admitted from lobby, role change, media change, mute/unmute | `participant_id`, changed fields |
| `participant_disconnected` | Participant leaves | `participant_id`, `disconnect_reason`, `duration` |

### Other events

| Event | When it fires |
|---|---|
| `presentation_started` | Participant begins sharing screen |
| `presentation_ended` | Screen sharing stops |
| `recording_started` / `recording_ended` | Recording lifecycle |
| `transfer` | Participant transferred between conferences |

---

## Timing Expectations

- Event sink delivery can lag **1-5 seconds** behind the actual event **(common pattern)**
- Under load, lag can increase to **10-30 seconds**
- Events are NOT guaranteed to arrive in order — use timestamps, not arrival order
- `participant_connected` and `participant_updated` can arrive as a pair for a single admission, sometimes out of order

### Timing-critical operations

**Do not rely on event sink for timing-critical operations.** **(field-tested)**

For operations that must happen immediately when a participant is admitted:
- Trigger recalculation directly on the `/admit` endpoint
- Use event sink as a secondary/backup path
- Event sink delivery from Infinity is particularly unreliable in dev environments with ngrok

---

## Missing Events Troubleshooting

### No events at all

```
1. Is the event sink resource configured?
   GET /api/admin/configuration/v1/event_sink/
   → If empty: create event sink

2. Is the URL correct?
   → Stale ngrok URL? Update it.

3. Is the location correct?
   → Must contain transcoding nodes, not proxy-only

4. Is the event sink stuck?
   → Restart: DELETE existing + POST new
   → Use timestamp in description to distinguish recreated instances

5. Can Pexip reach the URL?
   → Check firewall, TLS, DNS from conferencing node network
```

### Some events missing

```
1. Which events are missing?
   → participant_updated for lobby admission? Check lobby is actually involved.
   → conference_ended? May have already fired if you started listening late.

2. Is the participant an ADP leg?
   → ADP/SIP participants DO fire participant_connected  **(common pattern)**
   → But get service_type=conference BEFORE lobby, unlike WebRTC participants

3. Is the event getting debounced?
   → Check your debounce logic isn't too aggressive
   → 5-30s TTL is the recommended range

4. Is the receiver returning 200 fast enough?
   → Pexip expects fast 2xx response
   → If your processing is slow, ACK immediately and process async
```

### Duplicate events

```
1. participant_connected + participant_updated pair
   → Normal for admission from lobby  **(common pattern)**
   → Debounce with key: conference_alias:participant_uuid

2. conference_ended firing multiple times
   → Can happen if participants rejoin rapidly
   → Use idempotent handler (check if already processed)

3. Same event arriving twice
   → Pexip may retry on perceived timeout
   → Use event ID or participant_id+timestamp for dedup
```

---

## ngrok Inspector for Development

During development with ngrok, use the inspector to verify events:

1. Open `http://127.0.0.1:4040` in a browser
2. Filter to POST requests to your event sink path
3. Inspect the JSON body of each event
4. Check response codes (should be 200)

### Common ngrok issues

- **Tunnel expired** → events stop arriving, no error in Pexip logs until timeout
- **Wrong tunnel** → if you have multiple ngrok tunnels, verify the event sink URL points to the right one
- **Free tier rate limits** → under heavy event load, ngrok may throttle

---

## Event Sink Restart Procedure

When an event sink is stuck and not delivering events: **(field-tested)**

### Via Management API
```python
# 1. Find the current event sink
sinks = fetch("GET", "/api/admin/configuration/v1/event_sink/")
sink = next(s for s in sinks["objects"] if "PDP" in s["name"])

# 2. Delete it
fetch("DELETE", f"/api/admin/configuration/v1/event_sink/{sink['id']}/")

# 3. Recreate with same settings
from datetime import datetime
fetch("POST", "/api/admin/configuration/v1/event_sink/", json={
    "name": f"PDP Event Sink",
    "description": f"Recreated {datetime.utcnow().isoformat()}",
    "url": sink["url"],
    "location": sink["location"],  # Must be location with transcoding nodes
})
```

### Via Django admin
1. Navigate to Platform > Event Sink in Django admin
2. Delete the stuck instance
3. Create a new one with the same URL and location

### Post-restart verification
- Make a test call to a conference
- Check ngrok inspector / receiver logs for incoming events
- Allow up to 60s for the new event sink to start delivering
- If still not working, check location assignment (transcoding nodes required)

---

## Polling Fallback Pattern

When event sink delivery is unreliable, implement a polling fallback: **(field-tested)**

```python
# Hybrid approach: event sink + polling
# 1. Process events from event sink (primary, fast)
# 2. Poll Management API every N seconds as backup

# Poll for active conferences
GET /api/admin/status/v1/conference/

# Poll for participants in a conference
GET /api/admin/status/v1/participant/?conference=<conference_id>
```

Use this pattern for:
- Development environments where ngrok is unreliable
- Critical operations where event sink lag is unacceptable
- Environments where event sink has known delivery issues

Do NOT use this as a replacement for event sink in production — it adds Management API load and has its own latency.
