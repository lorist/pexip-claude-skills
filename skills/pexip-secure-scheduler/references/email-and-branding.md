# Email invites and branding

This file covers everything that **shapes what a meeting looks and
feels like** from the participant's side: the invite email, the
in-meeting branding (theme, view, pinning), the SMTP plumbing,
RTMP streaming destinations, and the i18n surface.

---

## 1. The email pipeline

The Scheduler ships one **EmailTemplate** (singleton — there's no
POST or DELETE) and two `/api/command/` endpoints to render and send
it.

```
EmailTemplate                                    SMTPServer
(subject_template, body_template)                (host, port, user, pass, from, TLS)
       ▲                                                   ▲
       │ Jinja2 evaluated with                             │ used to send
       │ a participant + encounter                         │
       │                                                   │
       └───────┬───────────────────────────────────────────┘
               │
               ▼
   POST /api/command/generate_email   → returns rendered HTML (preview)
   POST /api/command/send_email       → renders AND sends
```

### EmailTemplate

Endpoints under `/api/email_template/` — **read + update only**
(no POST, no DELETE). It's effectively a singleton.

| Field | Type | Default | Notes |
|---|---|---|---|
| `id` | int64, readOnly | — | |
| `subject_template` | string ≤255 | `"Organization"` | Jinja2-rendered subject line |
| `body_template` | string ≤24576 | (a full HTML default — see below) | Jinja2-rendered HTML body |

### Jinja2 variables in scope

The default `body_template` shipped with the Scheduler reveals the
variables in scope:

| Variable | Type | Notes |
|---|---|---|
| `participant_display_name` | string | `participant.display_name` |
| `participant_pin` | string | `participant.pin` |
| `participant_authentication_method` | string | `"PIN"` / `"IDP"` / `""` |
| `participant_identity_provider` | string | The IdP `group_name` (when auth method is IDP) |
| `participant_aliases` | dict `{alias_string: [protocol_strings]}` | The generated aliases for this participant, keyed by alias string with a list of protocols (`SIP`/`H323`/`WEB`) |
| `encounter_name` | string | `encounter.name` |
| `encounter_start_date` | date | iCal-style date object — `.strftime()` works |
| `encounter_start_time` | time | iCal-style time object — `.strftime('%H:%M')` works |
| `encounter_end_time` | time | iCal-style time object |
| `encounter_timezone` | string | The IANA timezone |
| `default_webapp_url` | string | From `global_settings.default_webapp_url` |

The default template iterates `participant_aliases.items()` and emits
a different row per protocol — WEB becomes a hyperlink to the webapp,
SIP/H.323 become a dial string. It also conditionally renders the PIN
row (if `authentication_method == "PIN"`) or the SSO login hint (if
`"IDP"`).

### Default body template (verbatim, abridged)

```html
<!DOCTYPE html>
<html>
  <head>
    <style type="text/css">
      table.joinTable { border: none; width: 520px; text-align: left; border-collapse: collapse; }
      table.joinTable td, table.joinTable th { border: none; padding: 10px 6px 10px 0; }
      td.listItem { color: #777777; }
      /* ... */
    </style>
  </head>
  <body>
    <p><b>Dear {{ participant_display_name }},</b></p>
    <p>The Organization is inviting you to a scheduled meeting...</p>

    <h2>{{ encounter_name }}</h2>
    <p>{{ encounter_start_date }} /
       {{ encounter_start_time.strftime('%H:%M') }}-{{ encounter_end_time.strftime('%H:%M') }}
       ({{ encounter_timezone }})</p>

    <table class="joinTable">
      <tbody>
        {% for alias, alias_protocols in participant_aliases.items() %}
          {% if 'WEB' in alias_protocols %}
            <tr>
              <td>Web (PC / Mac / iOS / Android):</td>
              <td><a href="{{ default_webapp_url }}#/?conference={{ alias }}&name={{ participant_display_name }}&pin={{ participant_pin }}">Join meeting</a></td>
            </tr>
          {% elif 'SIP' in alias_protocols %}
            <tr><td>From a video conferencing endpoint dial:</td><td>sips:{{ alias }}</td></tr>
          {% elif 'H323' in alias_protocols %}
            <tr><td>From a video conferencing endpoint dial:</td><td>h323:{{ alias }}</td></tr>
          {% endif %}
        {% endfor %}

        {% if participant_authentication_method == "PIN" %}
          <tr><td>PIN code:</td><td>{{ participant_pin }}</td></tr>
        {% endif %}
        {% if participant_authentication_method == "IDP" %}
          <tr><td>Login:</td><td>{{ participant_identity_provider }}</td></tr>
        {% endif %}
      </tbody>
    </table>
  </body>
</html>
```

### Customising the template

Update the template with PATCH:

```json
PATCH /api/email_template/1/
{
  "subject_template": "Invitation: {{ encounter_name }} on {{ encounter_start_date }}",
  "body_template": "<html>... your branded HTML ...</html>"
}
```

Notes:

- The same Jinja2 context is in scope in `subject_template` and
  `body_template`.
