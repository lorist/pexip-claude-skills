# `@pexip/signal` deep dive

The event primitive every higher Pexip package uses. Trips up new devs
because the API looks like nothing else they've seen — it's not RxJS,
not EventEmitter, not Promises.

## The mental model

A **signal** is a typed channel. Producers `.emit(value)`. Consumers
`.add(handler)` and get back a **detach function** they call to
unsubscribe. That's it. No `.subscribe()` returning a Subscription. No
`.on(name, fn)` / `.off()`. No event names — each signal *is* the event.

```ts
import { createSignal } from "@pexip/signal";

const tick = createSignal<{ time: number }>({ name: "tick" });

const detach = tick.add((value) => {
  console.log("tick at", value.time);
});

tick.emit({ time: Date.now() });   // handler fires
detach();                          // handler stops firing
```

Pexip's higher packages wrap this — you don't usually create signals
yourself, you subscribe to ones the SDK gives you (e.g.
`signals.onConnected.add(...)`).

## The four variants

The variant matters when **late subscribers** matter — i.e. when something
might be emitted before your handler attaches.

### `Signal` (generic, fire-and-forget)

The default. If you `.add()` after an emit, you missed it. Use for
events that only matter in the moment ("button clicked", "error
occurred").

```ts
const onError = createSignal<{ error: Error }>({ name: "onError" });
onError.emit({ error: new Error("boom") });
onError.add(h => /* h never sees the boom */);
```

### `BehaviorSignal` (holds last value)

Like RxJS's `BehaviorSubject`. Holds the most recent emitted value. New
subscribers receive it immediately on `.add()`. Use for state that has
a "current value" by definition (current connection state, current
participant list).

```ts
const connectionState = createBehaviorSignal({ state: "idle" });
connectionState.emit({ state: "connecting" });
connectionState.add(s => /* immediately fires with state: "connecting" */);
```

### `ReplaySignal` (holds last N values)

Buffer of the last N emissions; new subscribers receive the buffer in
order. Use sparingly — usually means you're trying to reconstruct a
log. Often a sign you should be using events differently.

### `BatchedSignal` (microtask coalescing)

Emissions within the same microtask are coalesced into a single
delivery. Use when a producer might emit dozens of times in a tight
loop and you only want to render once.

## When you'd reach for which

| Situation | Variant |
|---|---|
| One-off events: errors, button clicks, "remote presentation started" | `Signal` |
| Current state: am I connected? what's my role? what's the participant list? | `BehaviorSignal` |
| Want a small history (last 5 chat messages, debug log) | `ReplaySignal` |
| Producer fires in a tight loop, consumer renders | `BatchedSignal` |

## Detach lifecycle

`.add()` always returns a detach function. **You must call it** when
your subscriber's lifetime ends. Otherwise:

- The handler keeps firing forever.
- Closures it captures (DOM nodes, React state setters) leak.

In React, this means `useEffect` cleanup:

```tsx
useEffect(() => {
  const detach = signals.onParticipants.add(({ participants }) => {
    setParticipants(participants);
  });
  return detach;        // <-- crucial
}, [signals]);
```

The shape `return detach` works because `useEffect`'s cleanup signature
is `() => void` and the detach function matches.

## React integration patterns

### Subscribing once on mount

The pattern above. `useEffect` with a stable dependency. Detach in
cleanup.

### Mirroring a `BehaviorSignal` into React state

`BehaviorSignal`s are great because the immediate fire-on-`.add()`
behaviour means you don't need a separate "initial state" path:

```tsx
const [state, setState] = useState(connectionState.value);
useEffect(() => {
  return connectionState.add(setState);   // fires immediately with current
}, [connectionState]);
```

### Several signals, one effect

Detach can return an array — wrap in a single cleanup that fires all of
them:

```tsx
useEffect(() => {
  const detaches = [
    signals.onConnected.add(() => /* ... */),
    signals.onDisconnected.add(() => /* ... */),
    signals.onError.add(({ error }) => /* ... */),
  ];
  return () => detaches.forEach(d => d());
}, [signals]);
```

Don't try to wire each in its own `useEffect` — the SDK fires them in
emission order, and splitting effects can change subscription order in
ways that matter for some signals (early subscribers see early emits).

## What about `await`?

You can `await` a signal by wrapping it once:

```ts
function once<T>(signal: { add: (h: (v: T) => void) => () => void }) {
  return new Promise<T>(resolve => {
    const detach = signal.add(v => { detach(); resolve(v); });
  });
}

const { participants } = await once(signals.onParticipants);
```

But this is rare in real code — the whole point of signals is that they
fire many times.

## Common mistakes

1. **Reaching for `.subscribe()`.** Doesn't exist. Use `.add()`.
2. **Forgetting to detach.** Memory leak; in React, also a "can't update
   state on unmounted component" warning.
3. **Subscribing inside the render body** of a React component instead
   of `useEffect`. Subscribes on every render → leak storm.
4. **Subscribing after `infinityClient.call()`.** If the network is fast
   the first signal can fire before you subscribe. Always wire signals
   before calling `.call()`.
5. **Treating `BehaviorSignal` as fire-and-forget.** It's stateful — if
   you re-emit the same value, subscribers fire again (no de-duping by
   default).
