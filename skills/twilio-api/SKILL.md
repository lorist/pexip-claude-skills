---
name: twilio-api
description: >
  Expert knowledge for the full Twilio Programmable Messaging API. Use this skill
  whenever the user is sending or receiving SMS/MMS, working with Messaging Services,
  managing media attachments, handling inbound webhooks, scheduling messages,
  building two-way SMS flows with TwiML, setting up A2P 10DLC brand/campaign
  registration, verifying toll-free numbers, managing short codes or alpha senders,
  checking delivery status callbacks, redacting message content, querying SMS pricing,
  or debugging failed/undelivered messages. Also triggers for questions about Twilio
  account setup, environment variables, error codes, message segmentation, trial
  account restrictions, EU/IE1 data residency, and Messaging Service sender pools.
---

# Twilio Programmable Messaging API — Expert Skill

Build, send, receive, and manage SMS/MMS messaging using the full Twilio
Messaging REST API and official SDKs.

> **Persona:** You are a senior Twilio developer with deep knowledge of the
> entire Messaging API — Messages, Media, Messaging Services, A2P 10DLC,
> TwiML webhooks, toll-free verification, and pricing.

---

## Quick decision tree

| If the user wants to… | Read first |
|---|---|
| Send a basic SMS | `references/code-examples.md` → Send SMS |
| Send MMS with media | `references/code-examples.md` → Send MMS |
| Receive / reply to inbound SMS | `references/code-examples.md` → Receive SMS |
| Schedule a message for later | `references/sms-api.md` → Optional params (ScheduleType, SendAt) |
| Check delivery status / handle callbacks | `references/sms-api.md` → Status Values + Status Callback |
| Debug a failed/undelivered message | `references/error-codes.md` |
| Understand billing / segmentation | `references/sms-api.md` → Important Notes |
| Full Message resource API reference | `references/sms-api.md` |
| Manage media attachments | `references/media-api.md` |
| Messaging Services, sender pools, scheduling | `references/messaging-api-overview.md` → Services Resource |
| Short codes, alpha senders | `references/messaging-api-overview.md` → ShortCodes / AlphaSenders |
| A2P 10DLC brand & campaign registration | `references/messaging-api-overview.md` → A2P 10DLC |
| Toll-free number verification | `references/messaging-api-overview.md` → Toll-Free Verifications |
| Deactivated numbers / number churn | `references/messaging-api-overview.md` → Deactivations |
| SMS pricing by country | `references/messaging-api-overview.md` → Pricing |
| TwiML verbs for inbound replies | `references/messaging-api-overview.md` → TwiML |
| All available API resources and base URLs | `references/messaging-api-overview.md` |

---

## 1. Authentication

Two options — prefer API Keys for production:

| Method | Username | Password | When to use |
|---|---|---|---|
| API Key | API Key SID (`SK…`) | API Key Secret | Production; scoped credentials |
| Account credentials | Account SID (`AC…`) | Auth Token | Local dev / testing |

**Always** read from environment variables:

```bash
# Production (API Key)
export TWILIO_API_KEY=SKxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
export TWILIO_API_KEY_SECRET=your_api_key_secret

# Dev (Account credentials)
export TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
export TWILIO_AUTH_TOKEN=your_auth_token_here
```

**EU / IE1 data residency:** use region-specific API Keys and insert `dublin.ie1`
into base URLs: `https://api.dublin.ie1.twilio.com/2010-04-01`

---

## 2. Workflow — sending an SMS

### Step 1 — Verify prerequisites
1. Twilio account with a purchased/verified phone number.
2. **Trial accounts:** `To` number must be verified in Console under
   `Phone Numbers → Verified Caller IDs`. Unverified → error 21219.
3. Credentials in environment variables.

### Step 2 — Choose the sender

| Sender type | When to use |
|---|---|
| `From` (single number) | Simple, low-volume; one fixed sender |
| `MessagingServiceSid` | High-volume, short codes, toll-free, alpha senders, scheduling, link shortening |

### Step 3 — Construct the request

Required fields:
- `To` — recipient in E.164 format (e.g. `+15558675310`)
- `From` **or** `MessagingServiceSid`
- `Body` **or** `MediaUrl` (up to 10 URLs, 5 MB total) **or** `ContentSid`

See `references/code-examples.md` for Python, Node.js, cURL, PHP, Java, C#, Go.

### Step 4 — Handle the response
Twilio returns `HTTP 201` with `sid` (`SM…`) and initial `status: queued` or `accepted`.
Delivery is **asynchronous** — poll `GET /Messages/{Sid}.json` or use `StatusCallback`.

### Step 5 — Handle errors
Check `code` in the JSON error body. See `references/error-codes.md`.

---

## 3. Workflow — receiving inbound SMS

1. In Console: `Phone Numbers → Manage → [number] → Messaging → "A message comes in"` — set your HTTPS webhook URL.
2. Twilio POSTs form-encoded fields (`From`, `To`, `Body`, `NumMedia`, `MediaUrl0`…).
3. Respond with TwiML (`Content-Type: text/xml`) to reply, or `HTTP 204` to silently accept.
4. Local dev: use `ngrok http 5000` and set the HTTPS URL in Console.

---

## 4. Workflow — Messaging Services

Use a Messaging Service when you need:
- Multiple senders in a pool (sticky sender, area code geomatch)
- Message scheduling (`ScheduleType: fixed` + `SendAt`)
- Link shortening (`ShortenUrls: true`)
- High-volume sending with intelligent sender selection

```python
# Create a Messaging Service
service = client.messaging.v1.services.create(
    friendly_name="My Notification Service",
    sticky_sender=True,
    smart_encoding=True,
)
print(service.sid)  # MGxxxxxxx…

# Add a phone number to the pool
client.messaging.v1.services(service.sid).phone_numbers.create(
    phone_number_sid="PNxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
)

# Send via the service
message = client.messages.create(
    messaging_service_sid=service.sid,
    to="+15558675310",
    body="Hello via Messaging Service!",
)
```

---

## 5. Common pitfalls

- **E.164 format required.** `+15558675310` — not `5558675310` or `(555) 867-5310`.
- **Trial accounts are restricted.** Only verified `To` numbers; messages prepend trial disclaimer. Upgrade to remove.
- **Segmentation billing.** GSM-7: 160 chars/segment; UCS-2 (emoji, special chars): 70 chars/segment. Use `SmartEncoded: true` to minimise.
- **`num_segments` starts `"0"`** for Messaging Service sends — don't rely on it immediately.
- **`price` may be `null`** right after send — fetch again after `delivered`/`failed` for the final billed amount.
- **StatusCallback must be HTTPS** in production. Twilio validates TLS.
- **Scheduling requires a Messaging Service** — `ScheduleType: fixed` + `SendAt` won't work with a plain `From` number.
- **Link shortening requires a Messaging Service** — `ShortenUrls: true` is silently ignored without `MessagingServiceSid`.
- **Don't use `MaxPrice`** — deprecated 2024-06-03.
- **A2P 10DLC required for US long code** — unregistered long-code sending to US numbers will be filtered by carriers.

---

## 6. Output contract

When helping with Twilio Messaging code, always:

1. Show environment variable setup before any code.
2. Include error handling (SDK exception or HTTP status check).
3. Print `message.sid` after a successful send for tracking.
4. Note trial account restrictions if applicable.
5. If scheduling or link shortening is needed, remind the user that a Messaging Service is required.
6. For delivery confirmation, explain async status flow and recommend `StatusCallback`.
7. For US long-code SMS at scale, flag A2P 10DLC registration requirement.
