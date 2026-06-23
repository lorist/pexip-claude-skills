# Twilio Messages Resource API Reference

## Base URL

```
https://api.twilio.com/2010-04-01/Accounts/{AccountSid}/Messages.json
```

Authentication: HTTP Basic Auth — Account SID as username, Auth Token as password.

---

## Endpoints

| Operation | Method | URL |
|---|---|---|
| Send (create) | POST | `.../Messages.json` |
| Fetch one | GET | `.../Messages/{Sid}.json` |
| List all | GET | `.../Messages.json` |
| Update / cancel / redact | POST | `.../Messages/{Sid}.json` |
| Delete | DELETE | `.../Messages/{Sid}.json` |

---

## Create Message — Request Parameters

### Required (at least one from each group)

**Recipient:**

| Parameter | Type | Description |
|---|---|---|
| `To` | string (E.164) | Recipient phone number, e.g. `+15558675310`. For channels: `whatsapp:+15552229999` |

**Sender (one of):**

| Parameter | Type | Description |
|---|---|---|
| `From` | string | Your Twilio number, short code, or channel address |
| `MessagingServiceSid` | SID `MG…` | Messaging Service — Twilio selects sender dynamically |

**Content (one of):**

| Parameter | Type | Description |
|---|---|---|
| `Body` | string | SMS/MMS text — up to 1,600 characters |
| `MediaUrl` | array[uri] | Up to 10 media URLs for MMS |
| `ContentSid` | SID `HX…` | Content API template SID |

### Optional

| Parameter | Type | Default | Description |
|---|---|---|---|
| `StatusCallback` | uri | — | HTTPS webhook called on every status change |
| `ApplicationSid` | SID `AP…` | — | TwiML App whose `message_status_callback` receives status posts |
| `ValidityPeriod` | integer | 36000 | Seconds to keep message in queue (1–36000). Use >5s |
| `SmartEncoded` | boolean | false | Replace Unicode with GSM-7 equivalents to reduce segments |
| `ProvideFeedback` | boolean | false | Enable delivery confirmation feedback |
| `ShortenUrls` | boolean | false | Shorten URLs (requires `MessagingServiceSid`) |
| `ScheduleType` | enum | — | Set to `fixed` to schedule; use with `SendAt` |
| `SendAt` | ISO 8601 | — | Future send time (requires `MessagingServiceSid` + `ScheduleType=fixed`) |
| `SendAsMms` | boolean | false | Force delivery as MMS regardless of media |
| `ContentVariables` | JSON string | — | Variable substitutions for Content API templates |
| `RiskCheck` | enum | enable | `enable` or `disable` fraud risk checking |
| `FallbackFrom` | string | — | SMS fallback sender when RCS recipient unreachable |

---

## Response Fields

| Field | Type | Description |
|---|---|---|
| `sid` | SID `SM…`/`MM…` | Unique message identifier |
| `account_sid` | SID `AC…` | Owning account |
| `body` | string | Message text (may be redacted to `""`) |
| `status` | enum | Current status (see below) |
| `direction` | enum | `inbound`, `outbound-api`, `outbound-call`, `outbound-reply` |
| `from` | string | Sender phone/channel address |
| `to` | string | Recipient phone/channel address |
| `date_created` | RFC 2822 | Resource creation time |
| `date_sent` | RFC 2822 | When Twilio sent or received the message |
| `date_updated` | RFC 2822 | Last update time |
| `num_segments` | string | Number of SMS segments (starts `"0"` for Messaging Service sends) |
| `num_media` | string | Count of attached media files |
| `price` | string | Billed amount — may be `null` until delivery confirmed |
| `price_unit` | string | ISO 4217 currency code, e.g. `usd` |
| `error_code` | integer | Error code if `failed`/`undelivered`; else `null` |
| `error_message` | string | Human-readable error description; else `null` |
| `messaging_service_sid` | SID `MG…` | Associated Messaging Service, if used |
| `api_version` | string | API version used |
| `uri` | string | Relative URI of this resource |
| `subresource_uris` | object | Map to media, feedback sub-resources |

---

## Message Status Values

| Status | Direction | Meaning |
|---|---|---|
| `queued` | Outbound | Accepted; awaiting dispatch from specific sender |
| `accepted` | Outbound (Service) | Service accepted; dynamically selecting sender |
| `scheduled` | Outbound (Service) | Scheduled for future delivery |
| `sending` | Outbound | Dispatching to upstream carrier |
| `sent` | Outbound | Carrier accepted the message |
| `delivered` | Outbound | Carrier/handset confirmed delivery |
| `undelivered` | Outbound | Delivery receipt shows failure (content filtering, etc.) |
| `failed` | Outbound | Could not send (queue overflow, suspension, media error) |
| `receiving` | Inbound | Twilio received and is processing |
| `received` | Inbound | Processing complete |
| `read` | Outbound (RCS/WhatsApp) | Recipient opened message |
| `canceled` | Outbound (Service) | Scheduled message was canceled |

---

## Status Callback Payload

Twilio POSTs these fields to your `StatusCallback` URL on each status change:

| Field | Description |
|---|---|
| `MessageSid` | Message SID |
| `MessageStatus` | Status at time of callback |
| `ErrorCode` | Present when `failed` or `undelivered` |
| `To` | Recipient number |
| `From` | Sender number |
| `RawDlrDoneDate` | SMS/MMS only — carrier DLR date `YYMMDDhhmm` |

Validate authenticity using the Twilio SDK's `RequestValidator` — do not implement custom validation.

---

## List Messages — Query Parameters

| Parameter | Type | Description |
|---|---|---|
| `To` | string | Filter by recipient |
| `From` | string | Filter by sender |
| `DateSent` | date `YYYY-MM-DD` | Exact date filter |
| `DateSentBefore` | date | Sent on or before |
| `DateSentAfter` | date | Sent on or after |
| `PageSize` | integer | Results per page (default 50, max 1000) |
| `PageToken` | string | Pagination token from previous response |

Results ordered by `DateSent`, most recent first.

---

## Update / Redact / Cancel

POST to `.../Messages/{Sid}.json`:

| Parameter | Value | Effect |
|---|---|---|
| `Body` | `""` | Redact message body from logs |
| `Status` | `canceled` | Cancel a scheduled message |

---

## Important Notes

### SMS Segmentation & Billing
- **GSM-7** encoding: segments at 160 chars; multi-segment at 153 chars each
- **UCS-2** (emoji, special chars): segments at 70 chars; multi-segment at 67 chars each
- Each segment billed separately — use `SmartEncoded: true` to minimise cost

### Trial Account Restrictions
- `To` number must be verified in Twilio Console
- Messages prepend "Sent from your Twilio trial account — "
- Error 21219 if sending to unverified number

### Rate Limits
- Messages queued at your prescribed rate limit
- Use Messaging Services for high-volume sends
- Default `ValidityPeriod` is 36,000 seconds (10 hours) — set lower for time-sensitive messages
