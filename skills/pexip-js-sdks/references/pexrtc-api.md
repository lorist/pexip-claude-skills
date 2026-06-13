# PexRTC JavaScript Client API — full reference

Sourced from `https://docs.pexip.com/beta/api_client/api_pexrtc.htm`.
Every property, method, and callback verbatim, organised so you can
find what you need.

## Loading

```html
<script src="https://<conferencing-node>/static/webrtc/js/pexrtc.js"></script>
```

Self-hosted only — no CDN. The script is *the* protocol implementation
for that Conferencing Node's version of Pexip Infinity. Loading it from
two different CNs in the same page is undefined behaviour. Loading it
twice from the same CN re-defines `window.PexRTC` and probably breaks
in-flight calls.

## Construction

```js
const rtc = new PexRTC();
```

Single class, no variants. Set configuration properties on the instance
before calling `makeCall()`.

---

## 1. Configuration properties

Set on the instance **before** `makeCall()` (some are also changeable
in-call — flagged below).

| Property | Type | Default | In-call? | Notes |
|---|---|---|---|---|
| `audio_source` | string / uuid / null / false | `null` | yes | Device id from `enumerateDevices()`. Mutually exclusive with `user_media_stream`. |
| `video_source` | string / uuid / null / false | `null` | yes | Same shape and exclusion. |
| `autoGainControl` | boolean | `true` |  | Audio constraint. Ignored if `user_media_stream` is set. |
| `recv_audio` | boolean | `true` | yes | Receive audio? |
| `recv_video` | boolean | `true` | yes | Receive video? |
| `bandwidth_in` | number (kbps) | `1280` | yes | Overridden by `makeCall()`'s bandwidth arg. |
| `bandwidth_out` | number (kbps) | `1280` | yes | Same. |
| `call_tag` | string | none |  | Optional opaque tag on this participant. |
| `default_stun` | string | none |  | Extra STUN server. |
| `echoCancellation` | boolean | `true` |  | Audio constraint. |
| `fecc_supported` | boolean | `false` | yes | Advertise FECC support. |
| `h264_enabled` | boolean | `true` |  | H.264 codec offer. |
| `live_captions_available` | boolean | — |  | Read-only; reflects VMR capability. |
| `noiseSuppression` | boolean | `true` |  | Audio constraint. |
| `presentation_in_main` | boolean | `false` |  | Receive presentation as main video (single-stream). |
| `screenshare_fps` | number | `5` |  | Outgoing presentation frame rate. |
| `turn_server` | object \| object[] | none |  | TURN config(s). |
| `user_media_stream` | MediaStream | none | yes | Bring your own stream; bypasses `getUserMedia`. |
| `user_presentation_stream` | MediaStream | none | yes | BYO presentation stream. |
| `vp8_enabled` | boolean | `true` |  | VP8 codec offer. |
| `vp9_enabled` | boolean | `true` |  | VP9 codec offer. |
| `client_id` | string | none |  | Vendor identifier string. |

---

## 2. Methods, by purpose

### Connect / setup

#### `makeCall(node, conference, name, bandwidth, call_type)`

Begin the join. Captures media if `user_media_stream` isn't set, then
fires `onSetup` with the local stream.

- `node` — Conferencing Node FQDN
- `conference` — alias
- `name` — display name
- `bandwidth` — kbps, or `null`
- `call_type` — `"presentation"`, `"screen"`, `"audioonly"`, `"recvonly"`, `"rtmp"`, `"stream"`, `"none"`, or omit for video.

#### `connect(pin, extension, idp)`

Continue after `onSetup`. Apply PIN, choose Virtual Reception extension,
or pick an IDP.

- `pin` — string or `null`
- `extension` — string (Virtual Reception target)
- `idp` — IDP UUID (SSO)

May fire `onSetup` again (e.g. wrong PIN) or `onConnect` on success.

### In-call audio/video control

| Method | Purpose |
|---|---|
| `muteAudio(setting)` | Local audio mute. `setting`: boolean. Returns the new state. |
| `muteVideo(setting)` | Local video mute. `setting`: boolean. Returns the new state. |
| `requestAspectRatio(aspect_ratio)` | Tell the server your render aspect (0–2; 0.5625 = 9:16). |
| `addCall(call_type)` | Escalate from roster-only to add A/V or presentation. Fires `onConnect`. |
| `renegotiate(resend_sdp)` | Apply device change (`false`) or full bandwidth/streams refresh (`true`). |

