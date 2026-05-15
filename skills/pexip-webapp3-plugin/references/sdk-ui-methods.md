# Plugin SDK UI Methods Reference

Complete reference for `plugin.ui.*` methods available to webapp3 plugins.

---

## addButton

Add a button to the meeting UI. Returns a button object with `onClick` and
`update` methods.

```typescript
const btn = await plugin.ui.addButton({
  position: 'toolbar' | 'participantActions',
  label: string,
  icon?: string,
  tooltip?: string,
});
```

### Toolbar buttons

Appear in the meeting toolbar (bottom of screen):

```typescript
const btn = await plugin.ui.addButton({
  position: 'toolbar',
  label: 'My Action',
  icon: 'IconChat',
  tooltip: 'Do something useful',
});

btn.onClick.add(async () => {
  // Handler runs on click
  plugin.ui.showToast({ message: 'Button clicked' });
});
```

### Participant action buttons

Appear in the context menu when clicking a participant in the roster:

```typescript
const btn = await plugin.ui.addButton({
  position: 'participantActions',
  label: 'Send to Lobby',
});

btn.onClick.add(async ({ participantUuid }) => {
  // CRITICAL: onClick receives { participantUuid: "uuid-string" }
  // NOT a bare UUID string. Destructure the object.
  console.log('Clicked on participant:', participantUuid);
});
```

**Gotcha:** if you write `(participantUuid) =>` instead of
`({ participantUuid }) =>`, the variable contains the entire
`{ participantUuid: "..." }` object. Using it directly in a URL produces
`[object Object]`. **(field-tested)**

### Dynamic updates

Update a button's label, visibility, or eligible participants at runtime:

```typescript
// Filter which participants see the action button
btn.update({
  position: 'participantActions',
  label: 'Send to Lobby',
  participantIDs: eligibleUuids,  // Only show for these participants
});
```

```typescript
// Toggle a toolbar button label/icon based on state
let isActive = false;
btn.onClick.add(async () => {
  isActive = !isActive;
  btn.update({
    position: 'toolbar',
    label: isActive ? 'Stop' : 'Start',
    icon: isActive ? 'IconStop' : 'IconPlay',
  });
});
```

### Common icon names

Icons must be valid webapp3 icon identifiers:

| Icon | Description |
|---|---|
| `IconChat` | Chat bubble |
| `IconMicrophone` | Microphone |
| `IconMicrophoneOff` | Muted microphone |
| `IconCamera` | Camera |
| `IconCameraOff` | Camera off |
| `IconPresentation` | Screen share |
| `IconSettings` | Gear/settings |
| `IconParticipants` | People/roster |
| `IconMore` | Three dots/overflow |
| `IconLock` | Lock |
| `IconRecord` | Record (circle) |

---

## showToast

Display a temporary notification banner:

```typescript
plugin.ui.showToast({
  message: string,       // Required: text to show
  isDanger?: boolean,    // Red/error styling (default false)
  type?: 'info' | 'warning',  // Toast style variant
  duration?: number,     // Display duration in ms
});
```

Examples:

```typescript
// Success notification
plugin.ui.showToast({ message: 'Message sent to 3 endpoints' });

// Error notification
plugin.ui.showToast({ message: 'Failed to reach server', isDanger: true });
```

---

## showForm

Display a modal dialog with input fields. Returns the form values on submit,
or `undefined` if cancelled:

```typescript
const result = await plugin.ui.showForm({
  title: string,
  description?: string,
  form: {
    elements: {
      [fieldName: string]: {
        name: string,          // Display label
        type: 'text' | 'select' | 'checkbox' | 'password',
        isOptional?: boolean,  // default false
        value?: string,        // Pre-filled value
        placeholder?: string,
        options?: Array<{ id: string; label: string }>,  // For 'select' type
      },
    },
    submitBtnTitle?: string,   // default "Submit"
  },
});
```

Example — text input:

```typescript
const input = await plugin.ui.showForm({
  title: 'Send Message',
  description: 'Type your message below:',
  form: {
    elements: {
      message: { name: 'Message', type: 'text', isOptional: false },
    },
    submitBtnTitle: 'Send',
  },
});

if (!input) return; // User cancelled
const text = input.message;
```

Example — select dropdown:

```typescript
const input = await plugin.ui.showForm({
  title: 'Choose Layout',
  form: {
    elements: {
      layout: {
        name: 'Meeting Layout',
        type: 'select',
        options: [
          { id: '1:0', label: 'Speaker only' },
          { id: '4:0', label: 'Grid 2x2' },
          { id: '9:0', label: 'Grid 3x3' },
        ],
      },
    },
  },
});

if (input) {
  console.log('Selected layout:', input.layout);
}
```

**Return value:** An object keyed by field name with string values, or
`undefined` if the user closes the dialog without submitting.
