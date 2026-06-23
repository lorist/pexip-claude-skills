# Twilio Media Subresource — Reference

Media is a subresource of Messages. Twilio creates a Media record automatically
when an inbound or outbound MMS/WhatsApp message contains an attachment. Media
persists until explicitly deleted.

---

## Limits

| Limit | Value |
|---|---|
| Max media files per message | 10 |
| Max total size per message | 5 MB |
| Image resizing | Twilio resizes to carrier spec; rejects payloads > 5 MB |

---

## Endpoints

Base path: `/2010-04-01/Accounts/{AccountSid}/Messages/{MessageSid}/Media`

### Fetch a single media item
```
GET .../Media/{Sid}.json
```

Path parameters:

| Parameter | Type | Required |
|---|---|---|
| `AccountSid` | SID `AC…` | Yes |
| `MessageSid` | SID `SM…`/`MM…` | Yes |
| `Sid` | SID `ME…` | Yes |

---

### List media for a message
```
GET .../Media.json
```

Query parameters:

| Parameter | Type | Description |
|---|---|---|
| `DateCreated` | datetime | Exact match filter |
| `DateCreatedBefore` | datetime | Upper bound filter |
| `DateCreatedAfter` | datetime | Lower bound filter |
| `PageSize` | integer | Results per page (default 50, max 1000) |
| `Page` | integer | Page index (min 0) |
| `PageToken` | string | Token from previous response |

---

### Delete a media item
```
DELETE .../Media/{Sid}.json
```

Returns `HTTP 204` with no body on success.

> **Note:** If two messages share the same media, the file persists until
> both messages are deleted.

---

## Response Fields (Media Object)

| Field | Type | Description |
|---|---|---|
| `sid` | SID `ME…` | Unique media identifier |
| `account_sid` | SID `AC…` | Owning account |
| `parent_sid` | SID `SM…`/`MM…` | Associated message SID |
| `content_type` | string | MIME type — e.g. `image/jpeg`, `image/png`, `image/gif`, `video/mp4`, `audio/mpeg` |
| `date_created` | RFC 2822 | When the media was created |
| `date_updated` | RFC 2822 | When the media was last updated |
| `uri` | string | Relative API path to this resource |

List responses also include pagination fields: `end`, `first_page_uri`, `next_page_uri`, `page`, `page_size`, `previous_page_uri`, `start`, `uri`, and a `media_list` array.

---

## Caching

- Twilio caches media on first use — may cause a slight delay on initial send.
- Caching respects HTTP headers (`ETag`, `Last-Modified`).
- To force freshness, serve media with `Cache-Control: no-cache`.

---

## Code Examples

### Python — list media for a message
```python
from twilio.rest import Client
import os

client = Client(os.environ["TWILIO_ACCOUNT_SID"], os.environ["TWILIO_AUTH_TOKEN"])

media_list = client.messages("SMxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx").media.list()
for m in media_list:
    print(m.sid, m.content_type, m.uri)
```

### Python — delete media
```python
client.messages("SMxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx") \
      .media("MExxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx") \
      .delete()
```

### Node.js — list media
```javascript
const client = require("twilio")(
  process.env.TWILIO_ACCOUNT_SID,
  process.env.TWILIO_AUTH_TOKEN
);

const mediaItems = await client
  .messages("SMxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx")
  .media
  .list();

mediaItems.forEach(m => console.log(m.sid, m.contentType));
```

### cURL — fetch single media item
```bash
curl -G "https://api.twilio.com/2010-04-01/Accounts/$TWILIO_ACCOUNT_SID/Messages/SMxxx/Media/MExxx.json" \
  -u "$TWILIO_ACCOUNT_SID:$TWILIO_AUTH_TOKEN"
```
