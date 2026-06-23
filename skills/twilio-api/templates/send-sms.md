# Template — Send SMS Response

Use this template when helping a user send an SMS. Fill every section.

---

## Setup

```bash
# Install SDK
pip install twilio   # or: npm install twilio

# Set credentials
export TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
export TWILIO_AUTH_TOKEN=your_auth_token_here
```

## Code

```python
# [language-specific snippet from references/code-examples.md]
```

## Expected output

```
Message SID: SMxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
Status: queued
```

## Delivery confirmation

To confirm delivery, either:
- Poll: `client.messages("<SID>").fetch().status`
- Webhook: pass `status_callback="https://yourapp.com/status"` when creating

## Trial account note

> If on a trial account, `To` must be verified at twilio.com/console under
> **Phone Numbers → Verified Caller IDs**. Unverified numbers return error 21219.
