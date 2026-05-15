# Avatar Policy Server Example

Minimal Flask server demonstrating the Pexip Infinity v40+ `avatar_request`
endpoint with proper JPEG format, exact dimension matching, and 404 handling.

## What it does

Serves participant avatars as JPEG images at the exact dimensions Pexip requests.
Uses a stubbed in-memory user database — replace with Keycloak or another IdP
lookup in production.

## Setup

```bash
pip install flask Pillow
python app.py
```

Server runs on `http://localhost:5001`.

## Configure Pexip Infinity

1. Go to Pexip admin > Policy Server configuration
2. Enable `enable_avatar_lookup`
3. Set policy server URL to include this server

## Test with curl

```bash
# Request avatar (returns JPEG or 404)
curl -o avatar.jpg "http://localhost:5001/policy/v1/participant/avatar/user-001?idp_uuid=user-001&width=128&height=128"

# Verify it is JPEG
file avatar.jpg
```

## Key patterns demonstrated

1. **JPEG only** — Pexip silently falls back to initials for PNG/WebP/other formats
2. **Exact dimensions** — must match the `width` and `height` query parameters
3. **RGB color space** — `img.convert("RGB")` before saving (RGBA causes fallback)
4. **404 caching** — Pexip caches 404 per session; never return 404 for transient errors
5. **User lookup chain** — idp_uuid first, then alias username (add display name in production)

## Production considerations

- Replace the `USERS` dict with Keycloak admin API lookups
- Add the `avatarBase64` attribute to KC User Profile with `maxLength: 65536`
- Use a three-stage lookup: idp_uuid -> username -> firstName+lastName
- Consider caching avatar bytes in-memory (LRU) to reduce KC API calls
- See `references/avatar-requirements.md` for the complete implementation
