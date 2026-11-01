import { Select } from "./Select";
import { useEffect, useRef, useState } from "react";
import { bilingual as t, tr, useLanguage } from "../i18n";
import { MICROPHONE_EVENT, currentMicrophoneState, resumeMicrophone, inspectRecording, selectMicrophone, selectedMicrophone, startRecorder, type MicrophoneState, type RecordingQuality } from "../recorder";

/** Same microphone check and signal feedback in every capture surface. No provider calls. */
export default function MicrophonePanel({ disabled = false, audio, simple = false }: { disabled?: boolean; audio?: Blob | null; simple?: boolean }) {
  useLanguage();
  const [state, setState] = useState<MicrophoneState>(currentMicrophoneState);
  const [devices, setDevices] = useState<MediaDeviceInfo[]>([]), [device, setDevice] = useState(selectedMicrophone());
  const [testing, setTesting] = useState(false), [testUrl, setTestUrl] = useState(""), [error, setError] = useState("");
  const [quality, setQuality] = useState<RecordingQuality | null>(null);
  const stop = useRef<null | (() => Promise<Blob>)>(null), timer = useRef<number | undefined>(undefined), alive = useRef(true);
  async function devicesNow() {
    try { setDevices((await navigator.mediaDevices.enumerateDevices()).filter(d => d.kind === "audioinput" && d.label)); } catch { /* Permission may not be granted yet. */ }
  }
  useEffect(() => {
    alive.current = true;
    const update = (e: Event) => { setState((e as CustomEvent<MicrophoneState>).detail); };
    window.addEventListener(MICROPHONE_EVENT, update); void devicesNow();
    navigator.mediaDevices?.addEventListener("devicechange", devicesNow);
    return () => { alive.current = false; clearTimeout(timer.current); void stop.current?.().catch(() => {}); window.removeEventListener(MICROPHONE_EVENT, update); navigator.mediaDevices?.removeEventListener("devicechange", devicesNow); };
  }, []);
  useEffect(() => { if (state.label) void devicesNow(); }, [state.label]);
  useEffect(() => { let current = true; setQuality(null); if (audio) void inspectRecording(audio).then(q => { if (current) setQuality(q); }).catch(() => {}); return () => { current = false; }; }, [audio]);
  useEffect(() => () => { if (testUrl) URL.revokeObjectURL(testUrl); }, [testUrl]);
  async function finish() {
    const finishCapture = stop.current; stop.current = null; if (!finishCapture) return;
    try { const blob = await finishCapture(); if (alive.current) setTestUrl(URL.createObjectURL(blob)); }
    catch (e) { if (alive.current) setError((e as Error).message); }
    finally { if (alive.current) setTesting(false); }
  }
  async function test() {
    setError(""); setTesting(true);
    document.querySelectorAll("audio").forEach(a => a.pause()); window.dispatchEvent(new Event("shiftproof:stop-playback"));
    try { stop.current = await startRecorder(() => {}, () => { void finish(); }); if (!alive.current) { await stop.current(); stop.current = null; return; } timer.current = window.setTimeout(() => { void finish(); }, 3000); }
    catch (e) { if (alive.current) { setError((e as Error).message); setTesting(false); } }
  }
  const capturing = ["recording", "interrupted", "paused", "no_signal"].includes(state.state);
  const level = capturing && state.level > 0 ? Math.min(1, Math.max(0, (20 * Math.log10(state.level) + 65) / 65)) : 0;
  const status = state.state === "opening" ? t("माइक की अनुमति का इंतज़ार है", "Waiting for microphone permission")
    : state.state === "paused" ? t("ब्राउज़र ने आवाज़ रोक रखी है", "Browser audio is paused")
    : state.state === "interrupted" ? t("माइक से आवाज़ आना रुक गया", "Microphone interrupted")
    : state.state === "no_signal" ? t("माइक चालू है, लेकिन आवाज़ नहीं मिल रही", "Microphone is on, but no sound is reaching the app")
    : capturing ? t("माइक चालू है · अब बोलें", "Microphone is on · speak now")
    : state.state === "error" ? t("माइक की जाँच पूरी नहीं हुई", "Microphone check failed")
    : t("रिकॉर्डिंग शुरू होने पर यहाँ आवाज़ दिखेगी", "Your voice level will appear here while recording");
  return <section className="microphone-panel" aria-label={t("माइक की जाँच", "Microphone check")}>
    <div className="microphone-level"><strong>{testing ? t("तीन सेकंड कुछ बोलें", "Speak for three seconds") : t("माइक की आवाज़", "Microphone level")}</strong><span className={"microphone-status-dot " + (capturing ? "is-on" : "")} aria-hidden="true" /></div>
    <div className="microphone-meter" role="meter" aria-label={t("माइक की आवाज़", "Microphone level")} aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(level * 100)}>
      {Array.from({ length: 20 }, (_, index) => <span key={index} className={level > index / 20 ? "is-lit" : ""} />)}
    </div>
    <p className="microphone-status" aria-live="polite" aria-atomic="true">{status}</p>
    {state.state === "paused" && <button type="button" className="button-outline" onClick={resumeMicrophone}>{t("माइक की आवाज़ चालू करें", "Enable microphone audio")}</button>}
    {state.state === "no_signal" && <p>{t("बोलने पर भी पट्टी नहीं हिलती तो रिकॉर्डिंग रोकें और नीचे दूसरा माइक चुनें। ब्राउज़र और डिवाइस की माइक अनुमति भी जाँचें।", "If the bars stay flat while speaking, stop and choose another microphone below. Check browser and device microphone permissions too.")}</p>}
    <details open={!simple || state.state === "no_signal" || state.state === "error"}><summary>{t("माइक में दिक्कत है?", "Microphone help")}</summary>
    {state.label && <small>{state.label}</small>}
    <div className="microphone-options">
      <button type="button" className="text-button" disabled={disabled || testing || capturing || state.state === "opening"} onClick={() => void test()}>{t("माइक जाँचें", "Test microphone")}</button>
      {devices.length > 0 && <label>{t("माइक", "Microphone")}<Select value={device} disabled={disabled || testing || capturing || state.state === "opening"} onChange={e => { setDevice(e.target.value); selectMicrophone(e.target.value); setState({ level: 0, label: "", state: "idle" }); }}><option value="">{t("डिवाइस का चुना हुआ माइक", "Default microphone")}</option>{devices.map(d => <option key={d.deviceId} value={d.deviceId}>{d.label}</option>)}</Select></label>}
    </div>
    {state.path && <details className="microphone-diagnostics"><summary>{t("माइक की तकनीकी जानकारी", "Microphone details")}</summary>
      <dl><dt>{t("रिकॉर्डिंग का तरीका", "Capture path")}</dt><dd>{state.path}</dd>
      <dt>{t("ब्राउज़र ऑडियो", "Browser audio")}</dt><dd>{state.contextState}</dd>
      <dt>{t("माइक कनेक्शन", "Microphone connection")}</dt><dd>{state.trackState} · {state.muted ? t("रुका हुआ", "muted") : t("चालू", "unmuted")}</dd>
      <dt>{t("ऑडियो नमूने", "Audio samples")}</dt><dd>{state.frames ?? 0}</dd>
      <dt>{t("रिकॉर्ड हुए बाइट", "Recorded bytes")}</dt><dd>{state.nativeBytes ?? 0}</dd></dl>
    </details>}
    </details>
    {quality?.silent && <p role="alert">{t("इस रिकॉर्डिंग में आवाज़ नहीं है। माइक जाँचें और दोबारा रिकॉर्ड करें।", "This recording contains no sound. Test the microphone and record again.")}</p>}
    {(quality?.quiet || state.state === "quiet") && <p>{t("आवाज़ धीमी है। भेजने से पहले सुनें या माइक के पास बोलकर दोबारा रिकॉर्ड करें।", "The recording is quiet. Listen before sending or record again closer to the microphone.")}</p>}
    {state.state === "interrupted" && <p role="alert">{t("रिकॉर्डिंग के दौरान माइक रुका था। भेजने से पहले पूरी रिकॉर्डिंग जाँचें।", "The microphone was interrupted. Check the entire recording before sending.")}</p>}
    {(error || state.message) && <p role="alert">{tr(error || state.message || "")}</p>}
    {testUrl && <div><p>{t("यह केवल माइक की जाँच है। इसे भेजा नहीं जाएगा।", "This is a microphone test only. It will not be submitted.")}</p><audio controls src={testUrl} onPlay={e => document.querySelectorAll("audio").forEach(a => { if (a !== e.currentTarget) a.pause(); })} onError={() => setError("Playback failed. Please test the microphone again.")} /></div>}
  </section>;
}
