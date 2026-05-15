# Management API — Branding Endpoints Reference

CRUD operations for webapp3 brandings and aliases via the Pexip Infinity
Management Node REST API.

**Base URL:** `https://<management-node>/api/admin/configuration/v1/`

All requests require admin credentials (Basic Auth or OAuth2 bearer token).
Self-signed certificates: use `verify=False` or configure CA trust.

---

## List brandings

```
GET /api/admin/configuration/v1/webapp_branding/
```

Query parameters:
- `limit` / `offset` — pagination (default limit: 20)
- `webapp_type` — filter by `"webapp3"` or `"webapp2"`

**curl:**
```bash
curl -sk -u admin:password \
  "https://mgmt.example.com/api/admin/configuration/v1/webapp_branding/?webapp_type=webapp3&limit=100"
```

**Python:**
```python
import requests

resp = requests.get(
    f"https://{mgmt}/api/admin/configuration/v1/webapp_branding/",
    params={"webapp_type": "webapp3", "limit": 100},
    auth=(user, password),
    verify=False,
)
brandings = resp.json()["objects"]
for b in brandings:
    print(f"{b['uuid']}  {b['name']}")
```

Response object fields:

| Field | Type | Description |
|---|---|---|
| `uuid` | string | Unique ID (used in download/delete URLs) |
| `name` | string | Display name |
| `description` | string | Optional description |
| `webapp_type` | string | `"webapp3"` |
| `resource_uri` | string | API self-link |

---

## Download branding ZIP

```
GET /api/admin/configuration/v1/webapp_branding/{uuid}/download/
```

Returns the branding ZIP file as `application/zip`.

**curl:**
```bash
curl -sk -u admin:password \
  "https://mgmt.example.com/api/admin/configuration/v1/webapp_branding/abc-123/download/" \
  -o branding.zip
```

**Python:**
```python
resp = requests.get(
    f"https://{mgmt}/api/admin/configuration/v1/webapp_branding/{uuid}/download/",
    auth=(user, password),
    verify=False,
)
with open("branding.zip", "wb") as f:
    f.write(resp.content)
```

---

## Upload new branding

```
POST /api/admin/configuration/v1/webapp_branding/
```

Multipart form data:

| Field | Type | Required | Value |
|---|---|---|---|
| `name` | string | Yes | Display name (include plugin version for traceability) |
| `description` | string | No | Optional description |
| `webapp_type` | string | Yes | `"webapp3"` |
| `branding_file` | file | Yes | The ZIP file |

**curl:**
```bash
curl -sk -u admin:password \
  -F "name=My Branding v2" \
  -F "webapp_type=webapp3" \
  -F "branding_file=@branding-modified.zip" \
  "https://mgmt.example.com/api/admin/configuration/v1/webapp_branding/"
```

**Python:**
```python
with open("branding-modified.zip", "rb") as f:
    resp = requests.post(
        f"https://{mgmt}/api/admin/configuration/v1/webapp_branding/",
        files={"branding_file": ("branding.zip", f, "application/zip")},
        data={"name": "My Branding v2", "webapp_type": "webapp3"},
        auth=(user, password),
        verify=False,
    )
new_uuid = resp.json()["uuid"]
```

The response includes the new branding's `uuid` and `resource_uri`.

---

## Update branding metadata

```
PATCH /api/admin/configuration/v1/webapp_branding/{id}/
```

Only metadata fields (`name`, `description`) can be updated. To change the
ZIP contents, upload a new branding and delete the old one.

**curl:**
```bash
curl -sk -u admin:password -X PATCH \
  -H "Content-Type: application/json" \
  -d '{"name": "My Branding v3"}' \
  "https://mgmt.example.com/api/admin/configuration/v1/webapp_branding/42/"
```

**Note:** PATCH uses the integer `id` (from `resource_uri`), not the `uuid`.

---

## Delete branding

```
DELETE /api/admin/configuration/v1/webapp_branding/{uuid}/
```

