# Avatar Requirements Reference

Complete implementation guide for `/policy/v1/participant/avatar/<alias>` — the
endpoint Pexip v40+ calls to fetch participant photos during a conference.

---

## Format Requirements (Non-Negotiable)

Pexip avatar_request has strict undocumented requirements. Violating any one
causes a silent fallback to initials with no error logged on the Pexip side.

| Requirement | Detail |
|---|---|
| Image format | JPEG only (not PNG, not WebP, not BMP) |
| Dimensions | Must exactly match `width` and `height` from query params |
| Color space | RGB (not RGBA, not palette/P mode) |
| Content-Type | `image/jpeg` |
| Cache-Control | `public, max-age=300` (recommended) |

---

## User Lookup Chain

Pexip sends these query parameters with the avatar request:

| Parameter | Purpose |
|---|---|
| `idp_uuid` | Keycloak user sub (most precise) |
| `remote_display_name` | Display name from IdP |
| `service_name` | Conference alias (for realm resolution) |
| `width` | Requested image width (default 256) |
| `height` | Requested image height (default 256) |

The alias path parameter contains the participant's SIP/alias identifier.

### Three-stage lookup:

```python
# 1. By idp_uuid (most precise)
if idp_uuid:
    kc_user = keycloak_find_user_by_idp_uuid(kc_base, token, realm, idp_uuid)

# 2. By alias username (strip scheme prefix, try variants)
if not kc_user and alias_user:
    for uname in [alias_user, alias_user.replace(" ", ".")]:
        users = kc_request(f"admin/realms/{realm}/users?username={uname}&exact=true")
        if users:
            kc_user = users[0]
            break

# 3. By display name (first + last)
if not kc_user and remote_display_name:
    parts = remote_display_name.split(" ", 1)
    first, last = parts[0], parts[1] if len(parts) > 1 else ""
    users = kc_request(
        f"admin/realms/{realm}/users?firstName={first}&lastName={last}&exact=true"
    )
    if users:
        kc_user = users[0]
```

Extract the alias username from the path parameter:
```python
alias_user = re.sub(r"^[a-zA-Z0-9+.\-]+:", "", alias).split("@")[0]
```

---

## PIL Image Processing Pipeline

```python
import base64
import io
from PIL import Image

def process_avatar(avatar_base64, width, height):
    """Decode, convert, resize, and re-encode as JPEG."""
    raw_bytes = base64.b64decode(avatar_base64)
    img = Image.open(io.BytesIO(raw_bytes))

    # MUST convert to RGB -- RGBA causes silent fallback to initials
    img = img.convert("RGB")

    # MUST match exact requested dimensions
    img = img.resize((width, height), Image.LANCZOS)

    buf = io.BytesIO()
    # MUST save as JPEG -- PNG causes silent fallback
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()
```

---

## Keycloak User Profile Schema

The avatar is stored as a base64-encoded string in a custom Keycloak user attribute.
The KC User Profile schema must be configured with a generous max length:

```json
{
  "name": "avatarBase64",
  "displayName": "Avatar (Base64)",
  "validations": {
    "length": {
      "max": 65536
    }
  },
  "annotations": {},
  "permissions": {
    "view": ["admin", "user"],
    "edit": ["admin", "user"]
  }
}
```

The default KC attribute max length is 255 characters, which is far too small for
even a 64x64 JPEG. Without increasing this, avatar uploads silently truncate.

---

## Error Handling: 404 vs 500

**404** — Pexip caches 404 responses per session. Once a 404 is returned for a
participant, Pexip will NOT retry until that participant fully disconnects and
rejoins. Reserve 404 for definitive "no avatar exists" situations:

- No Keycloak user found for any lookup method
- User found but has no `avatarBase64` attribute
- Image decode/resize failure (corrupt data)

**500** — Pexip treats 500 as a transient error and may retry (behavior varies
by version). Use 500 for genuinely transient failures:

- Keycloak authentication failed (token expired)
- Network timeout to Keycloak

In practice, return 404 for all errors. The retry behavior on 500 is inconsistent
and may cause request storms during Keycloak outages.

```python
# Recommended: always return 404 tuple for errors
return ("", 404)

# Do NOT return Flask's abort(404) -- the HTML error page confuses Pexip
```

---

## Complete Flask Endpoint

```python
@policy_bp.route("/policy/v1/participant/avatar/<path:alias>", methods=["GET"])
def participant_avatar(alias):
    """Serve participant avatar as JPEG.

    Pexip v40+ avatar_request. Returns KC user's avatarBase64 attribute
    as image/jpeg at the requested dimensions, or 404.
    """
    try:
        remote_display_name = request.args.get("remote_display_name", "").strip()
        idp_uuid = request.args.get("idp_uuid", "").strip()
        service_name = request.args.get("service_name", "").strip()

        try:
            width = int(request.args.get("width", "256"))
            height = int(request.args.get("height", "256"))
        except ValueError:
            width = height = 256

        # Extract username from alias path
        alias_user = re.sub(r"^[a-zA-Z0-9+.\-]+:", "", alias).split("@")[0]

        # Resolve KC realm from service_name -> demo config -> idp_group
        realm = resolve_realm_from_service(service_name)
        if not realm:
            return ("", 404)

        # Authenticate to Keycloak
        token = keycloak_get_token(kc_url, kc_user, kc_pass)
        if not token:
            return ("", 404)

        # Three-stage user lookup
        kc_user_row = lookup_user(kc_base, token, realm, idp_uuid, alias_user, remote_display_name)
        if not kc_user_row:
            return ("", 404)

        # Get avatar attribute
        b64 = get_user_attribute(kc_base, token, realm, kc_user_row["id"], "avatarBase64")
        if not b64:
            return ("", 404)

        # Decode, convert RGB, resize, encode JPEG
        try:
            raw_bytes = base64.b64decode(b64)
            img = Image.open(io.BytesIO(raw_bytes))
            img = img.convert("RGB").resize((width, height), Image.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=90)
            out_bytes = buf.getvalue()
        except Exception:
            return ("", 404)

        return Response(
            out_bytes,
            mimetype="image/jpeg",
            headers={"Cache-Control": "public, max-age=300"},
        )

    except Exception:
        return ("", 404)
```

---

## Enabling Avatar Lookup on Pexip

Avatar requests are only sent when `enable_avatar_lookup` is enabled on the
**policy_server** resource in Pexip Infinity admin, NOT on the conference or
VMR. This is a separate boolean from the policy profile itself.

If avatars are never requested despite a working endpoint, check:
1. Pexip admin > Policy Server configuration > `enable_avatar_lookup` = True
2. The policy server URL is correct and reachable from conferencing nodes
3. The conference is using a policy profile that references this policy server
