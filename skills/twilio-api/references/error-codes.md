# Twilio SMS — Common Error Codes

When a message has `status: failed` or `status: undelivered`, check the
`error_code` and `error_message` fields on the Message resource.

---

## Most Common Errors

| Code | Name | Cause | Fix |
|---|---|---|---|
| **21211** | Invalid 'To' phone number | Number not in E.164 format, or non-existent | Ensure format is `+15558675310`; validate with a number lookup |
| **21214** | 'To' phone number cannot receive SMS | Number is landline or doesn't support SMS | Use a mobile number; consider voice fallback |
| **21219** | 'To' number not verified | Trial account — recipient not in Verified Caller IDs | Verify the number in Twilio Console, or upgrade account |
| **21401** | Invalid SID | Malformed Account SID | Check `TWILIO_ACCOUNT_SID` — must start with `AC` |
| **21408** | Permission to send to this region denied | Geo permissions disabled for destination country | Enable in Console → Messaging → Geo Permissions |
| **21610** | Message body is required | Empty `Body` with no `MediaUrl` or `ContentSid` | Provide a non-empty `Body` |
| **21611** | From number has no SMS capability | Number doesn't support SMS | Use an SMS-capable number; check Console → Phone Numbers |
| **21612** | 'From' and 'To' cannot be the same | Sender = recipient | Use a different `To` number |
| **21614** | 'To' number not mobile | Landline or VOIP number | Use a mobile number |
| **21617** | Message body exceeds 1,600 characters | Body too long | Truncate or split into multiple messages |
| **30001** | Queue overflow | Too many outbound messages queued | Reduce send rate; use Messaging Services with rate limits |
| **30002** | Account suspended | Account suspended by Twilio | Check Twilio Console for alerts / billing issues |
| **30003** | Unreachable destination handset | Phone off, out of coverage, or number deactivated | Retry later; consider removing from list after repeated failures |
| **30004** | Message blocked | Carrier or Twilio blocked (spam/opt-out) | Check if recipient opted out; review content for spam triggers |
| **30005** | Unknown destination handset | Number not in carrier database | Validate number with Twilio Lookup before sending |
| **30006** | Landline or unreachable carrier | Carrier doesn't support SMS | Use voice or confirm number is mobile |
| **30007** | Carrier violation | Content flagged by carrier filter | Review message content; avoid spam triggers, URL shorteners |
| **30008** | Unknown error | Carrier returned generic failure | Retry; if persistent, check Twilio Status page |
| **63016** | Failed to queue message | Messaging Service could not queue | Check MessagingServiceSid; verify service is active |

---

## Error Response Body

On a `4xx` response, Twilio returns JSON:

```json
{
  "code": 21219,
  "message": "The number +15558675310 is unverified. Trial accounts cannot send to unverified numbers.",
  "more_info": "https://www.twilio.com/docs/errors/21219",
  "status": 400
}
```

Always check `error.code` (not just HTTP status) for actionable diagnosis.

---

## Debugging checklist

1. **HTTP status 401** → Wrong Account SID or Auth Token
2. **HTTP status 400** → Bad request parameters — read the `code` field
3. **status: failed** (after send accepted) → Carrier rejection — check `error_code` on fetched message
4. **status: undelivered** → Message reached carrier but not handset — often opt-out or unreachable
5. **No status callback received** → Callback URL not HTTPS, or not publicly accessible; test with ngrok
