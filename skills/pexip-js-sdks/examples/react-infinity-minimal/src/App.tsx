import { useEffect, useRef, useState } from "react";
import {
  ClientCallType,
  createInfinityClient,
  createInfinityClientSignals,
  type InfinityClient,
} from "@pexip/infinity";

type Phase = "idle" | "connecting" | "pin-required" | "in-call" | "error";

export function App() {
  const [phase, setPhase] = useState<Phase>("idle");
  const [error, setError] = useState<string | null>(null);
  const [participants, setParticipants] = useState<Array<{ uuid: string; displayName: string }>>([]);

  const [node, setNode] = useState("conf.example.com");
  const [conferenceAlias, setAlias] = useState("meet.alice");
  const [displayName, setDisplayName] = useState("");
  const [pin, setPin] = useState("");

  const localVideoRef = useRef<HTMLVideoElement>(null);
  const remoteVideoRef = useRef<HTMLVideoElement>(null);

  const clientRef = useRef<InfinityClient | null>(null);
  const localStreamRef = useRef<MediaStream | null>(null);

  // Create the client + wire signals once.
  useEffect(() => {
    const signals = createInfinityClientSignals([]);
    const client = createInfinityClient(signals);
    clientRef.current = client;

    const detaches = [
      signals.onConnected.add(() => {
        setPhase("in-call");
        setError(null);
      }),
      signals.onPinRequired.add(() => {
        setPhase("pin-required");
      }),
      signals.onError.add(({ error }) => {
        setPhase("error");
        setError(error?.message ?? String(error));
      }),
      signals.onDisconnected.add(({ reason }) => {
        setPhase("idle");
        if (reason) setError(reason);
        teardown();
      }),
      // Participant list is delivered as a single signal carrying the full roster.
      // Shape varies slightly by package version; cast loosely.
      signals.onParticipants.add(({ participants }: { participants: Array<{ uuid: string; displayName: string }> }) => {
        setParticipants(participants);
      }),
      // Remote stream becomes available once the call is up.
      signals.onRemoteStream?.add(({ stream }: { stream: MediaStream }) => {
        if (remoteVideoRef.current) remoteVideoRef.current.srcObject = stream;
      }) ?? (() => {}),
    ];

    return () => {
      detaches.forEach((d) => d());
      void client.disconnect({ reason: "Page unmounted" }).catch(() => {});
    };
  }, []);

  const join = async (pinValue?: string) => {
    if (!clientRef.current) return;
    setPhase("connecting");
    setError(null);
    try {
      // Capture once. If you want background blur, route through @pexip/media-processor here.
      if (!localStreamRef.current) {
        localStreamRef.current = await navigator.mediaDevices.getUserMedia({ audio: true, video: true });
        if (localVideoRef.current) localVideoRef.current.srcObject = localStreamRef.current;
      }
      await clientRef.current.call({
        conferenceAlias,
        displayName: displayName || "Anonymous",
        callType: ClientCallType.AudioVideo,
        bandwidth: 1280,
        mediaStream: localStreamRef.current,
        node,
        pin: pinValue,
      } as Parameters<InfinityClient["call"]>[0]);
    } catch (e) {
      setPhase("error");
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const submitPin = () => {
    if (!pin) return;
    void join(pin);
  };

  const hangup = async () => {
    if (clientRef.current) {
      await clientRef.current.disconnect({ reason: "User hung up" }).catch(() => {});
    }
    teardown();
  };

  const teardown = () => {
    localStreamRef.current?.getTracks().forEach((t) => t.stop());
    localStreamRef.current = null;
    if (localVideoRef.current) localVideoRef.current.srcObject = null;
    if (remoteVideoRef.current) remoteVideoRef.current.srcObject = null;
    setParticipants([]);
    setPhase("idle");
  };

  return (
    <div style={{ fontFamily: "system-ui, sans-serif", margin: 16, maxWidth: 720 }}>
      <h1>Pexip Infinity — minimal React client</h1>

      <fieldset disabled={phase === "in-call" || phase === "connecting"}>
        <legend>Join</legend>
        <label style={{ display: "block" }}>Conferencing Node:&nbsp;
          <input value={node} onChange={(e) => setNode(e.target.value)} size={36} />
        </label>
        <label style={{ display: "block" }}>Alias:&nbsp;
          <input value={conferenceAlias} onChange={(e) => setAlias(e.target.value)} size={36} />
        </label>
        <label style={{ display: "block" }}>Display name:&nbsp;
          <input value={displayName} onChange={(e) => setDisplayName(e.target.value)} size={36} />
        </label>
      </fieldset>

      <div style={{ marginTop: 8 }}>
        {phase === "idle" || phase === "error" ? (
          <button onClick={() => void join()}>Join</button>
        ) : null}
        {phase === "in-call" ? <button onClick={() => void hangup()}>Hang up</button> : null}
        {phase === "connecting" ? <span>Connecting…</span> : null}
      </div>

      {phase === "pin-required" && (
        <div style={{ marginTop: 8 }}>
          <input
            type="password"
            placeholder="PIN"
            value={pin}
            onChange={(e) => setPin(e.target.value)}
          />
          <button onClick={submitPin}>Submit PIN</button>
        </div>
      )}

      {error && <p style={{ color: "crimson" }}>Error: {error}</p>}

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginTop: 12 }}>
        <video ref={localVideoRef} autoPlay muted playsInline style={{ width: "100%", background: "#111", borderRadius: 4 }} />
        <video ref={remoteVideoRef} autoPlay playsInline style={{ width: "100%", background: "#111", borderRadius: 4 }} />
      </div>

      <h2 style={{ marginTop: 16 }}>Participants ({participants.length})</h2>
      <ul>
        {participants.map((p) => (
          <li key={p.uuid}>{p.displayName}</li>
        ))}
      </ul>
    </div>
  );
}
