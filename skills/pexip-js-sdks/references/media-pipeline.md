# Media pipeline: `@pexip/media` + `@pexip/media-processor` + `@pexip/media-control`

Three packages that together cover capture, effects, and runtime device
control. They're meant to be composed; the docs show each in isolation
which makes it hard to see the shape.

## The pipeline, end to end

```
1.  navigator.mediaDevices.getUserMedia({ audio, video })
              │
              ▼
2.  @pexip/media          ← capture wrapper, holds the active MediaStream
              │
              ▼
3.  @pexip/media-processor (optional) ← background blur / denoise
              │     emits a NEW MediaStream
              ▼
4.  infinityClient.call({ mediaStream: <processed> })
              ▲
              │ device hot-swap or mute
5.  @pexip/media-control mutates the active stream in place
```

The packages have clean boundaries:

- **`@pexip/media`** holds the *current* captured stream. It doesn't
  know about effects or the conference client.
- **`@pexip/media-processor`** is a pure transform: stream in, stream
  out. It doesn't know about the conference client either.
- **`@pexip/media-control`** is the runtime control surface: switch
  cameras, swap mics, toggle mute. It knows how to update the active
  stream without re-negotiating SDP.

## Capture (`@pexip/media`)

The bare minimum:

```ts
import { createMediaStream } from "@pexip/media";

const stream = await createMediaStream({
  audio: true,
  video: { width: 1280, height: 720 },
});
```

This is `getUserMedia` plus device fallback (try preferred device, fall
back to defaults if denied). The stream you get back is a normal
`MediaStream` — you can hand it straight to `infinityClient.call()` if
you don't need effects.

## Effects (`@pexip/media-processor`)

The package is heavy because it pulls a MediaPipe segmentation model
(for blur/virtual background) and an AudioWorklet (for denoise). Both
are lazy-load candidates.

### Background blur

```ts
import { createVideoProcessor } from "@pexip/media-processor";

const videoProcessor = createVideoProcessor({
  effects: "blur",
});

const processedStream = await videoProcessor.process(stream);
//                                                    ^^^^^^
//                              the original captured stream

await infinityClient.call({
  mediaStream: processedStream,    // pass the processed one
  // ...
});
```

**The cardinal mistake** is passing `stream` (the original) to `.call()`
instead of `processedStream`. Pexip will dutifully send the unblurred
camera feed to the conference. There's no warning. Always pass the
output of the processor.

### Virtual background

Same pattern, different effect:

```ts
const videoProcessor = createVideoProcessor({
  effects: "background",
  backgroundImage: "/assets/office.jpg",
});
```

### Denoise

Audio path is symmetric:

```ts
import { createAudioProcessor } from "@pexip/media-processor";

const audioProcessor = createAudioProcessor({ effects: "denoise" });
const processedStream = await audioProcessor.process(stream);
```

You can compose audio + video processors on the same stream — process
video first, then pass the result through the audio processor. Order
doesn't strictly matter for blur+denoise (they touch different tracks)
but pick one and stick to it for predictability.

### Disabling effects

Re-process with `effects: "none"` to get a stream with no transforms.
Don't try to "remove" the processor from a stream — replace the stream.

## Runtime control (`@pexip/media-control`)

The package that handles "change devices mid-call" and the muted-state
machine.

### Hot-swap a device

```ts
import { setStream } from "@pexip/media-control";

const newStream = await navigator.mediaDevices.getUserMedia({
  video: { deviceId: { exact: newCameraId } },
  audio: true,
});

setStream(newStream);
//   ↑ updates the active stream; @pexip/infinity picks it up via signal
```

This avoids the SDP renegotiation that PexRTC requires. The new track
slots into the existing peer connection.

### Mute / unmute

The mute state lives in `@pexip/media-control` — not on the stream
itself, not on the infinity client. React components that mirror it
should subscribe to the relevant `BehaviorSignal`.

```ts
import { setMuted } from "@pexip/media-control";
setMuted({ audio: true });
```

### Why a separate package?

You could `track.enabled = false` directly on a `MediaStreamTrack` and
call it muting. The package exists because:

- It coordinates with the rest of the stack (UI components reflect
  state).
- It handles the "muted before joining" case (mute state must persist
  across `infinityClient.call()`).
- It encapsulates the device-swap-without-renegotiate dance.

## Composing all three

Real-world wiring:

```ts
import { createMediaStream } from "@pexip/media";
import { createVideoProcessor, createAudioProcessor } from "@pexip/media-processor";
import { setStream } from "@pexip/media-control";

const raw = await createMediaStream({ audio: true, video: true });
const blurred = await createVideoProcessor({ effects: "blur" }).process(raw);
const cleaned = await createAudioProcessor({ effects: "denoise" }).process(blurred);

setStream(cleaned);                    // tell media-control about it
await infinityClient.call({ mediaStream: cleaned, /* … */ });
```

Now device hot-swap, mute, and effects all work coherently.

## Mobile notes

- **Screen share is unavailable.** `getDisplayMedia()` silently fails on
  mobile Chrome and Safari. Detect platform and hide the button.
- **Background blur is heavy.** MediaPipe is fine on a desktop, painful
  on a low-end Android. Make blur opt-in on mobile, not default-on.
- **Camera switch is slow.** The track-replace dance has visible UI
  pause on iOS Safari. Show a loading state.

## Debugging

If audio/video isn't reaching the conference but `infinityClient.call()`
returned without error:

1. Check the stream you passed has live tracks: `stream.getTracks().forEach(t => console.log(t.kind, t.readyState, t.enabled))`. `readyState` should be `"live"`.
2. Check you passed the **processed** stream (post-`processor.process()`),
   not the original.
3. Check the participant tile in the conference UI — your tile shows
   what Pexip thinks it's receiving from you. If it's black,
   the track is dead before it left the browser.
4. If running over a corporate network, check TURN reachability — see
   `pexip-client-api` skill §multi-node and `pexip-call-rca` for
   ICE-failure patterns.