### Presentation / screenshare

| Method | Purpose |
|---|---|
| `getPresentation()` | Subscribe to the full-rate presentation stream. Fires `onPresentationConnected` / `onPresentationDisconnected`. |
| `present(call_type)` | Start (`"screen"`) or stop (`null`) sharing your screen. |
| `getMediaStatistics()` | Chrome only. Returns `{ outgoing: { audio, video }, incoming: { audio, video } }`. |
| `getSecureCheckCode()` | Direct-media security check string. |

### Chat / messaging

| Method | Purpose |
|---|---|
| `sendChatMessage(message, uuid)` | Chat. Omit `uuid` for broadcast. |
| `sendApplicationMessage(obj, uuid)` | App-level JSON to a participant or broadcast. |
| `setMessageText(text)` | Banner across stage. Use `\n` for multi-line. Empty clears. |

### DTMF / FECC

| Method | Purpose |
|---|---|
| `sendDTMF(digits, uuid)` | DTMF to gateway (no `uuid`) or participant. |
| `sendFECC(action, axis, direction, target, timeout)` | Far-end camera control. `action` ∈ `start`/`stop`/`continue`; `axis` ∈ `pan`/`tilt`/`zoom`. Recommended `timeout`: 1000 ms for `start`, 200 ms for `continue`. |

### Hand raise

| Method | Purpose |
|---|---|
| `setBuzz()` | Raise your hand. |
| `clearBuzz(uuid)` | Lower your own (no arg) or — if Host — a specific participant's. |
| `clearAllBuzz()` | Host: lower everyone's hands. |

### Breakouts

| Method | Purpose |
|---|---|
| `moveToBreakout(breakout_uuid)` | Host: move yourself. |
| `setBreakoutHelp(setting)` | Request / cancel help in a breakout. |
| `createBreakout(name, duration, end_action, participants, guests_allowed_to_leave, cb)` | Host. `participants` is `{ "main": [...uuids], "<other-room>": [...] }`. `end_action`: `"disconnect"`/`"transfer"`. |
| `moveParticipantsFromBreakout(from_breakout, to_breakout, participants)` | Host: move a list of UUIDs between rooms. |
| `closeBreakout(breakout_uuid)` | Host: terminate a room (apply `end_action`). |

### Per-participant control (Host)

| Method | Purpose |
|---|---|
| `setParticipantMute(uuid, setting)` | Admin mute audio. |
| `videoMuted(uuid)` / `videoUnmuted(uuid)` | Admin mute/unmute video. |
| `setParticipantRxPresentation(uuid, setting)` | Allow/deny receiving presentation. |
| `setParticipantSpotlight(uuid, setting)` | Spotlight on/off. |
| `clearSpotlights()` | Clear all spotlights. |
| `setParticipantText(uuid, text)` | Overlay text. |
| `setPresentationInMix(state, uuid)` | Adaptive Composition: include presentation in the mix. |
| `setRole(uuid, setting)` | `setting`: `"chair"` (host) / `"guest"`. |
| `setParticipantLayoutGroup(uuid, layout_group)` | v41+. Assign to a layout group (pairs with `setPinningConfig` — see Pinning configuration below). |
| `setSendToAudioMixes(mixes, uuid)` | Configure send mixes. `mixes`: `{ mixes: [{ mix_name, prominent }, ...], uuid }`. |
| `setReceiveFromAudioMix(mix, uuid)` | Configure receive mix. |
| `unlockParticipant(uuid)` | Admit from waiting room. |
| `disconnectParticipant(uuid)` | Drop a participant. |
| `transferParticipant(uuid, destination, role, pin)` | Send to another conference. |
| `showLiveCaptions(uuid)` / `hideLiveCaptions(uuid)` | v37+. Toggle captions for a participant. |

### Conference-wide control (Host)

