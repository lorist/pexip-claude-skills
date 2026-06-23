# Twilio Programmable Messaging API — Full Resource Overview

## Base URLs

| Resource Group | Base URL |
|---|---|
| Messages, Media, Feedback, ShortCodes | `https://api.twilio.com/2010-04-01` |
| Messaging Services & subresources | `https://messaging.twilio.com/v1` |
| Deactivations, Toll-Free Verifications, A2P 10DLC | `https://messaging.twilio.com/v1` |
| SMS Pricing | `https://pricing.twilio.com/v1` |

**EU / Ireland region (IE1):** Insert `dublin.ie1` before `.twilio.com` in any URL.
Example: `https://api.dublin.ie1.twilio.com/2010-04-01`

---

## Authentication

| Method | Username | Password |
|---|---|---|
| API Key (recommended) | API Key SID (`SK…`) | API Key Secret |
| Account credentials (dev/testing) | Account SID (`AC…`) | Auth Token |

IE1 region requires region-specific API keys or region-specific Auth Token.

```bash
# API Key (preferred)
curl -u $TWILIO_API_KEY:$TWILIO_API_KEY_SECRET ...

# Account SID + Auth Token (local dev)
curl -u $TWILIO_ACCOUNT_SID:$TWILIO_AUTH_TOKEN ...
```

---

## Resources

### 1. Messages
**Path:** `/2010-04-01/Accounts/{AccountSid}/Messages`

Core resource for sending and managing SMS/MMS messages.
See `references/sms-api.md` for full parameter and response details.

| Operation | Method | Path |
|---|---|---|
| Send | POST | `.../Messages.json` |
| Fetch | GET | `.../Messages/{Sid}.json` |
| List | GET | `.../Messages.json` |
| Update / redact | POST | `.../Messages/{Sid}.json` |
| Delete | DELETE | `.../Messages/{Sid}.json` |

**Key send parameters:** `To`, `From`/`MessagingServiceSid`, `Body`/`MediaUrl`/`ContentSid`, `StatusCallback`, `ScheduleType`+`SendAt`, `SmartEncoded`, `ShortenUrls`, `ValidityPeriod`.

---

### 2. Media (subresource of Messages)
**Path:** `/2010-04-01/Accounts/{AccountSid}/Messages/{MessageSid}/Media`

Stores media attached to inbound or outbound MMS/WhatsApp messages.
See `references/media-api.md` for full details.

| Operation | Method | Path |
|---|---|---|
| Fetch | GET | `.../Media/{Sid}.json` |
| List | GET | `.../Media.json` |
| Delete | DELETE | `.../Media/{Sid}.json` |

Limits: up to **10 media files** per message, **5 MB** total. Twilio resizes images to carrier specs.

---

### 3. Feedback (subresource of Messages)
**Path:** `/2010-04-01/Accounts/{AccountSid}/Messages/{MessageSid}/Feedback`

Report user-confirmed delivery outcomes for a message.

| Operation | Method |
|---|---|
| Create feedback | POST |

---

### 4. ShortCodes
**Path:** `/2010-04-01/Accounts/{AccountSid}/SMS/ShortCodes`

Manage short codes associated with your account.

| Operation | Method |
|---|---|
| Fetch | GET |
| List | GET |
| Update | POST |

**Key fields:** `sid`, `short_code`, `friendly_name`, `sms_url`, `sms_method`, `sms_fallback_url`, `sms_fallback_method`.

---

### 5. Messaging Services
**Path:** `https://messaging.twilio.com/v1/Services`

Pool multiple senders (numbers, short codes, alpha senders) for high-volume, intelligent sender selection. Required for scheduling and link shortening.

| Operation | Method |
|---|---|
| Create | POST |
| Fetch | GET |
| List | GET |
| Update | POST |
| Delete | DELETE |

**Create parameters:**

| Parameter | Type | Description |
|---|---|---|
| `FriendlyName` | string | Required. Human-readable label |
| `InboundRequestUrl` | uri | Webhook for inbound messages |
| `InboundMethod` | enum | `GET` or `POST` (default `POST`) |
| `FallbackUrl` | uri | Fallback webhook on delivery failure |
| `FallbackMethod` | enum | `GET` or `POST` |
| `StatusCallback` | uri | Status update webhook |
| `StickySender` | boolean | Always use same sender for a given recipient |
| `SmartEncoding` | boolean | Auto GSM-7 conversion to reduce segments |
| `MmsConverter` | boolean | Convert MMS to SMS when MMS unavailable |
| `FallbackToLongCode` | boolean | Fall back to long code if short code fails |
| `ScanMessageContent` | enum | `disable`, `inherit`, `enable` |
| `AreaCodeGeomatch` | boolean | Match sender area code to recipient |
| `ValidityPeriod` | integer | Message validity in seconds (1–36000) |
| `SynchronousValidation` | boolean | Validate requests synchronously |
| `Usecase` | string | Use case (e.g. `notifications`, `marketing`) |
| `UseInboundWebhookOnNumber` | boolean | Use number-level inbound webhook instead |

**Messaging Service subresources:**

