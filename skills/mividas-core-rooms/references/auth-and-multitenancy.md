# Auth, hosts, and multitenancy

## Base URL

Every Mividas installation has its own hostname. The API lives under `/json-api/v1/`:

```
https://<mividas-host>/json-api/v1/
```

The host might look like `mividas.example.com`, `mividas.customer.pextest.com`, or any other FQDN — there is no shared `mividas.com` API. The hostname comes from the customer's deployment.

## Authentication

**HTTP Basic Auth.** The user account is a Mividas Core admin or service account configured in the Mividas web UI (`Admin → Users` in the product). The OpenAPI document declares an `oauth2` scheme with a `read:groups` scope — that is only for the end-user Portal sign-in, *not* this management API. Use Basic.

```bash
curl -u "$USER:$PASS" "https://mividas.example.com/json-api/v1/customer/"
```

```python
import base64, urllib.request
req = urllib.request.Request("https://mividas.example.com/json-api/v1/customer/")
req.add_header("Authorization", "Basic " + base64.b64encode(f"{user}:{pwd}".encode()).decode())
```

Sessions: every request is independently authenticated; there is no login endpoint to call first. There are no separate "API tokens" for the admin API — credentials are the same user credentials a human admin would use.

## The `X-Mividas-Customer` header

Mividas Core can run in **multi-tenant** mode where one Mividas server fronts many customer tenants (each customer mapping to a CMS tenant or a Pexip tenant). If the authenticated user has access to more than one customer, **every request must declare which customer the action targets**:

```
X-Mividas-Customer: 7
```

Behaviour:

- If the user has access to **exactly one** customer, the header is optional — Mividas resolves the implicit customer.
- If the user has access to **multiple** customers and you omit the header, you'll get an error (typically `400` or `403`) or, worse, the wrong customer's data on a read endpoint — always set it explicitly when you know which tenant you mean.
- The header is **per-request**. Setting it once on a session doesn't persist.

### Looking up customer IDs

```http
GET /json-api/v1/customer/
```

The OpenAPI `info.description` references `GET /json-api/v1/customers/` (plural) — that path does **not** exist; the actual path is `/customer/` (singular). Treat the doc string as a typo.

The response is a paginated list of `CustomerAdmin` objects. Useful fields:

| Field | Use |
|---|---|
| `id` | The integer to put in `X-Mividas-Customer`. |
| `title` | Human name. |
| `mcu_provider` | FK to a `Provider` — the primary MCU for this customer. |
| `recording_provider` / `streaming_provider` | FK to recording/streaming providers. |
| `acano_tenant_id` | The CMS tenant ID this customer maps to in CMS. Must already exist in CMS. |
| `pexip_tenant_id` | The Pexip Infinity tenant string for this customer (auto-generated unless this is the cluster's default customer). |
| `enable_core` / `enable_epm` | Whether this customer has Core (conferencing) and/or Rooms (endpoint management) features enabled. |
| `usage` | Read-only dict of current usage counters (cospaces, users, endpoints, …). |

## `/customerkey/` — per-customer shared keys

Distinct from user Basic Auth, Mividas also supports per-customer "shared keys" (sometimes called API keys) under `/customerkey/`. These are typically used by **other systems integrating into Mividas** (e.g. an internal portal, a CRM doing dial-out automation) rather than by Mividas admins. The shared key authenticates a *customer* rather than a *user*; how it's presented on the wire depends on the integration (most commonly a custom header or a query parameter — confirm against the specific feature you're integrating with).

You generally do not need `/customerkey/` for ordinary admin scripting — stick with Basic Auth + the customer header.

## Permissions inside a customer

Within a customer, Mividas has its own role model (admin / operator / read-only / portal user / …). The admin API enforces this against the Basic Auth user. If you get unexpected `403`s on actions you think should work, check the user's role in the Mividas UI — service accounts often start as read-only.

## TLS / certificates

Production Mividas installations terminate TLS at their own hostname. The `Provider`, `EWSCredentials`, `EndpointFirmware` external URLs, etc. each have their own `verify_certificate` boolean for *outbound* connections from Mividas to those systems. The **inbound** TLS to Mividas itself is whatever the customer's reverse proxy / load balancer presents — there is no per-tenant TLS knob.

## Customer-aware resources

Most resources are scoped to one customer once the `X-Mividas-Customer` header is set. A handful are intentionally global and ignore the header — `/cluster/`, `/provider/`, `/customer/` itself, `/themesettings/` (depending on install), and the `/debug/*` log surfaces (which may be restricted to superusers). When in doubt, send the header — global endpoints will simply ignore it.

## Background: the OAuth2 scheme

For completeness: the OpenAPI's `oauth2` security scheme with `authorizationUrl: /oauth/authorize` and scope `read:groups` is used by the end-user **Mividas Portal** (the user-facing booking interface) for SSO. It is not how an admin-API integration authenticates and you should not try to mint OAuth tokens for `/json-api/v1/` calls.