**curl:**
```bash
curl -sk -u admin:password -X DELETE \
  "https://mgmt.example.com/api/admin/configuration/v1/webapp_branding/abc-123/"
```

Returns 204 No Content on success. Cannot delete a branding that is currently
referenced by a webapp alias.

---

## Webapp Aliases

### List aliases

```
GET /api/admin/configuration/v1/webapp_alias/
```

### Create alias

```
POST /api/admin/configuration/v1/webapp_alias/
```

```json
{
  "alias": "custom-path",
  "webapp_type": "webapp3",
  "webapp_branding": "/api/admin/configuration/v1/webapp_branding/42/"
}
```

### Update alias to point to new branding

```
PATCH /api/admin/configuration/v1/webapp_alias/{id}/
```

```json
{
  "webapp_branding": "/api/admin/configuration/v1/webapp_branding/99/"
}
```

This is how you deploy a new branding version without changing the user-facing
URL.

### Delete alias

```
DELETE /api/admin/configuration/v1/webapp_alias/{id}/
```

---

## Complete Plugin Installation Flow

Python script that downloads a branding, injects a plugin, uploads, and
re-routes the alias:

```python
import json
import os
import requests
import shutil
import tempfile
import zipfile

def install_plugin(mgmt, user, pw, branding_uuid, alias_id, plugin_dist_dir, plugin_id):
    base = f"https://{mgmt}/api/admin/configuration/v1"
    auth = (user, pw)

    # 1. Download existing branding
    resp = requests.get(f"{base}/webapp_branding/{branding_uuid}/download/",
                        auth=auth, verify=False)
    tmp = tempfile.mkdtemp()
    zip_path = os.path.join(tmp, "branding.zip")
    with open(zip_path, "wb") as f:
        f.write(resp.content)

    # 2. Extract
    extract_dir = os.path.join(tmp, "extracted")
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(extract_dir)

    # 3. Find manifest.json
    manifest_path = None
    for root, dirs, files in os.walk(extract_dir):
        if "manifest.json" in files:
            manifest_path = os.path.join(root, "manifest.json")
            break
    if not manifest_path:
        raise RuntimeError("No manifest.json found in branding ZIP")

    branding_root = os.path.dirname(manifest_path)

    # 4. Copy plugin dist into plugins/
    dest = os.path.join(branding_root, "plugins", plugin_id)
    shutil.copytree(plugin_dist_dir, dest)

    # 5. Update manifest.json
    with open(manifest_path) as f:
        manifest = json.load(f)
    manifest.setdefault("plugins", [])
    manifest["plugins"].append({
        "src": f"./plugins/{plugin_id}/index.html",
        "sandboxValues": [
            "allow-same-origin", "allow-popups",
            "allow-popups-to-escape-sandbox", "allow-forms", "allow-scripts",
        ],
    })
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    # 6. Re-zip
    new_zip = os.path.join(tmp, "branding-modified.zip")
    with zipfile.ZipFile(new_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(extract_dir):
            for file in files:
                abs_path = os.path.join(root, file)
                arc_name = os.path.relpath(abs_path, extract_dir)
                zf.write(abs_path, arc_name)

    # 7. Upload new branding
    with open(new_zip, "rb") as f:
        resp = requests.post(
            f"{base}/webapp_branding/",
            files={"branding_file": ("branding.zip", f, "application/zip")},
            data={"name": f"Branding with {plugin_id}", "webapp_type": "webapp3"},
            auth=auth, verify=False,
        )
    new_uuid = resp.json()["uuid"]
    new_uri = resp.json()["resource_uri"]

    # 8. Re-route alias
    requests.patch(
        f"{base}/webapp_alias/{alias_id}/",
        json={"webapp_branding": new_uri},
        auth=auth, verify=False,
    )

    # 9. Optionally delete old branding
    requests.delete(f"{base}/webapp_branding/{branding_uuid}/",
                    auth=auth, verify=False)

    shutil.rmtree(tmp)
    return new_uuid
```
