# Authentication and identity

The Scheduler distinguishes between three different identity concepts.
**Conflating them is the most common cause of "401 / 403 / why is my
participant not getting in"** confusion.

| Concept | What it controls | Where it lives |
|---|---|---|
| **API authentication** | How *your code* talks to the Portal API | `basicAuth` + `command/long_lived_token` |
| **Portal user authentication** | How a *human* logs in to the Scheduler **web UI** | `/api/authentication_mode/` (local username/password or OIDC SSO) |
| **Meeting participant authentication** | How a *meeting participant* proves who they are when joining a meeting | `participant.authentication_method` = `PIN` \| `IDP` \| `""` |

This file walks through each, plus the supporting machinery:
`FeatureGroup`, `OAuth2Client`, `IdentityProvider`, `AccessGroup`.

---

## 1. API authentication — basic auth + long-lived token

Every Portal API operation declares two security schemes (with the
exception of the token endpoints):

```yaml
security:
- basicAuth: []
- tokenAuth: []
```

This is an **OR**, not an AND. Send **one** of them per request.

| Scheme | Header | Notes |
|---|---|---|
| `basicAuth` | `Authorization: Basic <base64(user:pass)>` | The credentials are those of a Scheduler-side user account (admin or otherwise). Fine for one-off scripts; not great for long-running integrations because the password lives in your config. |
| `tokenAuth` | `Authorization: Bearer <token>` | A long-lived API token. Preferred for production integrations, SCIM provisioners, and anything else that runs as a service. |

### The `command/long_lived_token` endpoints

```
GET  /api/command/long_lived_token/          ─┐
POST /api/command/long_lived_token/           ├─ security: basicAuth ONLY
POST /api/command/long_lived_token/revoke/   ─┘
```

The operation description in the spec is *"View to create a long-lived
token for the scim client."* That's the documented use case (SCIM
provisioning), but the token works for any Portal API endpoint that
accepts `tokenAuth`.

⚠️ **Spec gotcha — where the token lives.** All three responses are
declared as `200 — No response body`. The spec does **not** declare
where the token surfaces. In practice it's returned in a response
header (`X-Token`, `X-Auth-Token`, or similar) or a `Set-Cookie`. The
first time you call this in a new environment, run with `curl -i` and
**pin the contract in your code**:

```bash
$ curl -i -u admin:hunter2 \
    -X POST https://scheduler.example.com/api/command/long_lived_token/
HTTP/1.1 200 OK
X-Token: 8e3b4f3a-a1c2-4f5e-9d8b-1234567890ab     # ← here, or wherever your version puts it
...
```

### Token rotation

You can't refresh a token with itself — the rotation endpoints all
require basicAuth. The recommended pattern:

```
# Provision (basicAuth) → store TOKEN
POST /api/command/long_lived_token/

# Use (tokenAuth) for as long as needed
GET  /api/encounter/         Authorization: Bearer <TOKEN>
...

# Revoke (basicAuth) and re-provision
POST /api/command/long_lived_token/revoke/
POST /api/command/long_lived_token/             → new TOKEN
```

There's no rotation-without-credentials. If you need to rotate tokens
on a schedule without storing the admin password, keep the password
in a secrets store and pull it just-in-time for the rotation cron.

---

## 2. Portal user auth — local vs OIDC

For the **web UI** (the Scheduler portal that humans log into to
schedule meetings), authentication is controlled by `AuthenticationMode`.

Endpoints under `/api/authentication_mode/` — singleton at id `1`, no
POST/DELETE.

### Schema

| Field | Type | Default | Notes |
|---|---|---|---|
| `id` | int64, readOnly | — | Always `1` |
| `mode` | enum `local`/`oidc` | `local` | The active auth mode |
| `oidc_metadata_url` | uri, default `""` | — | OIDC discovery URL (`.well-known/openid-configuration`) |
| `oidc_client_id` | string ≤255 | — | OIDC client id |
| `oidc_client_secret` | string ≤196, default `""` | — | OIDC client secret |
| `oidc_disable_local_login` | bool, default `true` | — | If true (and mode=oidc), local login is hidden — only SSO works |
| `oidc_default_feature_group` | int FK → `feature_group.id`, nullable | — | New users created via OIDC are assigned to this FeatureGroup. **Set this** before turning on OIDC, otherwise OIDC-provisioned users have no permissions. |

### Switching to OIDC

```json
PATCH /api/authentication_mode/1/
{
  "mode": "oidc",
  "oidc_metadata_url": "https://idp.example.com/.well-known/openid-configuration",
  "oidc_client_id": "scheduler",
  "oidc_client_secret": "...",
  "oidc_disable_local_login": false,         /* leave local login as a fallback initially */
  "oidc_default_feature_group": 2
}
```

