# Authentication Debugging — Expanded Reference

Detailed troubleshooting for Pexip Infinity authentication issues: SAML/IdP,
Keycloak, OAuth2 client credentials, and the common "Not authenticated" error.

---

## SAML Attribute Mapping Chain

Authentication attributes flow through a four-step chain. A break at any step
causes attributes to silently disappear:

```
Step 1: Keycloak User Profile
  User has attribute "title" = "Level 3"
  → KC v26+ REQUIRES attribute defined in User Profile schema  **(field-tested)**
  → If not in schema, attribute is silently ignored

Step 2: Keycloak SAML Mapper
  Protocol Mapper: "title" → SAML attribute "title"
  → Mapper type: "User Attribute" (not "User Property")
  → SAML Attribute Name: "title"
  → Must be configured on the SAML client, not the client scope

Step 3: Pexip Identity Provider Custom Attribute
  IdP attribute registered on Pexip: "title"
  → Must exist in /api/admin/configuration/v1/identity_provider_attribute/
  → Pexip silently ignores unregistered attributes  **(field-tested)**
  → No error in any log when an attribute is not registered

Step 4: Policy Server participant_properties
  Pexip sends "idp_attributes": {"title": "Level 3"} to policy server
  → Policy server maps title to classification level
  → Returns overlay_text with level indicator
```

### Debugging the chain

To verify each step:

**Step 1:** Check Keycloak User Profile schema
- Admin Console > Realm Settings > User Profile > Attributes
- The `title` attribute must be listed
- If missing, add it (required for KC v26+)

**Step 2:** Check SAML mapper
- Admin Console > Clients > `<saml-client>` > Client Scopes > Mappers
- Look for mapper with SAML Attribute Name = `title`
- Verify mapper type is "User Attribute" and user attribute is `title`

**Step 3:** Check Pexip IdP attribute registration
```
GET /api/admin/configuration/v1/identity_provider_attribute/
```
- Look for an entry with `name: "title"`
- If missing, create it:
```
POST /api/admin/configuration/v1/identity_provider_attribute/
{"name": "title", "identity_provider": "/api/admin/configuration/v1/identity_provider/<id>/"}
```

**Step 4:** Check policy server logs
- Search for incoming `participant_properties` requests
- Check if `idp_attributes` contains the expected attributes
- If `idp_attributes` is empty or missing `title`, the break is at step 1, 2, or 3

---

## Keycloak v26+ User Profile Schema Requirement

Starting with Keycloak v26, custom user attributes must be explicitly defined
in the User Profile schema before they can be:
- Set via Admin API
- Included in SAML assertions
- Included in OIDC tokens

**This is a silent failure.** **(field-tested)** Setting an attribute via API returns success,
but the attribute is not stored and not included in assertions.

### Fix
1. Go to Keycloak Admin Console > Realm Settings > User Profile
2. Click "Create attribute"
3. Name: `title` (or whatever your classification attribute is)
4. Set permissions (who can view/edit)
5. Save

After adding to the schema, re-set the attribute on affected users.

---

## "Not Authenticated" Error

This is one of the most common Pexip errors. Decision tree:

```
"Not authenticated" error when joining a conference
  |
  +-- Is the policy server URL correct?
  |     #1 cause: stale ngrok URL  **(field-tested)**
  |     Check: GET /api/admin/configuration/v1/policy_server/
  |     Fix: update URL, wait 30s for replication
  |
  +-- Is an IdP group configured?
  |     The conference requires IdP auth but no IdP group is set
  |     Check: service_configuration response includes idp_group
  |     Check: Pexip Identity Provider is configured and linked
  |
  +-- Is non_idp_participants set correctly?
  |     On Pexip v39+: must be "allow_if_trusted" not "allow"  **(field-tested)**
  |     "allow" was deprecated/changed in behavior
  |     Check: service_configuration response
  |
  +-- Is the SAML assertion being sent?
  |     Browser popup may be blocked  **(field-tested)**
  |     Check: browser popup blocker settings
  |     Check: Keycloak login page loads in popup
  |
  +-- Are redirect URIs correct in Keycloak?
        SAML client needs exact redirect URIs
        Wildcards only work in path, not hostname  **(field-tested)**
        Need BOTH localhost AND 127.0.0.1 for local dev  **(field-tested)**
```

---

## OAuth2 Client Credentials Debugging

For Management API OAuth2 access (used by automated systems, not end-user auth):

### JWT `aud` claim

The `aud` (audience) claim in the JWT assertion MUST use the **internal** management FQDN (`management_vm.name`), NOT the external CNAME. **(field-tested)**

```
# WRONG — external CNAME
aud: "pexip-mgmt.example.com"

# CORRECT — internal management_vm.name
aud: "pexmgr.internal.domain"
```

