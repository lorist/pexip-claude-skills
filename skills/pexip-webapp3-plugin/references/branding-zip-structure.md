# Branding ZIP Structure Reference

Anatomy of a Pexip Infinity webapp3 branding ZIP — the packaging format for
plugins, images, and meeting UI customisation.

---

## Directory Layout

A branding ZIP contains a single top-level `webapp3/branding/` directory:

```
webapp3/
  branding/
    manifest.json              ← Plugin registry + image mappings
    plugins/
      plugin-a/
        index.html             ← Plugin entry point
        assets/
          index-abc123.js      ← Bundled plugin code
      plugin-b/
        index.html
        assets/
          index-def456.js
    images/
      jumbotron.jpg            ← Background image (1920×1080)
      logo.png                 ← Logo (336×160 or 168×80)
      card.jpg                 ← Meeting card (640×360)
    audio/
      ring.mp3                 ← Custom ringtone (optional)
```

## manifest.json Schema

```json
{
  "plugins": [
    {
      "src": "./plugins/plugin-a/index.html",
      "sandboxValues": [
        "allow-same-origin",
        "allow-popups",
        "allow-popups-to-escape-sandbox",
        "allow-forms",
        "allow-scripts"
      ]
    }
  ],
  "images": {
    "jumbotron": "./images/jumbotron.jpg",
    "logo": "./images/logo.png"
  },
  "applicationConfig": {
    "brandingColor": "#1a1a2e"
  }
}
```

### plugins array

- Lives at **root level** of manifest.json, NOT under `applicationConfig`
- Each entry has `src` (path to index.html) and `sandboxValues`
- Order determines load order — first entry loads first

### sandboxValues reference

| Value | Required for | Notes |
|---|---|---|
| `allow-scripts` | **All plugins** | Without this, the iframe JS won't execute |
| `allow-same-origin` | `fetch()`, cookies | Required for any network call from the plugin |
| `allow-popups` | `window.open()` | Required if plugin opens external links |
| `allow-popups-to-escape-sandbox` | Popup navigation | Required alongside `allow-popups` |
| `allow-forms` | Form submission | Required if plugin uses `showForm()` |

**Default recommendation:** include all five values unless you have a specific
reason to restrict.

### src path conventions

Two conventions exist in the wild:

1. `"./plugins/my-plugin/index.html"` — standard, plugin under `plugins/`
2. `"./branding/my-plugin/index.html"` — older convention, plugin under `branding/`

Both work. When parsing an existing branding ZIP for plugin installation,
check both paths. If only `./branding/` is handled, plugins using that
convention resolve their ID to "branding" instead of the real plugin name.
**(field-tested)**

Some brandings from older Pexip versions have plugin folders directly at the
ZIP root (outside `plugins/`). During installation, relocate these into
`plugins/` for consistency.

---

## Webapp Aliases

Webapp aliases route URL paths to brandings:

| URL | Alias maps to |
|---|---|
| `https://meet.example.com/webapp3/m/my-meeting` | Default branding |
| `https://meet.example.com/webapp3/custom-path/m/my-meeting` | Custom branding |

Aliases are managed via the Management API:
`/api/admin/configuration/v1/webapp_alias/`

Each alias has:
- `alias`: the URL path segment (e.g. `custom-path`)
- `webapp_branding`: URI reference to the branding resource
- `webapp_type`: must be `"webapp3"`

---

## Stock Branding Gotcha

The built-in "Pexip webapp3 branding" that ships with a fresh Pexip Infinity
install is a ~152-byte near-empty ZIP. Downloading it via the Management API
works, but re-uploading (even unmodified) fails with:

```
{"branding_file": ["No branding files found"]}
```

**Workaround:** never clone from the stock branding. Instead:
- Clone from a **real** branding that has been uploaded previously, OR
- Start from a locally bundled base ZIP that includes a minimal
  `manifest.json` and at least one asset file

This affects any automated plugin-installation workflow that assumes the
default branding is a valid base. **(field-tested, Pexip v39+)**

---

## Image Sizes

| Slot | Recommended size | Format |
|---|---|---|
| `jumbotron` (background) | 1920 × 1080 | JPEG or PNG |
| `logo` (meeting header) | 336 × 160 (2x) or 168 × 80 (1x) | PNG with transparency |
| `card` (meeting card) | 640 × 360 | JPEG or PNG |