Practical advice:

- Configure OIDC with `oidc_disable_local_login: false` first, log in
  once via OIDC to confirm it works, **then** set it to `true`.
- The OIDC IdP for **portal users** can be different from the IdP for
  **meeting participants** (next section). They're independent.

---

## 3. Meeting participant auth — PIN vs IDP

This governs how **a participant proves who they are when joining
the meeting on Infinity**. Three options:

| `participant.authentication_method` | What Infinity does on join |
|---|---|
| `""` (empty string) | No challenge. Anyone with the alias gets in. |
| `"PIN"` | Infinity prompts for the participant's `pin` value. |
| `"IDP"` | Infinity redirects to the configured IdP for SSO; on success, checks that an attribute matches `participant.identity_provider_value`. |

### How `IDP` works end-to-end

1. The Scheduler has an `IdentityProvider` row that maps to an **IdP
   already configured on Pexip Infinity** (under Platform > Identity
   providers). The Scheduler doesn't host the IdP — Infinity does.

   ```json
   POST /api/identity_provider/
   {
     "group_name": "Acme-Workforce-IdP",
     "attribute_name": "email"
   }
   ```

   - `group_name` is the name of the IdP **on the Infinity side**.
   - `attribute_name` is which SAML/OIDC attribute Infinity should
     look up in the assertion and compare against the participant.

2. A `Participant` with IDP auth points at this IdP row:

   ```json
   POST /api/participant/
   {
     "display_name": "Alice Example",
     "authentication_method": "IDP",
     "identity_provider": 7,                /* the IdP row above */
     "identity_provider_value": "alice@acme.com"
   }
   ```

3. On join, the flow is:

   ```
   Alice dials her per-participant alias
     → Infinity sees the alias maps to a participant requiring "IDP" auth via IdP 7
     → Infinity redirects Alice to the IdP for SSO
     → IdP returns a SAML/OIDC assertion
     → Infinity reads the "email" attribute from the assertion
     → Infinity compares it to "alice@acme.com"
       match → admit
       no match → reject
   ```

So the Scheduler is **not** acting as the SSO consumer — Infinity is.
The Scheduler just configures the binding (which IdP, which attribute,
which expected value).

### IdentityProvider schema

| Field | Type | Required | Notes |
|---|---|---|---|
| `id` | int64, readOnly | — | |
| `group_name` | string ≤250 | ✅ | "IdP group as configured on Infinity" — must match the name of an Identity Provider on the Infinity side |
| `attribute_name` | string ≤250 | ✅ | Which attribute from the IdP assertion to compare |

Endpoints under `/api/identity_provider/` — full CRUD.

### Choosing PIN vs IDP

- **PIN** is the path of least resistance for external participants
  who don't have accounts in your identity system. The Scheduler
  generates the PIN, the invite email includes it, the participant
  types it in.
- **IDP** is for internal participants who already have SSO. Better
  security, no email-leaked PIN. But it requires the IdP to actually
  be configured on Infinity and for the participant to have a
  matching assertion attribute.

You can mix in one meeting — the chair on IDP, an external guest on
PIN, an unauthenticated dial-in on `""`.

---

## 4. AccessGroup — who can schedule what

`/api/access_group/` — full CRUD. Supports filters `name`,
`name__contains`.

### Schema

| Field | Type | Required | Notes |
|---|---|---|---|
| `id` | int64, readOnly | — | |
| `name` | string ≤250 | ✅ | Display name |

Used on **Encounter** via the `access_groups` array — which access
groups are permitted to schedule / view / modify this meeting.

AccessGroups are a coarse-grained ACL on encounters. Common usage:

- Create `Sales`, `Engineering`, `External` AccessGroups.
- When the sales team schedules a meeting, tag it with
  `access_groups: [<Sales id>]` so only sales-team portal users see
  and modify it.
- Confidential meetings: `access_groups: []` (or a tightly-scoped
  group like `Executive`).

Note that AccessGroups govern **portal access** (who can edit the
meeting in the UI), **not** who can attend the meeting (that's
EncounterParticipants).

---

## 5. FeatureGroup — permission bundles

`/api/feature_group/` — full CRUD.

### Schema

| Field | Type | Required | Notes |
|---|---|---|---|
| `id` | int64, readOnly | — | |
| `name` | string ≤150 | ✅ | Display name, e.g. "admin", "scheduler", "viewer" |
| `permissions` | array of string | ✅ | Permission codes |

