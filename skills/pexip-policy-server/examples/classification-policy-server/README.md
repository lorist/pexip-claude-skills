# Classification Policy Server Example

Minimal Flask policy server demonstrating Pexip Infinity participant classification
with role ladder, PIN validation, view normalization, and L1 rejection.

## What it does

- **Service Configuration**: Creates virtual conference rooms with PIN protection,
  proper view normalization, and breakout room handling.
- **Participant Properties**: Assigns classification levels based on IdP title
  attribute, implements the 4-tier role ladder (Policy Server > high-level chair >
  low-level guest > non-IdP passthrough), and rejects participants below the
  meeting's classification threshold.

## Setup

```bash
pip install flask
python app.py
```

Server runs on `http://localhost:5000`.

## Configure Pexip Infinity

1. Go to Pexip admin > External Policy Server
2. Set URL to `http://<your-host>:5000` (or use ngrok for remote access)
3. Enable service_configuration and participant_properties

## Test with curl

Service configuration:
```bash
curl "http://localhost:5000/policy/v1/service/configuration?local_alias=meeting-001"
```

Participant with IdP (General = L6, auto-admitted as chair):
```bash
curl -X POST "http://localhost:5000/policy/v1/participant/properties?local_alias=meeting-001&remote_alias=heidi@example.com&idp_uuid=abc123" \
  -H "Content-Type: application/json" \
  -d '{"idp_attributes": {"title": "General", "firstName": "Heidi", "lastName": "Smith"}}'
```

Policy Server participant (always chair):
```bash
curl "http://localhost:5000/policy/v1/participant/properties?local_alias=meeting-001&remote_alias=Policy+Server"
```

## Key patterns demonstrated

1. `_normalize_alias()` — strips `sip:` prefix and `@domain` suffix
2. `_normalize_view()` — maps aliases and typos to valid Infinity values
3. `_json_ok()` vs bare `jsonify()` — correct response wrapping for accept vs reject
4. PIN validation — `allow_guests: true` always paired with `pin`
5. Breakout room stripping — `result.pop("allow_guests", None)`
6. Role ladder — Policy Server checked first, then level-based, then passthrough
7. L1 rejection — uses stored meeting level, bare `jsonify()` for reject

## Limitations

This example uses in-memory state (`_meeting_levels` dict). A production server
needs SQLite-backed conference state with cross-worker dedup. See
`references/classification-lifecycle.md` for the full pattern.
