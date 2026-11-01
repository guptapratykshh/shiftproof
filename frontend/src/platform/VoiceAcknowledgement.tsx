import MicrophonePanel from "../components/MicrophonePanel";
import { useEffect, useRef, useState } from "react";
import { bilingual, tr } from "../i18n";
import { Mic, Square, Check } from "lucide-react";
import { startRecorder, requireAudibleRecording } from "../recorder";
import { binary, call } from "./client";
import {
  acknowledgementKey,
  loadAcknowledgement,
  saveAcknowledgement,
  deleteAcknowledgement,
} from "./acknowledgementDrafts";
export default function VoiceAcknowledgement({
  userId,
  base,
  shiftId,
  version,
  done,
  beforeRecord,
  onPending,
  blocked = false,
}: {
  blocked?: boolean;
  userId: string;
  base: string;
  shiftId: string;
  version: number;
  language: "hi" | "en";
  done: () => Promise<unknown>;
  beforeRecord: () => void;
  onPending: (pending: boolean) => void;
}) {
  const [recording, setRecording] = useState(false),
    [arming, setArming] = useState(false),
    [seconds, setSeconds] = useState(0),
    [audio, setAudio] = useState<Blob | null>(null),
    [url, setUrl] = useState(""),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [capturedVersion, setCapturedVersion] = useState(version),
    [savedId, setSavedId] = useState(""),
    [hydrated, setHydrated] = useState(false);
  const stop = useRef<null | (() => Promise<Blob>)>(null),
    alive = useRef(true),
    versionRef = useRef(version),
    writes = useRef<Promise<unknown>>(Promise.resolve());
  const key = acknowledgementKey(userId, base, shiftId);
  function persist(blob: Blob, captured: number, uploaded = "") {
    const next = writes.current
      .catch(() => {})
      .then(() =>
        saveAcknowledgement({
          key,
          userId,
          base,
          shiftId,
          version: captured,
          audio: blob,
          savedId: uploaded,
          updatedAt: new Date().toISOString(),
        }),
      );
    writes.current = next;
    return next;
  }
  async function clearSaved() {
    await writes.current.catch(() => {});
    await deleteAcknowledgement(key);
  }
  const t = bilingual;
  useEffect(() => {
    alive.current = true;
    void loadAcknowledgement(key)
      .then((saved) => {
        if (!alive.current) return;
        if (
          saved &&
          saved.userId === userId &&
          saved.base === base &&
          saved.shiftId === shiftId
        ) {
          setAudio(saved.audio);
          setSavedId(saved.savedId);
          setCapturedVersion(saved.version);
          versionRef.current = saved.version;
        }
      })
      .catch((e) => {
        if (alive.current) setError(e.message);
      })
      .finally(() => {
        if (alive.current) setHydrated(true);
      });
    return () => {
      alive.current = false;
      const finish = stop.current;
      stop.current = null;
      if (finish)
        void finish()
          .then((blob) => persist(blob, versionRef.current))
          .catch(() => {});
    };
  }, []);
  useEffect(() => {
    onPending(recording || arming || !!audio);
  }, [recording, arming, audio, onPending]);
  useEffect(() => {
    if (!audio) {
      setUrl("");
      return;
    }
    const u = URL.createObjectURL(audio);
    setUrl(u);
    return () => URL.revokeObjectURL(u);
  }, [audio]);
  async function finish() {
    const f = stop.current;
    if (!f) return;
    stop.current = null;
    try {
      const b = await f();
      if (alive.current) { setAudio(b); setCapturedVersion(versionRef.current); setSavedId(""); }
      await persist(b, versionRef.current);
    } catch (e) {
      if (alive.current) setError((e as Error).message);
    } finally { if (alive.current) setRecording(false); }
  }
  async function record() {
    setError("");
    if (recording) {
      await finish();
      return;
    }
    setArming(true);
    beforeRecord();
    versionRef.current = version;
    try {
      stop.current = await startRecorder(
        setSeconds,
        () => void finish(),
        (blob) => {
          // Retain the previous readback until its replacement finishes safely.
          if (audio) return;
          void requireAudibleRecording(blob).then(() => persist(blob, versionRef.current)).catch((e) => {
            if (e.category === "silent_audio" || e.category === "empty_audio") return;
            if (alive.current) setError(e.message);
          });
        },
      );
      if (alive.current) setRecording(true);
      else await stop.current();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setArming(false);
    }
  }
  return (
    <section className="platform-panel voice-ack">
      <h2>
        {t(
          "हैंडओवर मिला · अपनी समझ बोलें",
          "Receive handover · say what needs checking",
        )}
      </h2>
      <p>
        {t(
          "जरूरी बातें सुनें। क्या बाकी है, बोलकर बताएँ। फिर अपनी पुष्टि दें।",
          "Listen to the outstanding work, record what you understood, then confirm receipt.",
        )}
      </p>
      <p className="offline-note">
        {t(
          "बिना भेजी आवाज़ इस डिवाइस पर सहेजी जाती है। अचानक बंद होने पर आखिरी लगभग एक सेकंड छूट सकता है।",
          "Unsubmitted readbacks are saved on this device. Abrupt closure may lose approximately the final second.",
        )}
      </p>
      {error && (
        <p role="alert" className="platform-error">
          {tr(error)}
        </p>
      )}
      <MicrophonePanel disabled={busy || arming || recording} audio={audio} />
      <button
        className="button-outline"
        disabled={busy || arming || !hydrated}
        onClick={() => void record()}
      >
        {recording ? <Square size={18} /> : <Mic size={18} />}{" "}
        {recording
          ? `${t("रोकें", "Stop")} · ${Math.round(seconds)}${t(" सेकंड", "s")}`
          : t("अपनी समझ बोलें", "Record readback")}
      </button>
      {url && <audio controls src={url} />}
      {audio && capturedVersion !== version && (
        <p role="alert">
          {t(
            "हैंडओवर बदल गया है। नई जानकारी देखें और फिर बोलें।",
            "The handover changed. Check the latest information and record your readback again.",
          )}
        </p>
      )}
      {audio && !recording && (
        <button
          className="text-button"
          disabled={busy}
          onClick={async () => {
            try {
              await clearSaved();
              setAudio(null);
              setSavedId("");
            } catch (e) {
              setError((e as Error).message);
            }
          }}
        >
          {t("यह रिकॉर्डिंग हटाएँ", "Discard this recording")}
        </button>
      )}
      <button
        className="button-orange"
        disabled={
          !audio ||
          blocked ||
          !hydrated ||
          recording ||
          arming ||
          busy ||
          !navigator.onLine ||
          capturedVersion !== version
        }
        onClick={async () => {
          if (!audio) return;
          setBusy(true);
          setError("");
          try {
            let id = savedId;
            if (!id) {
              const response = await binary(
                base + `/shifts/${shiftId}/acknowledgements/audio`,
                audio,
              );
              id = JSON.parse(await response.text()).audio_id;
              setSavedId(id);
              await persist(audio, capturedVersion, id);
            }
            await call(base + `/shifts/${shiftId}/acknowledgements`, {
              expected_version: capturedVersion,
              readback: t(
                "आवाज़ से हैंडओवर की पुष्टि की।",
                "Acknowledged by voice.",
              ),
              audio_id: id,
            });
            await clearSaved();
            setAudio(null);
            setSavedId("");
            await done();
          } catch (e) {
            setError((e as Error).message);
          } finally {
            setBusy(false);
          }
        }}
      >
        <Check size={18} />
        {busy
          ? t("पुष्टि हो रही है…", "Confirming…")
          : t(
              "जानकारी मिली · पुष्टि करें",
              "I received this handover · confirm",
            )}
      </button>
    </section>
  );
}
