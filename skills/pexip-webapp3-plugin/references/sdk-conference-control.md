# Plugin SDK Conference Control Reference

Methods for controlling the conference and participants from a webapp3 plugin.

---

## requestParticipants

Fetch the current participant list via RPC (not events):

```typescript
const resp = await plugin.conference.requestParticipants({});
const participants = resp.data.result;
// IMPORTANT: resp.data.result, not resp.result (response wrapping)
```

Response participants use **snake_case** field names:

```typescript
interface RpcParticipant {
  uuid: string;
  display_name: string;     // NOT displayName
  overlay_text: string;     // NOT overlayText
  role: 'chair' | 'guest'; // ⚠️ RPC returns 'chair', but setRole() requires 'host'
  protocol: string;
  is_muted: string;         // "Yes" / "No" (string, not boolean)
  is_presenting: string;
  service_type: string;
  spotlight: number;
  call_direction: string;
}
```

**Case convention split:** events use camelCase (`displayName`), RPC uses
snake_case (`display_name`). Code that consumes both must handle this.
**(field-tested)**

**Role mapping:** RPC returns `'chair'` but `setRole()` requires `'host'`.
You must convert: `target.role === 'chair' ? 'host' : target.role`.
Passing `'chair'` to `setRole()` is silently rejected.

**Display name preference:** For user-facing labels, prefer `overlay_text`
over `display_name` — it contains the "formal" name set by the host or
policy server. Fallback chain:

```typescript
const label = participant.overlay_text || participant.display_name || 'Participant';
```

**(field-tested)**

---

## setRole

Change a participant's role between host and guest:

```typescript
await plugin.conference.setRole({
  participantUuid: string,   // Target participant
  role: 'host' | 'guest',   // MUST be "host"/"guest"
});
```

**Gotcha:** the Client API uses `"host"` / `"guest"`. Using `"chair"` /
`"guest"` (the policy server convention) is rejected. **(field-tested)**

---

## sendRequest

Generic method for any Client API call that lacks a dedicated SDK method:

```typescript
const resp = await plugin.conference.sendRequest({
  method: 'GET' | 'POST' | 'PATCH' | 'DELETE',
  path: string,      // Relative to /api/client/v2/conferences/<alias>/
  payload?: object,   // JSON body for POST/PATCH
});
```

All responses follow the wrapper pattern:
```typescript
// { status: number, data: { status: string, result: any } }
const value = resp.data.result;
```

### Common sendRequest paths

| Method | Path | Payload | Description |
|---|---|---|---|
| POST | `set_message_text` | `{ text: "..." }` | Set banner/overlay text |
| GET | `get_message_text` | — | Read current banner text |
| POST | `lock` | — | Lock the conference |
| POST | `unlock` | — | Unlock the conference |
| POST | `muteall` | — | Mute all guests |
| POST | `unmuteall` | — | Unmute all guests |
| POST | `disconnect` | — | Disconnect self |
| POST | `breakouts/{uuid}/set_message_text` | `{ text: "..." }` | Banner in breakout room |

**There is no `setMessageText` method** on the SDK. Always use `sendRequest`
with `path: 'set_message_text'`. Attempting to call `plugin.conference.setMessageText()`
throws a method-not-found error. **(field-tested)**

---

## Breakout Rooms

### Create a breakout room

```typescript
const result = await plugin.conference.breakout({
  name: string,                    // Room name
  end_action: 'transfer' | 'disconnect',  // What happens when room closes
});
const breakoutUuid = result.breakout_uuid;
```

### Move participants into a breakout

```typescript
await plugin.conference.breakoutMoveParticipants({
  toRoomUuid: breakoutUuid,
  participants: [participantUuid1, participantUuid2],
});
```

### Close a breakout room

```typescript
await plugin.conference.closeBreakoutRoom({
  breakoutUuid: breakoutUuid,
});
```

When `end_action: 'transfer'`, participants transfer back to the main room.
Their role on return matches what it was when they entered the breakout.

### Send-to-lobby pattern

Move a participant from an active conference back to the lobby. No direct
"send to lobby" API exists; use this breakout-based workaround:

```typescript
async function sendToLobby(
  plugin: any,
  participantUuid: string,
  displayName?: string,
): Promise<void> {
  try {
    // 1. Demote to guest — ensures they return as guest (lobby-eligible)
    await plugin.conference.setRole({ participantUuid, role: 'guest' });

    // 2. Create a temporary breakout with transfer-back
    const room = await plugin.conference.breakout({
      name: 'lobby-transfer',
      end_action: 'transfer',
    });

    // 3. Move participant into the breakout
    await plugin.conference.breakoutMoveParticipants({
      toRoomUuid: room.breakout_uuid,
      participants: [participantUuid],
    });

    // 4. Wait for the move to complete, then close the room
    await new Promise((r) => setTimeout(r, 3000));
    await plugin.conference.closeBreakoutRoom({
      breakoutUuid: room.breakout_uuid,
    });

    plugin.ui.showToast({ message: `${displayName || 'Participant'} sent to lobby` });
  } catch (error) {
    console.error('Send to lobby failed:', error);
    plugin.ui.showToast({
      message: `Failed to send ${displayName || 'participant'} to lobby`,
      isDanger: true,
    });
  }
}
```

Production plugins always wrap multi-step conference operations in try/catch with `isDanger` toast on failure and success toast on completion. **(field-tested)**

This pattern is used in production by the send-to-lobby plugin (v13).
The 3-second delay is necessary for Pexip to complete the room move before
the close fires. **(field-tested)**

---

## Per-Participant Actions via sendRequest

For participant-level actions not covered by dedicated methods:

```typescript
// Mute a specific participant
await plugin.conference.sendRequest({
  method: 'POST',
  path: `participants/${participantUuid}/mute`,
});

// Unmute
await plugin.conference.sendRequest({
  method: 'POST',
  path: `participants/${participantUuid}/unmute`,
});

// Spotlight
await plugin.conference.sendRequest({
  method: 'POST',
  path: `participants/${participantUuid}/spotlighton`,
});

// Transfer to another conference
await plugin.conference.sendRequest({
  method: 'POST',
  path: `participants/${participantUuid}/transfer`,
  payload: { conference_alias: 'other-vmr', role: 'host' },
});

// Disconnect a specific participant
await plugin.conference.sendRequest({
  method: 'POST',
  path: `participants/${participantUuid}/disconnect`,
});
```
