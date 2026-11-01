import { Select } from "../components/Select";
import { AppearanceControl } from "../theme";
import MicrophonePanel from "../components/MicrophonePanel";
import { useEffect, useRef, useState } from "react";
import {
  useLanguage,
  setLanguage,
  adoptAccountLanguage,
  bilingual,
  locale,
  tr,
} from "../i18n";
import { Mic, Square, WifiOff } from "lucide-react";
import { Brand } from "./Landing";
import { downloadRecoveryFile } from "./recoveryFiles";
import { clearAccountAcknowledgements } from "./acknowledgementDrafts";
import { startRecorder } from "../recorder";
import { captureShiftProblem, NO_CURRENT_SHIFT } from "./captureShift";
import { call, type Session } from "./client";
import { clearOfflineContext, type OfflineContext } from "./offlineContext";
import {
  saveDraft,
  listDrafts,
  deleteDraft,
  clearAccountDrafts,
  type CaptureDraft,
} from "./drafts";
export default function OfflineCapture({
  context,
}: {
  context: OfflineContext;
}) {
  const english = useLanguage() === "en";
  const setEnglish = (value: boolean) => setLanguage(value ? "en" : "hi");
  useEffect(() => {
    adoptAccountLanguage(context.userId, "hi");
  }, [context.userId]);
  const [online, setOnline] = useState(navigator.onLine),
    [item, setItem] = useState(context.items[0]?.id || ""),
    [text, setText] = useState(""),
    [recording, setRecording] = useState(false),
    [arming, setArming] = useState(false),
    [seconds, setSeconds] = useState(0),
    [audio, setAudio] = useState<Blob | null>(null),
    [url, setUrl] = useState(""),
    [drafts, setDrafts] = useState<CaptureDraft[]>([]),
    [message, setMessage] = useState(""),
    [error, setError] = useState("");
  const capture = useRef({
      id: crypto.randomUUID() as string,
      at: new Date().toISOString(),
    }),
    stop = useRef<null | (() => Promise<Blob>)>(null),
    alive = useRef(true),
    latestAudio = useRef<Blob | null>(null);
  const t = bilingual;
  const load = () =>
    listDrafts(context.userId, context.organizationId).then((ds) =>
      setDrafts(
        ds.filter(
          (d) => (d.reportedById || "") === (context.reportedById || ""),
        ),
      ),
    );
  useEffect(() => {
    alive.current = true;
    void load();
    const changed = () => setOnline(navigator.onLine);
    window.addEventListener("online", changed);
    window.addEventListener("offline", changed);
    return () => {
      alive.current = false;
      void stop.current?.().catch(() => {});
      window.removeEventListener("online", changed);
      window.removeEventListener("offline", changed);
    };
  }, []);
  useEffect(() => {
    if (!audio) {
      setUrl("");
      return;
    }
    const u = URL.createObjectURL(audio);
    setUrl(u);
    return () => URL.revokeObjectURL(u);
  }, [audio]);
  const draft = (blob: Blob | null): CaptureDraft => ({
    id: capture.current.id,
    userId: context.userId,
    reportedById: context.reportedById,
    organizationId: context.organizationId,
    itemId: item,
    shiftId: context.activeShiftId,
    recordedAt: capture.current.at,
    updatedAt: new Date().toISOString(),
    transcript: text,
    audio: blob,
    corrections: [],
    reply: null,
  });
  async function persist(blob = latestAudio.current) {
    if (!blob && !text) return;
    await saveDraft(draft(blob));
    if (alive.current) {
      setMessage(
        t("ड्राफ़्ट इस डिवाइस पर सुरक्षित है।", "Draft saved on this device."),
      );
      await load();
    }
  }
  useEffect(() => {
    const timer = setTimeout(() => {
      if (!recording) void persist().catch((e) => setError(e.message));
    }, 300);
    return () => clearTimeout(timer);
  }, [text, audio, recording]);
  async function finish() {
    const f = stop.current;
    if (!f) return;
    stop.current = null;
    try {
      const b = await f();
      latestAudio.current = b;
      if (alive.current) setAudio(b);
      await persist(b);
    } catch (e) {
      if (alive.current) setError((e as Error).message);
    } finally {
      if (alive.current) setRecording(false);
    }
  }
  async function record() {
    if (recording) {
      await finish();
      return;
    }
    if (captureShiftProblem(context.shifts.find(s => s.id === context.activeShiftId), new Date().toISOString())) {
      setError(tr(NO_CURRENT_SHIFT));
      return;
    }
    setArming(true);
    setError("");
    capture.current = { id: crypto.randomUUID(), at: new Date().toISOString() };
    try {
      stop.current = await startRecorder(
        setSeconds,
        () => void finish(),
        (blob) => {
          latestAudio.current = blob;
          void persist(blob).catch((e) => setError(e.message));
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
  const hasDraft = !!(audio || text);
  const shiftUnavailable = !!captureShiftProblem(context.shifts.find(s => s.id === context.activeShiftId), new Date().toISOString());
  return (
    <div
      className="worker-account offline-capture"
      lang={english ? "en" : "hi"}
    >
      <header>
        <Brand />
        <AppearanceControl />
        <button className="button-outline" onClick={() => setEnglish(!english)}>
          {english ? "हिन्दी" : "English"}
        </button>
      </header>
      <main className="account-card">
        <span className="eyebrow">
          <WifiOff size={16} /> {t("ऑफ़लाइन रिकॉर्डिंग", "OFFLINE CAPTURE")}
        </span>
        <h1>{t("अपडेट सुरक्षित रखें", "Keep your update safe")}</h1>
        <p>
          {context.reportedByName || context.userName} ·{" "}
          {context.organizationName}
        </p>
        <div className="preview-notice">
          {t(
            "यह पिछली शिफ्ट की सहेजी जानकारी है। अभी पहुँच और असाइनमेंट की पुष्टि नहीं हुई है। रिकॉर्डिंग केवल डिवाइस पर रहेगी।",
            "These are cached assignment details. Access and assignments are unverified while offline. Recording stays on this device.",
          )}
          <br />
          {t("शिफ्ट", "Shift")}:{" "}
          {context.shifts.find((s) => s.id === context.activeShiftId)?.name ||
            context.activeShiftId}
        </div>
        {error && (
          <p role="alert" className="platform-error">
            {tr(error)}
          </p>
        )}
        {message && <p role="status">{tr(message)}</p>}
        <label>
          {t("किस काम का अपडेट?", "Work item")}
          <Select
            value={item}
            disabled={recording || arming || hasDraft}
            onChange={(e) => setItem(e.target.value)}
          >
            {context.items.map((i) => (
              <option value={i.id} key={i.id}>
                {i.id} · {i.name}
              </option>
            ))}
          </Select>
        </label>
        <button
          className={"record-circle " + (recording ? "recording" : "")}
          disabled={!item || arming || (!recording && (hasDraft || shiftUnavailable))}
          onClick={() => void record()}
          aria-label={
            recording
              ? t("रिकॉर्डिंग रोकें", "Stop recording")
              : t("रिकॉर्ड करें", "Start recording")
          }
        >
          {recording ? <Square /> : <Mic />}
        </button>
        {shiftUnavailable && !recording && <p role="status">{tr(NO_CURRENT_SHIFT)}</p>}
        <p className="record-caption">
          {recording
            ? `${Math.round(seconds)} / 45`
            : t("45 सेकंड तक बोलें", "Record up to 45 seconds")}
        </p>
        <MicrophonePanel disabled={recording || arming} audio={audio} />
        {url && <audio controls src={url} />}
        <details>
          <summary>
            {t("बोलने के बजाय लिखें", "Write instead of speaking")}
          </summary>
          <label>
            {t("आपके शब्द", "Your words")}
            <textarea
              value={text}
              disabled={recording || arming || (!hasDraft && shiftUnavailable)}
              onChange={(e) => setText(e.target.value)}
            />
          </label>
        </details>
        {hasDraft && (
          <button
            className="button-outline"
            onClick={() =>
              void persist().then(() => {
                capture.current = {
                  id: crypto.randomUUID(),
                  at: new Date().toISOString(),
                };
                setText("");
                setAudio(null);
                latestAudio.current = null;
              })
            }
          >
            {t("ड्राफ़्ट रखें · नया अपडेट", "Save draft · start another")}
          </button>
        )}
        <p className="offline-note">
          {t(
            "इंटरनेट आने पर खाता फिर जाँचा जाएगा। कोई अपडेट अपने आप नहीं भेजा जाएगा। अचानक बंद होने पर आखिरी लगभग एक सेकंड की आवाज़ छूट सकती है।",
            "Reconnect to verify your account before sending. Nothing is uploaded automatically. Abrupt closure may lose approximately the final second of recording.",
          )}
        </p>
        <button
          className="button-orange"
          disabled={!online || recording || arming}
          onClick={async () => {
            try {
              await persist();
              const session = await call<Session>("/auth/session");
              if (session.user.id !== context.userId) {
                clearOfflineContext();
                location.href = "/organizations";
                return;
              }
              if (
                !session.organizations.some(
                  (o) => o.id === context.organizationId,
                )
              ) {
                clearOfflineContext();
                throw new Error(
                  t(
                    "इस संगठन की पहुँच बदल गई है। सुपरवाइज़र से संपर्क करें।",
                    "Your organization access changed. Ask your supervisor.",
                  ),
                );
              }
              location.href = "/app/" + context.organizationId;
            } catch (e) {
              setError((e as Error).message);
            }
          }}
        >
          {t("कनेक्ट होकर खाता जाँचें", "Reconnect and verify account")}
        </button>
        <a href="/login">{t("दोबारा साइन इन करें", "Sign in again")}</a>
        <details className="draft-drawer">
          <summary>
            {t("सहेजे ड्राफ़्ट", "Saved drafts")} ({drafts.length})
          </summary>
          {drafts.map((d) => (
            <div key={d.id}>
              <span>
                {d.itemId} · {new Date(d.recordedAt).toLocaleString(locale())}
              </span>
              <button
                className="text-button"
                disabled={recording || arming}
                onClick={() =>
                  void downloadRecoveryFile(d).catch((e) => setError(e.message))
                }
              >
                {t("सुपरवाइज़र के लिए फ़ाइल", "Download recovery file")}
              </button>
              <button
                className="text-button"
                disabled={recording || arming}
                onClick={() => {
                  if (confirm(t("ड्राफ़्ट हटाएँ?", "Discard draft?")))
                    void deleteDraft(d.id).then(load);
                }}
              >
                {t("हटाएँ", "Discard")}
              </button>
            </div>
          ))}
        </details>
        <button
          className="text-button"
          disabled={recording || arming}
          onClick={() => {
            if (
              confirm(
                t(
                  "इस डिवाइस से इस खाते के ड्राफ़्ट और सहेजी पहचान हटाएँ?",
                  "Remove this account’s unfinished recordings, drafts and cached identity for every organization from this device?",
                ),
              )
            )
              void Promise.all([
                clearAccountDrafts(context.userId),
                clearAccountAcknowledgements(context.userId),
              ]).then(() => {
                clearOfflineContext();
                location.href = "/login";
              });
          }}
        >
          {t("डिवाइस से खाता हटाएँ", "Clear account from this device")}
        </button>
      </main>
    </div>
  );
}