FeatureGroups are the Scheduler's **permission bundle** abstraction.
They're attached to OAuth2 clients (and OIDC users via
`authentication_mode.oidc_default_feature_group`) to grant a set of
capabilities.

The exact permission codes vary by version and are not enumerated in
the OpenAPI spec. Common ones include:

| Permission code (typical) | What it grants |
|---|---|
| `scheduler.add_encounter` | Create encounters |
| `scheduler.change_encounter` | Modify encounters |
| `scheduler.delete_encounter` | Delete encounters |
| `scheduler.view_encounter` | List/read encounters |
| (similar `add_*`, `change_*`, `delete_*`, `view_*` for every model) | |
| `scheduler.admin` | Full admin |

⚠️ **Verify against your version** — pull the full permission list via
the admin UI or by inspecting Django's `Permission` table on a live
instance. The OpenAPI spec gives you the *shape* of the array but not
the *contents*.

---

## 6. OAuth2Client — for downstream apps

`/api/oauth2_client/` — full CRUD.

### Schema

| Field | Type | Required | Notes |
|---|---|---|---|
| `id` | int64, readOnly | — | |
| `client_id` | string, readOnly | ✅ (read) | Server-generated OAuth2 client id |
| `client_name` | string ≤32 | ✅ | Display name |
| `feature_group` | int FK → `feature_group.id` | ✅ | Permission bundle granted to this client |

OAuth2 clients are how **external applications** (an Outlook plugin,
a custom portal, a calendar integration) talk to the Scheduler with
their own identity rather than impersonating a human user.

Workflow:

1. Create a FeatureGroup with the permissions the integration needs.
2. POST `/api/oauth2_client/` with that FeatureGroup id and a
   `client_name`.
3. The response includes the auto-generated `client_id`. The
   `client_secret` is shown only on creation (typically out-of-band
   from the OpenAPI document — check your version's actual response).

The token endpoint the OAuth2 client uses to obtain access tokens is
deployment-specific and is **not** part of the Portal API schema —
consult the Scheduler deployment guide.

---

## 7. The full identity stack — picture

```
  ╔══════════════════════════════════════════════════════════════════╗
  ║                       Scheduler runtime                          ║
  ║                                                                  ║
  ║  ┌─ Web UI ────────────────────────────┐                         ║
  ║  │ Humans                              │   /api/authentication_mode/
  ║  │   ├─ local username/password   ◄────┼── (mode: local)          ║
  ║  │   └─ OIDC SSO                  ◄────┼── (mode: oidc)           ║
  ║  └─────────────────────────────────────┘                         ║
  ║                                                                  ║
  ║  ┌─ Portal API ────────────────────────┐                         ║
  ║  │ Integrations                        │                         ║
  ║  │   ├─ basicAuth (admin creds)   ◄────┼── any user account      ║
  ║  │   ├─ long-lived token          ◄────┼── /api/command/long_lived_token/
  ║  │   └─ OAuth2 client             ◄────┼── /api/oauth2_client/   ║
  ║  └─────────────────────────────────────┘                         ║
  ║                                                                  ║
  ║  ┌─ Resources gated by ────────────────┐                         ║
  ║  │ - portal user FeatureGroup          │                         ║
  ║  │ - encounter.access_groups           │                         ║
  ║  └─────────────────────────────────────┘                         ║
  ╚══════════════════════════════════════════════════════════════════╝

  ╔══════════════════════════════════════════════════════════════════╗
  ║                       Infinity runtime                           ║
  ║                                                                  ║
  ║   Meeting participants joining a meeting:                        ║
  ║     ├─ no auth        (participant.authentication_method == "")  ║
  ║     ├─ PIN            (participant.pin)                          ║
  ║     └─ IDP            (Infinity's own SSO via                    ║
  ║                        participant.identity_provider + value)    ║
  ╚══════════════════════════════════════════════════════════════════╝
```

The Scheduler and Infinity each have their own SSO surfaces; the
Scheduler's `identity_provider` rows are *pointers* into Infinity's
IdP config, not their own IdP integrations.

---

## 8. Cross-references

- Participant's `authentication_method` and the PIN regex → [participants-roles-aliases.md](participants-roles-aliases.md) §1
- AccessGroups attached to an Encounter → [encounters.md](encounters.md)
- Infinity's IdP configuration (the Scheduler's `identity_provider` is a reference into that) → [infinity-integration.md](infinity-integration.md)
- The "no body returned" gotcha on `long_lived_token` → [gotchas-and-conventions.md](gotchas-and-conventions.md)
