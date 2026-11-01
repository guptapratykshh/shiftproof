import type { Note } from "../types";
import { useRef, useState } from "react";
export function useCaptureState() {
  const [arming, setArming] = useState(false);
  const captureReporter = useRef("");
  const captureContext = useRef<{
    itemId: string;
    shiftId: string;
  } | null>(null);
  const [taskContext, setTaskContext] = useState<{
    id: string;
    title: string;
  } | null>(null);
  const [transcript, setTranscript] = useState("");
  const [blob, setBlob] = useState<Blob | null>(null);
  const [blobUrl, setBlobUrl] = useState("");
  const [recording, setRecording] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const [saved, setSaved] = useState<Note | null>(null);
  const [stage, setStage] = useState("");
  const [reply, setReply] = useState<{
    id: string;
    text: string;
    version: number;
  } | null>(null);
  const [corrections, setCorrections] = useState<string[]>([]);
  const capture = useRef<{
    id: string;
    at: string;
  }>({
    id: crypto.randomUUID(),
    at: new Date().toISOString(),
  });
  const stop = useRef<null | (() => Promise<Blob>)>(null);
  return {
    arming,
    setArming,
    captureReporter,
    captureContext,
    taskContext,
    setTaskContext,
    transcript,
    setTranscript,
    blob,
    setBlob,
    blobUrl,
    setBlobUrl,
    recording,
    setRecording,
    seconds,
    setSeconds,
    saved,
    setSaved,
    stage,
    setStage,
    reply,
    setReply,
    corrections,
    setCorrections,
    capture,
    stop,
  };
}