The error message is **unhelpful**: `"invalid_client: invalid_claim"` with no indication of which claim is wrong. **(field-tested)**

### Two IDs for oauth2_client

The `oauth2_client` resource on Pexip has two different IDs: **(field-tested)**

| ID type | Where it's used | Example |
|---|---|---|
| `client_id` (alphanumeric) | JWT `sub` claim, token request | `"my-policy-server"` |
| `id` (integer) | Management API URLs for CRUD | `42` |

```
# Token request uses client_id (alphanumeric)
POST /oauth/token/
  grant_type=client_credentials
  client_assertion has sub="my-policy-server"

# API management uses integer id
DELETE /api/admin/configuration/v1/oauth2_client/42/
```

**Mixing them causes DELETE 404** — using `client_id` in the URL path instead of `id`. **(field-tested)**

### ES256 JWT assertion format

```python
import jwt
import time

now = int(time.time())
assertion = jwt.encode({
    "iss": client_id,        # Alphanumeric client_id
    "sub": client_id,        # Same
    "aud": management_fqdn,  # INTERNAL management_vm.name
    "exp": now + 300,
    "iat": now,
    "jti": str(uuid.uuid4())
}, private_key, algorithm="ES256")
```

---

## SAML Certificate Requirements

Pexip SAML/IdP integration requires three certificates: **(common pattern)**

| Certificate | Purpose | Where it's configured |
|---|---|---|
| IdP public cert | Pexip verifies SAML assertions signed by the IdP | Identity Provider config on Pexip |
| Infinity public cert | IdP encrypts assertions for Pexip (optional but recommended) | Exported from Pexip, uploaded to IdP |
| Infinity private key | Pexip decrypts assertions from IdP | Managed internally by Pexip |

### Common certificate issues

- **Certificate expired** → SAML assertions fail silently. Check certificate dates.
- **Wrong certificate** → uploaded the staging cert to production IdP
- **Missing intermediate CA** → some IdP implementations need the full chain

---

## Keycloak Redirect URI Patterns

### Rules

1. **Wildcards only work in the path segment, not in the hostname** **(field-tested)**
   ```
   # WORKS
   https://pdp.example.com/*
   
   # DOES NOT WORK
   https://*.example.com/callback
   ```

2. **Need BOTH hostname variants for local development** **(field-tested)**
   ```
   http://localhost:5555/*
   http://127.0.0.1:5555/*
   ```

3. **HTTPS redirect from HTTP origin is blocked by browsers** **(field-tested)**
   - SAML login from `http://localhost:5555` posts back to HTTPS Keycloak
   - Browser may block the mixed-content form POST
   - Fix: use ngrok URL (HTTPS) or Chrome flag `--allow-running-insecure-content`

4. **webOrigins must match redirectUris**
   - Keycloak uses webOrigins for CORS
   - If redirectUri is `http://localhost:5555/*`, webOrigins needs `http://localhost:5555`

---

## SAML role_list Mapper

Keycloak's built-in `role_list` mapper sends ALL roles in a single SAML attribute.
Pexip can choke on multi-valued attributes.

### Fix

Set `single=true` on the role_list mapper: **(field-tested)**
1. Admin Console > Clients > `<saml-client>` > Client Scopes > `role_list` mapper
2. Set "Single Role Attribute" to ON
3. This sends one `<Attribute>` element per role instead of a multi-valued one

Without this, Pexip may log a duplicate Role attribute error and reject the assertion.

---

## Debugging Checklist: Participant Can't Authenticate

Run through in order:

1. **Is the conference configured for IdP auth?**
   - Check service_configuration response for `idp_group`
   - If no IdP group → conference is open, "Not authenticated" shouldn't appear

2. **Is the IdP (Keycloak) reachable?**
   - From the participant's browser (WebRTC) or network (SIP)
   - Check: `curl -k https://<keycloak-url>/realms/<realm>/.well-known/openid-configuration`

3. **Is the Pexip Identity Provider configured?**
   - `GET /api/admin/configuration/v1/identity_provider/`
   - Check UUID, SAML metadata URL, custom attributes

4. **Is the SAML assertion being sent?**
   - Check browser dev tools Network tab during login popup
   - Look for POST to Pexip's ACS (Assertion Consumer Service) URL

5. **Are attributes present in the assertion?**
   - Use browser SAML tracer extension to decode the assertion
   - Check for expected attributes (title, email, etc.)

6. **Are attributes registered on Pexip?**
   - `GET /api/admin/configuration/v1/identity_provider_attribute/`
   - Missing attributes are silently ignored

7. **Is participant_properties receiving the attributes?**
   - Check PDP logs for `idp_attributes` in incoming requests
   - Empty `idp_attributes` → break at steps 1-6 above