| Method | Purpose |
|---|---|
| `dialOut(destination, protocol, role, cb, params)` | Dial out. `protocol`: `"sip"`/`"h323"`/`"rtmp"`/`"mssip"`/`"auto"`. `cb` receives `{ result: [uuid_array] }`. `params` covers `presentation_uri`, `streaming`, `dtmf_sequence`, `call_type`, `keep_conference_alive`, `remote_display_name`, `overlay_text`. |
| `setConferenceLock(setting)` | Lock the conference. |
| `setMuteAllGuests(setting)` | Mute every guest. |
| `setGuestsCanUnmute(setting)` | Allow guests to self-unmute. |
| `setGuestsCanPresent(setting)` | v38+. Allow guests to present. |
| `setGuestsCanSeeGuests(setting)` | v38+. `"no_hosts"`/`"always"`/`"never"`. |
| `transformLayout(transforms)` | Layout, indicators, streaming controls — see Transform Layout below. |
| `getAvailableLayouts(cb)` | Fetch supported layouts. |
| `startConference()` | Release guests from the waiting room. |
| `disconnectAll()` | Drop everyone (including yourself). |
| `setClock(clock_values)` | v39+. In-conference timer (`elapsed`/`remaining`/`time`). |
| `getClock()` | v39+. Current timer config. |
| `setClassificationLevel(level)` | Theme classification level. |
| `getClassificationLevel(cb)` | Available levels + current. |

### Pinning configuration (Host)

Participant pinning reserves layout slots for named **layout groups**. Two
generations exist:

- **Static configs (v38+)** — predefined pinning configs authored in the
  conference theme. The client just names one to apply it.
- **Dynamic configs (v41+)** — the client supplies the whole config object
  inline at call time, no theme edit required. This is the "dynamic
  participant pinning" feature.

| Method | Version | Purpose |
|---|---|---|
| `setPinningConfig(config_name, dynamic_pinning_config)` | static v38 / dynamic v41 | Apply a config. Pass **either** `config_name` (a theme config) **or** `dynamic_pinning_config` (an inline object — see below). Pass `config_name` as `""` to clear. |
| `getPinningConfig(cb)` | v38 | The currently-applied config. |
| `getAvailablePinningConfigs(cb)` | v38 | Theme-defined configs available to name. |
| `setParticipantLayoutGroup(uuid, layout_group)` | v41 | Assign a participant to one of the config's layout groups (see participant-control table above). This is what actually fills the reserved slots. |

A pinning config is inert until participants are assigned to its layout
groups — `setPinningConfig` defines the slots, `setParticipantLayoutGroup`
puts people in them.

**`dynamic_pinning_config` object shape** (v41):

```js
{
  name: "exec_review",        // ≤50 chars, alphanumeric + underscore
  slots: [
    {
      layout_groups: ["chair", "presenter"],  // ordered; first match wins.
                                               // a "!<uuid>" entry pins one participant
      show_reserved: true,                     // show a placeholder while the slot is empty (default true)
      reserved_appearance: { /* … */ },        // optional slot styling
    },
    // … one entry per reserved slot
  ],
  backfill: false,            // fill un-pinned slots with other participants (default false)
  remove_self: false,         // drop self-view from the pinned layout (default false)
}
```

Constraint: a **dynamic** config's `reserved_appearance` **cannot reference
files** (theme assets) — inline configs are file-free. Static theme configs
can.

Worked example — pin chairs and presenters into reserved slots:

```js
// 1. Define the layout (host only).
rtc.setPinningConfig(null, {
  name: "exec_review",
  slots: [
    { layout_groups: ["chair"] },
    { layout_groups: ["presenter"] },
  ],
  backfill: true,
});

// 2. Assign participants to groups as they join / change role.
rtc.setParticipantLayoutGroup(chairUuid, "chair");
rtc.setParticipantLayoutGroup(presenterUuid, "presenter");

// 3. Observe: each participant's current group arrives as `layout_group`
//    on the participant object; the active config name arrives as
//    `pinning_config` in onConferenceUpdate.
```

Under the hood these map to the Client REST API
(`POST …/conferences/<alias>/set_pinning_config` with
`{pinning_config}` or `{dynamic_pinning_config}`, and
`POST …/participants/<uuid>/layout_group` with `{layout_group}`) — see the
`pexip-client-api` skill if you're driving it without PexRTC. The modern
`@pexip/infinity` packages do **not** wrap this yet (see
`references/modern-package-map.md`).

### Personal video mixes (v38+)