- The body is limited to **24,576 characters** including the HTML.
  Inline CSS adds up fast — keep it lean.
- iCalendar invite attachment generation is performed **by the
  Scheduler** when `send_email` runs; the template only controls the
  HTML body. You don't construct the `.ics` yourself.

### Previewing — `generate_email`

```
POST /api/command/generate_email
{ "encounter": "8b3e3f44-…", "participant": 42, "cancel": false }
```

Response:

```json
{
  "subject": "Invitation: Monday Sync on 2026-06-01",
  "body": "<html>...</html>"
}
```

Use this in a UI preview, or in your tests, to verify what
participants will see before you actually send.

### Sending — `send_email`

```
POST /api/command/send_email
{ "encounter": "8b3e3f44-…", "participant": 42, "cancel": false }
```

Response: `200` with no body. The Scheduler renders and posts to its
SMTP server.

Setting `cancel: true` produces a cancellation email (iCalendar
`METHOD:CANCEL`) instead of an invite. Send cancellations **before**
`DELETE /api/encounter/{id}/`, otherwise the encounter is gone and the
endpoint returns 404.

There's **no bulk send** — loop over your participants and call
`send_email` once per recipient.

```bash
for PID in 42 43 44 50 51; do
  curl -X POST https://scheduler.example.com/api/command/send_email \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d "{ \"encounter\": \"8b3e3f44-…\", \"participant\": $PID }"
done
```

### Update invites — bump `mail_sequence` first

When you PATCH an encounter and resend, **first** increment
`mail_sequence` on the encounter so the new `.ics` attachment carries
a higher SEQUENCE number than the original. Outlook/Apple/Google will
silently drop the update otherwise. See
[encounters.md](encounters.md) §5.

---

## 2. SMTPServer (singleton)

Endpoints under `/api/smtp_server/` — **read + update only**, no
POST/DELETE. Lives at id `1`.

| Field | Type | Default | Notes |
|---|---|---|---|
| `id` | int64, readOnly | — | Always `1` |
| `description` | string ≤250 | `""` | |
| `address` | string ≤255 | — | IP or FQDN of the SMTP server |
| `port` | int (1–65535) | `587` | Standard submission port |
| `username` | string ≤100 | `""` | SMTP auth user |
| `password` | string ≤196 | `""` | SMTP auth password |
| `from_email_address` | string ≤100 (email format) | `""` | The `From:` address. **Must be permitted by the SMTP server** for the configured username, or the server will reject the relay. |
| `connection_security` | enum `NONE`/`STARTTLS` | `STARTTLS` | TLS handshake mode |

Configure once per deployment:

```json
PATCH /api/smtp_server/1/
{
  "address": "smtp.example.com",
  "port": 587,
  "username": "noreply@example.com",
  "password": "...",
  "from_email_address": "no-reply@example.com",
  "connection_security": "STARTTLS"
}
```

Common failure modes:

- **`connection_security: NONE` on port 587** — many SMTP servers
  require STARTTLS on 587 and will fail.
- **Mismatched `from_email_address`** — the configured user must be
  allowed to send as that address, or you'll see 550 5.7.0 relays.
- **No DMARC alignment** — even when SMTP accepts the mail, downstream
  spam filters may reject if the From domain isn't in line with the
  authenticated user's DKIM/SPF.

There's no test-send endpoint in the Portal API. Use
`generate_email` to confirm rendering, then `send_email` against a
test participant whose `email` is your own.

---

## 3. Theme

`/api/theme/` — full CRUD.

| Field | Type | Required | Notes |
|---|---|---|---|
| `id` | int64, readOnly | — | |
| `name` | string ≤250 | ✅ | **Name of the IVR theme as appears on Pexip Infinity.** Must match verbatim. |
| `pinning_configs` | string ≤2000, default `""` | — | Comma-separated list of pinning configuration names available on this theme (e.g. `"default,chair-focus,grid-only"`). |

Themes are **not uploaded via the Scheduler** — they live on Pexip
Infinity (under Conferencing > IVR themes). The Scheduler row is a
reference by name. If the name doesn't match an Infinity theme, the
meeting falls back to Infinity's default theme.

Reference a theme from an Encounter:

```json
PATCH /api/encounter/{uuid}/
{ "theme": 3, "breakout_room_theme": 3, "pinning_config": "chair-focus" }
```

The `pinning_config` value **must** be one of the strings declared on
the theme's `pinning_configs`. Setting `pinning_config` to something
the theme doesn't list typically falls back to the theme's default.

---

## 4. View (layout)

`/api/view/` — full CRUD.

| Field | Type | Required | Notes |
|---|---|---|---|
| `id` | int64, readOnly | — | |
| `name` | string ≤250 | ✅ | Display name (what shows in the Scheduler UI) |
| `layout_name` | string ≤50 | ✅ | **Internal name of the layout** — must match a layout that Pexip Infinity knows about (e.g. `1:7`, `1:21`, `2:21`, `4:0`, `5:7`) |

