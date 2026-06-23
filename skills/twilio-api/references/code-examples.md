# Twilio SMS — Code Examples

## Environment Setup

Always set credentials as environment variables before running any example:

**macOS / Linux:**
```bash
export TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
export TWILIO_AUTH_TOKEN=your_auth_token_here
```

**Windows (PowerShell):**
```powershell
$env:TWILIO_ACCOUNT_SID="ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
$env:TWILIO_AUTH_TOKEN="your_auth_token_here"
```

---

## Send an Outbound SMS

### Python
```python
import os
from twilio.rest import Client

client = Client(os.environ["TWILIO_ACCOUNT_SID"], os.environ["TWILIO_AUTH_TOKEN"])

message = client.messages.create(
    body="Hello from Twilio!",
    from_="+15017122661",   # Your Twilio number
    to="+15558675310",      # Recipient (must be verified on trial accounts)
)

print(f"Message SID: {message.sid}")
print(f"Status: {message.status}")
```
**Install:** `pip install twilio`

---

### Node.js
```javascript
const twilio = require("twilio");

const client = twilio(
  process.env.TWILIO_ACCOUNT_SID,
  process.env.TWILIO_AUTH_TOKEN
);

async function sendSms() {
  const message = await client.messages.create({
    body: "Hello from Twilio!",
    from: "+15017122661",
    to: "+15558675310",
  });
  console.log(`Message SID: ${message.sid}`);
  console.log(`Status: ${message.status}`);
}

sendSms();
```
**Install:** `npm install twilio`

---

### cURL
```bash
curl -X POST "https://api.twilio.com/2010-04-01/Accounts/$TWILIO_ACCOUNT_SID/Messages.json" \
  --data-urlencode "Body=Hello from Twilio!" \
  --data-urlencode "From=+15017122661" \
  --data-urlencode "To=+15558675310" \
  -u "$TWILIO_ACCOUNT_SID:$TWILIO_AUTH_TOKEN"
```

---

### PHP
```php
<?php
require_once "/path/to/vendor/autoload.php";
use Twilio\Rest\Client;

$client = new Client(getenv("TWILIO_ACCOUNT_SID"), getenv("TWILIO_AUTH_TOKEN"));

$message = $client->messages->create(
    "+15558675310",
    ["body" => "Hello from Twilio!", "from" => "+15017122661"]
);

echo "SID: " . $message->sid . "\n";
```
**Install:** `composer require twilio/sdk`

---

### Java
```java
import com.twilio.Twilio;
import com.twilio.rest.api.v2010.account.Message;
import com.twilio.type.PhoneNumber;

public class SendSms {
    public static void main(String[] args) {
        Twilio.init(
            System.getenv("TWILIO_ACCOUNT_SID"),
            System.getenv("TWILIO_AUTH_TOKEN")
        );

        Message message = Message.creator(
                new PhoneNumber("+15558675310"),
                new PhoneNumber("+15017122661"),
                "Hello from Twilio!")
            .create();

        System.out.println("SID: " + message.getSid());
    }
}
```

---

### C# (.NET)
```csharp
using Twilio;
using Twilio.Rest.Api.V2010.Account;

TwilioClient.Init(
    Environment.GetEnvironmentVariable("TWILIO_ACCOUNT_SID"),
    Environment.GetEnvironmentVariable("TWILIO_AUTH_TOKEN")
);

var message = await MessageResource.CreateAsync(
    body: "Hello from Twilio!",
    from: new Twilio.Types.PhoneNumber("+15017122661"),
    to: new Twilio.Types.PhoneNumber("+15558675310")
);

Console.WriteLine($"SID: {message.Sid}");
```
**Install:** `dotnet add package Twilio`

---

### Go
```go
package main

import (
    "fmt"
    "os"
    "github.com/twilio/twilio-go"
    api "github.com/twilio/twilio-go/rest/api/v2010"
)

func main() {
    client := twilio.NewRestClient()

    params := &api.CreateMessageParams{}
    params.SetBody("Hello from Twilio!")
    params.SetFrom("+15017122661")
    params.SetTo("+15558675310")

    resp, err := client.Api.CreateMessage(params)
    if err != nil {
        fmt.Fprintln(os.Stderr, err.Error())
        os.Exit(1)
    }
    fmt.Println("SID:", *resp.Sid)
}
```
**Install:** `go get github.com/twilio/twilio-go`

---

## Send MMS (with media)

### Python
```python
message = client.messages.create(
    body="Check out this image!",
    from_="+15017122661",
    to="+15558675310",
    media_url=["https://example.com/image.jpg"],
)
```

---

## Receive and Reply to Inbound SMS (Python / Flask)

```python
from flask import Flask, request, Response
from twilio.twiml.messaging_response import MessagingResponse

app = Flask(__name__)

@app.route("/sms", methods=["POST"])
def reply_sms():
    incoming = request.form.get("Body", "")
    print(f"Received: {incoming}")

    resp = MessagingResponse()
    resp.message(f"You said: {incoming}")
    return Response(str(resp), mimetype="text/xml")

if __name__ == "__main__":
    app.run(debug=True, port=5000)
```

**Local testing with ngrok:**
```bash
ngrok http 5000
# Copy the HTTPS URL → Twilio Console → Phone Numbers → Messaging → "A message comes in"
```

---

## Schedule a Message (Messaging Service required)

### Python
```python
from datetime import datetime, timezone, timedelta

send_time = datetime.now(timezone.utc) + timedelta(hours=2)

message = client.messages.create(
    messaging_service_sid="MGxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
    body="This message is scheduled!",
    to="+15558675310",
    schedule_type="fixed",
    send_at=send_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
)
print(f"Scheduled SID: {message.sid}, Status: {message.status}")
```

---

## Check Delivery Status

### Python — Poll once
```python
msg = client.messages(message_sid).fetch()
print(f"Status: {msg.status}")
print(f"Error: {msg.error_code} — {msg.error_message}")
```

### Python — StatusCallback webhook (Flask)
```python
@app.route("/status", methods=["POST"])
def status_callback():
    sid    = request.form["MessageSid"]
    status = request.form["MessageStatus"]
    error  = request.form.get("ErrorCode", "")
    print(f"{sid} → {status} {error}")
    return "", 204
```

Pass `status_callback="https://yourapp.com/status"` when creating the message.

---

## Redact Message Body

```python
client.messages(message_sid).update(body="")
```

---

## Cancel a Scheduled Message

```python
client.messages(message_sid).update(status="canceled")
```
