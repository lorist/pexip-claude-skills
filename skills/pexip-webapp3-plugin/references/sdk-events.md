# Plugin SDK Events Reference

Complete reference for `plugin.events.*` signals available to webapp3 plugins
via `@pexip/plugin-api`.

## Subscription Pattern

All events use the same signal pattern:

```typescript
plugin.events.<eventName>.add((value) => {
  // value is the payload — NEVER destructure as ({value}) =>
});
```

Signals can have multiple listeners. Remove a listener by storing the
reference:

```typescript
const handler = (value) => console.log(value);
plugin.events.message.add(handler);
// Later:
plugin.events.message.remove(handler);
```

---

## authenticatedWithConference

Fires once when the user successfully joins a conference (after token
exchange and any SSO flow).

```typescript
interface AuthenticatedWithConferenceEvent {
  conferenceAlias: string;    // The alias used to join
  conferenceName: string;     // Display name of the conference
  role: 'host' | 'guest';    // User's role
  serviceType: string;        // e.g. "conference"
  analyticsEnabled: boolean;
  chatEnabled: boolean;
  guestsCanPresent: boolean;
  directMedia: boolean;
}
```

```typescript
plugin.events.authenticatedWithConference.add((info) => {
  console.log(`Joined: ${info.conferenceAlias} as ${info.role}`);
});
```

**Gotcha:** some fields may appear under different names depending on Pexip
version. Defensive access: `info.conferenceAlias || info.conference_alias`.

**Conference alias at init time:** `authenticatedWithConference` fires
asynchronously after join. If you need the alias earlier (e.g., during
plugin initialization), parse it from the URL:

```typescript
function getConferenceAlias(): string {
  // 1. Own URL hash params: /#/?conference=alias
  const hashParams = new URLSearchParams(window.location.hash.split('?')[1] || '');
  if (hashParams.get('conference')) return hashParams.get('conference')!;

  // 2. Parent frame URL hash params (same-origin only)
  try {
    const parentHash = new URLSearchParams(
      window.parent.location.hash.split('?')[1] || ''
    );
    if (parentHash.get('conference')) return parentHash.get('conference')!;
  } catch { /* cross-origin */ }

  // 3. URL pathname fallback: /meetingname/ -> "meetingname"
  const path = window.location.pathname.replace(/^\/|\/$/g, '');
  if (path) return path;

  return '';
}
```

Use the sync result as an early value, then update from the event when it fires.
**(field-tested)**

---

## me

Fires when the current user's participant info changes (initial join, name
update, role change).

```typescript
interface MeEvent {
  participant: {
    displayName: string;
    uuid: string;
    role: 'host' | 'guest';
    overlayText: string;
    isMuted: boolean;
    isPresenting: boolean;
    protocol: string;
    callTag: string;
  };
}
```

```typescript
let myName = '';
plugin.events.me.add((me) => {
  myName = me.participant.displayName;
});
```

---

## participants

Fires whenever the participant list changes (join, leave, role change, mute
state change).

```typescript
interface ParticipantsEvent {
  participants: Array<{
    uuid: string;           // ParticipantID
    displayName: string;    // camelCase in events
    overlayText: string;
    role: 'host' | 'guest';
    protocol: string;       // "webrtc", "sip", "api", "rtmp", ...
    isMuted: boolean;
    isPresenting: boolean;
    isWaiting: boolean;     // true = in lobby, not yet admitted
    callTag: string;
    spotlight: boolean;
  }>;
}
```

```typescript
const nameMap = new Map<string, string>();

plugin.events.participants.add(({ participants }) => {
  nameMap.clear();
  for (const p of participants) {
    nameMap.set(p.uuid, p.displayName);
  }
});
```

**Note:** participant fields use **camelCase** here (`displayName`,
`overlayText`, `isWaiting`). This differs from RPC responses which use
**snake_case** (`display_name`, `overlay_text`, `is_waiting`).

---

## message

Fires when a chat message arrives from **another** participant. Messages you
send yourself do NOT trigger this event.

```typescript
interface MessageEvent {
  payload: string;          // Message text
  displayName: string;      // Sender's display name (camelCase)
  senderName: string;       // Alternative sender name
  uuid: string;             // Sender's participant UUID
  type: string;             // Content type
  direct: boolean;          // Whether it was a direct message
}
```

```typescript
plugin.events.message.add((msg) => {
  console.log(`${msg.displayName}: ${msg.payload}`);
});
```

**Critical gotchas:**
- Only fires for OTHER participants' messages — own messages are never echoed
- The sender must use content type `text/plain`. If the Client API sends the
  message with `application/json`, `plugin.events.message` **never fires**.
  **(field-tested, Pexip v39+)**
- Requires 2+ participants to test

---

## directMessage

Optional event. Not all Pexip versions support it. Guard before subscribing:

```typescript
if ((plugin.events as any).directMessage) {
  (plugin.events as any).directMessage.add((msg) => {
    console.log('Direct:', msg.payload);
  });
}
```

Payload shape is the same as `message`.

---

## applicationMessage

Optional event for application-level messages (non-chat). Same guard pattern
and payload shape as `directMessage`:

```typescript
if ((plugin.events as any).applicationMessage) {
  (plugin.events as any).applicationMessage.add((msg) => {
    handleAppMessage(msg);
  });
}
```

---

## presentationConnectionStateChange

Fires when screen sharing starts or stops.

```typescript
interface PresentationStateEvent {
  state: 'connected' | 'disconnected' | 'connecting';
}
```

```typescript
plugin.events.presentationConnectionStateChange.add((event) => {
  console.log('Presentation:', event.state);
});
```

---

## conferenceStatus

Fires when conference-level state changes (lock state, recording state,
live captions).

```typescript
interface ConferenceStatusEvent {
  isLocked: boolean;
  isRecording: boolean;
  liveCaptionsAvailable: boolean;
  guestsCanPresent: boolean;
  guestsMuted: boolean;
}
```

```typescript
plugin.events.conferenceStatus.add((status) => {
  if (status.isLocked) {
    plugin.ui.showToast({ message: 'Conference locked' });
  }
});
```