| Method | Purpose |
|---|---|
| `createVideoMix(mix_name)` | Create a personal layout. `mix_name` patterns: `"main.!<uuid>"`, `"main.!personal"`, `"main"`. |
| `configureVideoMix(mix_name, config)` | Configure: `{ transform_layout: { layout, ... } }`. |
| `deleteVideoMix(mix_name)` | Remove. |

### Tokens

| Method | Purpose |
|---|---|
| `getAttestationToken(cb)` | JWT asserting your role. |

### Disconnect

| Method | Purpose |
|---|---|
| `disconnect()` | Full disconnect (signalling + media). Blocking. |
| `disconnectcall()` | Drop A/V only; keep the control connection alive (e.g. for roster). Blocking. |

---

## 3. Callback hooks

All callbacks are properties on the instance:
`rtc.onConnect = (stream) => { ... }`. Single assignment — set it once,
the previous handler is replaced. There is no `addEventListener`.

| Callback | Parameters | Fires when |
|---|---|---|
| `onSetup(stream, pin_status, conference_extension, idp_selection)` | Local stream + PIN/extension/IDP context | Initial setup complete; ready for `connect()`. May fire multiple times. |
| `onAuth(redirect_url, idp_uuid, idp_name)` | SAML AuthN URL + IDP info | IDP selected for SSO. Redirect the browser. |
| `onConnect(stream)` | Remote stream | Call connected after `connect()`. May fire multiple times if media added incrementally. |
| `onError(err)` | Error string | Fatal — call is closed. |
| `onDisconnect(reason)` | Reason string | Server-initiated disconnect (admin, etc.). |
| `onConferenceUpdate(properties)` | Object — see below | Conference properties changed. |
| `onLayoutUpdate(view, participants, requested_layout, overlay_text_enabled, guests_can_see_guests)` | Layout state | Stage layout changed. |
| `onPresentation(setting, presenter, uuid, presenter_source)` | Presentation state | Presentation started/stopped. May re-fire for presenter change. `presenter_source` ∈ `"video"`/`"static"` (direct media). |
| `onPresentationReload(url)` | JPEG URL | A new presentation frame is available. |
| `onRosterList(roster)` *(deprecated)* | Full participant array | Participant list updated. Replaced by create/update/delete. |
| `onParticipantCreate(participant)` | Participant object | New participant joined. |
| `onParticipantUpdate(participant)` | Participant object | Participant changed. |
| `onParticipantDelete(participant)` | `{ uuid }` | Participant left or was removed. |
| `onChatMessage(message)` | `{ origin, uuid, payload }` | Broadcast chat. |
| `onDirectMessage(message)` | `{ origin, uuid, payload }` | Private chat. |
| `onApplicationMessage(message)` | `{ origin, uuid, direct, payload }` (`payload` is JSON string) | App-level message. |
| `onStageUpdate(stage)` | `[{ participant_uuid, stage_index, vad }]` | Active speaker order + voice activity. |
| `onPresentationConnected(stream)` | Stream | Full-rate presentation stream ready. |
| `onPresentationDisconnected(reason)` | Reason | Presentation stream stopped. |
| `onScreenshareConnected(stream)` | Stream | Outgoing screenshare ready. |
| `onScreenshareStopped(reason)` | Reason | Screenshare stopped. |
| `onCallTransfer(alias)` | New alias | Call transferred. |
| `onFECC(signal)` | `{ action, movement: [{axis, direction}], timeout }` | FECC received. |
| `onSplashScreen(properties)` | `{ screen_key, text, background }` | Direct-media splash. Empty event clears. |
| `onBreakoutHelp(breakout_uuid, setting)` | Room + state | Help requested/cancelled. |
| `onBreakoutUpdate(breakout_uuid, event_name, data)` | Passthrough | Breakout conference property change. |
| `onBreakoutParticipant(breakout_uuid, event_name, data)` | Passthrough; `event_name` ∈ `create`/`update`/`delete` | Breakout participant event. |
| `onLiveCaptions(message)` | `{ data, is_final, src_lang, tgt_lang, sources }` | v37+. v38+ adds `sources` array. |

### `onConferenceUpdate(properties)` — the properties object

Keys (any subset, depending on what changed):