| Subresource | Path | Purpose |
|---|---|---|
| PhoneNumbers | `/Services/{Sid}/PhoneNumbers` | Add/remove phone numbers from the pool |
| ShortCodes | `/Services/{Sid}/ShortCodes` | Add/remove short codes |
| AlphaSenders | `/Services/{Sid}/AlphaSenders` | Add/remove alphanumeric sender IDs |
| DestinationAlphaSenders | `/Services/{Sid}/DestinationAlphaSenders` | Destination-specific alpha senders |
| ChannelSenders | `/Services/{Sid}/ChannelSenders` | Non-SMS channel senders (WhatsApp, RCS) |

---

### 6. Deactivations
**Path:** `https://messaging.twilio.com/v1/Deactivations`

Retrieve US phone numbers that were deactivated on a given date (number portability / churn).

| Operation | Method | Query parameter |
|---|---|---|
| Fetch by date | GET | `Date` (YYYY-MM-DD) |

**Response:** a downloadable file URL containing the deactivated numbers for that day.

---

### 7. Toll-Free Verifications
**Path:** `https://messaging.twilio.com/v1/Tollfree/Verifications`

Submit US/Canadian toll-free numbers for regulatory SMS compliance verification.

| Operation | Method |
|---|---|
| Create | POST |
| Fetch | GET |
| Update | POST |
| Delete | DELETE |

**Key parameters:** `TollfreePhoneNumberSid`, `UseCaseDescription`, `UseCaseSummary`, `ProductionMessageSample`, `OptInImageUrls`, `OptInType`, `BusinessName`, `BusinessWebsite`, `NotificationEmail`.

---

### 8. A2P 10DLC (US Application-to-Person)
**Path:** `https://messaging.twilio.com/v1`

Required for US long code SMS at scale. Three-step registration process.

| Resource | Path | Purpose |
|---|---|---|
| BrandRegistrations | `/a2p/BrandRegistrations` | Register your company brand |
| Vettings | `/a2p/BrandRegistrations/{Sid}/Vettings` | Optional enhanced vetting |
| Usa2p (UsAppToPerson) | `/Services/{Sid}/Compliance/Usa2p` | Register messaging campaign |
| Usecases | `/a2p/Usecases` | List available campaign use case types |

**Registration flow:**
1. Create a Brand Registration with company details
2. (Optional) Submit for enhanced vetting
3. Create a Usa2p campaign tied to a Messaging Service SID

---

### 9. Pricing
**Path:** `https://pricing.twilio.com/v1/Messaging/Countries`

Retrieve inbound and outbound SMS pricing per country.

| Operation | Method | Path |
|---|---|---|
| List all countries | GET | `/Messaging/Countries` |
| Fetch one country | GET | `/Messaging/Countries/{IsoCountry}` |

**Response fields:** `country`, `iso_country`, `outbound_sms_prices` (array by carrier), `inbound_sms_prices`, `price_unit`.

---

## TwiML — Messaging Verbs

TwiML (Twilio Markup Language) is returned from your webhook endpoint to control message flow.

| Verb | Purpose | Key attributes |
|---|---|---|
| `<Message>` | Send a reply to an inbound message | `to`, `from`, `action`, `method`, `statusCallback` |
| `<Body>` | (nested in `<Message>`) Text content | — |
| `<Media>` | (nested in `<Message>`) Media URL | — |
| `<Redirect>` | Hand off to another TwiML URL | `method` |

**Example — reply with text and media:**
```xml
<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Message>
    <Body>Thanks for your message!</Body>
    <Media>https://example.com/image.jpg</Media>
  </Message>
</Response>
```

**Example — redirect:**
```xml
<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Redirect method="POST">https://yourapp.com/twiml/next</Redirect>
</Response>
```

---

## Webhooks

### Inbound message webhook

Twilio POSTs these fields to your number's configured URL when a message is received:

| Field | Description |
|---|---|
| `MessageSid` | Unique message SID |
| `AccountSid` | Your account SID |
| `From` | Sender's phone number |
| `To` | Your Twilio number |
| `Body` | Message text |
| `NumMedia` | Count of media attachments |
| `MediaUrl0`…`MediaUrl9` | URLs of attached media |
| `MediaContentType0`…`MediaContentType9` | MIME types of media |

### Outbound status callback

Posted to `StatusCallback` URL on every status change — see `references/sms-api.md` for full field list.

---

## Key Operational Notes

- **Link shortening** requires a Messaging Service (`MessagingServiceSid`) and `ShortenUrls: true`.
- **Scheduling** requires a Messaging Service, `ScheduleType: "fixed"`, and `SendAt` (ISO 8601 UTC, 15 min – 7 days in the future).
- **Smart encoding** (`SmartEncoded: true`) replaces Unicode characters with GSM-7 equivalents — reduces segment count and cost.
- **AUP scanning** — Twilio scans outbound content for policy violations; violations return 4xx error codes.
- **Shared media** — if two messages share the same media, the media persists until both messages are deleted.
- **Content API** — use `ContentSid` (`HX…`) with `ContentVariables` for templated messages (WhatsApp Business, RCS).
