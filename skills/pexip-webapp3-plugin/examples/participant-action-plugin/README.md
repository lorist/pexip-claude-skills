# Participant Action Plugin

Pexip webapp3 plugin demonstrating participant interaction patterns:

- **participantActions** button with proper `{ participantUuid }` destructuring
- **participants** event tracking with UUID-to-name map
- **requestParticipants()** RPC with `resp.data.result` access (response wrapping)
- **setRole()** with correct `"host"` / `"guest"` values (not "chair")
- **Dynamic button filtering** via `btn.update({ participantIDs })`
- **Case convention handling** — events use camelCase, RPC uses snake_case

## What It Does

Adds a "Toggle Role" button to each participant's context menu. Clicking it
switches the participant between host and guest roles.

## Build

```bash
npm install
npm run build
```

Output: `dist/` folder ready to install into a branding ZIP at
`plugins/participant-action/`.

## Key Patterns Demonstrated

### Response wrapping
```typescript
const resp = await plugin.conference.requestParticipants({});
const data = resp.data.result; // NOT resp.result
```

### onClick destructuring
```typescript
btn.onClick.add(async ({ participantUuid }) => {
  // { participantUuid } destructures the object
  // (participantUuid) would give the whole object
});
```

### Case conventions
```typescript
// Events: camelCase
plugin.events.participants.add(({ participants }) => {
  participants[0].displayName;  // camelCase
});

// RPC: snake_case
const resp = await plugin.conference.requestParticipants({});
resp.data.result[0].display_name;  // snake_case
```