Views are **pure references** into Infinity's layout system, just
like themes. Create one View row per Infinity layout you want to
expose for selection on encounters.

---

## 5. Language

`/api/language/` — full CRUD. Used for interpreter pairing — see
[breakouts-and-interpreters.md](breakouts-and-interpreters.md) §3.

| Field | Type | Required | Notes |
|---|---|---|---|
| `id` | int64, readOnly | — | |
| `name` | string ≤250 | ✅ | Display name |
| `kind` | enum `SPOKEN`/`SIGN`, default `SPOKEN` | — | |

---

## 6. RTMPStream

`/api/rtmp_stream/` — full CRUD.

| Field | Type | Required | Notes |
|---|---|---|---|
| `id` | int64, readOnly | — | |
| `name` | string ≤250 | ✅ | Display name |
| `url` | string ≤500 (uri format) | ✅ | RTMP destination URL. Must be `rtmp://` or `rtmps://` scheme. |

Reference up to **5** streams on an Encounter:

```json
PATCH /api/encounter/{uuid}/
{ "rtmp_streams": [1, 3] }
```

The Scheduler pushes the description to Infinity which adds them as
dial-out RTMP destinations on the VMR. Common uses: YouTube Live,
Wowza, a recording archive.

---

## 7. PassthroughAlias

`/api/passthrough_alias/` — full CRUD.

| Field | Type | Required | Notes |
|---|---|---|---|
| `id` | int64, readOnly | — | |
| `alias` | string ≤250 | ✅ | An alias which falls back to the Pexip Infinity configuration. |

When the Scheduler receives a request to dial an alias that doesn't
correspond to a Scheduler-managed encounter, it normally rejects (or
follows `global_settings.default_response_type` — `REJECT` or
`CONTINUE`). PassthroughAliases are an **explicit allow-list**:
listed aliases are handed straight through to Infinity to resolve via
its **own** existing VMR/service config.

Use this for aliases you want both systems to share — e.g. permanent
VMRs configured directly on Infinity that the Scheduler must not
shadow. See [infinity-integration.md](infinity-integration.md) §3.

---

## 8. GlobalSettings (singleton)

`/api/global_settings/` — **read + update only**.

| Field | Type | Default | Notes |
|---|---|---|---|
| `id` | int64, readOnly | — | Always `1` |
| `join_grace_period` | duration string | `"00:00:00"` | How long before/after start/end times the meeting is joinable |
| `default_language` | string ≤10 | `"en"` | Default portal UI language |
| `default_breakout_rooms_mode` | enum `OFF`/`MANUAL`/`AUTOMATIC` | `"AUTOMATIC"` | Default for new encounters |
| `default_webapp_url` | uri ≤200 | — | Where to send participants for the WEB join link in the email template |
| `default_pin_length` | int (4–20) | `8` | Used when generating PINs for new participants |
| `default_response_type` | enum `REJECT`/`CONTINUE` | `"REJECT"` | What to do for aliases unknown to the Scheduler — reject the call, or let Infinity try to resolve them itself |

`default_response_type: CONTINUE` is the looser default — it pairs
with **PassthroughAlias** as a fallback so the Scheduler doesn't
swallow every unknown alias.

---

## 9. i18n — UI translations

`/api/i18n/` lists locales the Scheduler UI is translated into.

```
GET    /api/i18n/                              # list locales
POST   /api/i18n/                              # add a locale
PUT    /api/i18n/{locale}/                     # replace a locale
DELETE /api/i18n/{locale}/                     # delete a locale
GET    /api/i18n/{locale}/django_po/           # raw django.po (gettext)
GET    /api/i18n/{locale}/djangojs_po/         # raw djangojs.po (frontend)
```

Out of scope for most integrations. Most teams treat the i18n
endpoints as deployment-side: customize translations once and pin
them in the deployment artefact.

---

## 10. /api/calendar/ — date-range view

```
GET /api/calendar/?start=2026-06-01T00:00:00Z&end=2026-06-30T23:59:59Z
```

Returns expanded encounter events for the date range — i.e.
**recurrences are expanded into individual instances**. Useful for
calendar-grid UIs that want one row per occurrence rather than per
encounter-with-RRULE.

Spec note: the response is declared as "No response body" in the spec
— that's a documentation gap. The actual response is a JSON array of
event objects with start/end timestamps. ⚠️ Verify the exact shape
against your version (`curl -i` it before relying on it).

---

## 11. /api/version

```
GET /api/version
```

Returns the Scheduler's version info. Useful for compatibility checks
in your integration. Spec also declares "No response body" but the
endpoint does return JSON in practice.

---

## 12. Cross-references

- The encounter fields these resources are referenced from
  (`theme`, `breakout_room_theme`, `pinning_config`, `view`,
  `main_language`, `rtmp_streams`, `access_groups`) → [encounters.md](encounters.md) §1
- How the email template Jinja2 context overlaps with the alias template context → [participants-roles-aliases.md](participants-roles-aliases.md) §4
- Why themes/views/languages must match Infinity verbatim → [infinity-integration.md](infinity-integration.md)