`locked`, `guests_muted`, `all_muted`, `chat_enabled`,
`presentation_allowed`, `guests_can_present`, `guests_can_unmute`,
`started`, `live_captions_available`, `direct_media`, `recording`,
`transcribing`, `streaming`, `public_streaming`, `ai_enabled`,
`external_media_processing`, `classification` (object with `levels`,
`current`), `message_text`, `pinning_config`, `breakout_rooms`,
`breakout_name`, `breakout_description`, `end_action`, `end_time`,
`breakout_guests_allowed_to_leave`. v41+ also: `custom_properties`,
`host_custom_properties`.

### Participant object fields

Used by `onRosterList`, `onParticipantCreate`, `onParticipantUpdate`:

`buzz_time`, `call_direction`, `call_tag`, `can_receive_personal_mix`,
`custom_properties` (v41+), `disconnect_supported`, `display_name`,
`encryption`, `external_node_uuid`, `fecc_supported`, `has_media`,
`is_audio_only_call`, `is_conjoined`, `is_external`,
`is_idp_authenticated`, `is_main_video_dropped_out`, `is_muted`,
`is_client_muted`, `is_on_hold`, `is_presenting`,
`is_streaming_conference`, `is_transferring`, `is_tx_muted`,
`is_video_call`, `is_video_muted`, `is_video_silent`,
`last_spoken_time`, `layout_group`, `local_alias`, `mute_supported`,
`needs_presentation_in_mix`, `overlay_text`, `presentation_supported`,
`private_custom_properties` (v41+), `protocol` (empty for guests),
`receive_from_audio_mix`, `role`, `rx_presentation_policy`,
`send_to_audio_mixes`, `service_type`, `show_live_captions`,
`spotlight`, `start_time`, `supports_direct_chat`,
`transfer_supported`, `uuid`, `uri` (empty for guests), `vendor`
(empty for guests).

---

## 4. `transformLayout` reference

`rtc.transformLayout(transforms)` — every recognised key:

| Key | Type | Notes |
|---|---|---|
| `layout` / `host_layout` / `guest_layout` | string | One of: `"1:0"`, `"1:7"`, `"1:21"`, `"2:21"`, `"1:33"`, `"2x2"`, `"3x3"`, `"4x4"`, `"5x5"`, `"1:1"`, `"one_main_nine_around"`, `"one_main_twelve_around"`, `"two_mains_eight_around"`, `"ac"`, `"teams"`, `"teams_focus"`. |
| `enable_extended_ac` | boolean | Adaptive Composition; extends to 23 participants. Preview. |
| `ai_enabled_indicator` | boolean | v38+. |
| `enable_active_speaker_indication` | boolean | |
| `enable_overlay_text` | boolean | |
| `external_media_processing_indicator` | boolean | v39+. |
| `live_captions_indicator` | boolean | v38+. |
| `recording_indicator` | boolean | |
| `streaming_indicator` | boolean | |
| `transcribing_indicator` | boolean | |
| `streaming` | object | Per-stream layout: `{ layout, waiting_screen_enabled, indicators_enabled, presentation_in_mix (v39+) }`. |
| `free_form_overlay_text` | string[] | Custom overlay per layout position. |

Old layout names `"4:0"`, `"9:0"`, `"16:0"`, `"25:0"` are now
`"2x2"`/`"3x3"`/`"4x4"`/`"5x5"`. The old names still work.

---

## 5. Version history (selected)

| Pexip version | Added |
|---|---|
| **v37** | Live captions: `showLiveCaptions`, `hideLiveCaptions`, `onLiveCaptions` |
| **v38** | Pinning, personal layouts, enhanced captions: `createVideoMix`, `getPinningConfig`, `getAvailablePinningConfigs`, `setGuestsCanPresent`, `setGuestsCanSeeGuests`, `onLiveCaptions.sources[]` |
| **v39** | Timer, extended AC, media-processing indicator: `setClock`, `getClock`, `enable_extended_ac`, `external_media_processing_indicator`, `recording`/`transcribing`/`streaming`/`ai_enabled` in `onConferenceUpdate` |
| **v40** | `chat_enabled` field in `onConferenceUpdate` |
| **v41** | Custom properties, dynamic pinning: `custom_properties`, `host_custom_properties`, `private_custom_properties` in callbacks; `dynamic_pinning_config` parameter on `setPinningConfig`; `setParticipantLayoutGroup` |

When writing PexRTC code, prefer detecting capabilities (e.g.
`typeof rtc.setClock === "function"`) over hard-checking version
strings — the script you load is paired to the CN that served it.
