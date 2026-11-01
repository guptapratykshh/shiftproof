export type RecordingQuality = { frames: number; duration: number; peak: number; rms: number; silent: boolean; quiet: boolean };
export type MicrophoneState = { level: number; label: string; state: string; message?: string; contextState?: string; trackState?: string; muted?: boolean; frames?: number; nativeBytes?: number; path?: string };
export const MICROPHONE_EVENT = "shiftproof:microphone";
let activeCapture = false;
const DEVICE_KEY = "shiftproof:microphone-device";
export function selectedMicrophone() { try { return localStorage.getItem(DEVICE_KEY) || ""; } catch { return ""; } }
export function selectMicrophone(id: string) { try { localStorage.setItem(DEVICE_KEY, id); } catch { /* Device preference is optional. */ } }
let microphoneState: MicrophoneState = { level: 0, label: "", state: "idle" };
let resumeCapture: (() => void) | undefined;
export function currentMicrophoneState() { return microphoneState; }
export function resumeMicrophone() { resumeCapture?.(); }
function signal(detail: MicrophoneState) { microphoneState = detail; window.dispatchEvent(new CustomEvent(MICROPHONE_EVENT, { detail })); }
async function bounded<T>(promise: Promise<T>, ms: number, fallback: T): Promise<T> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  try { return await Promise.race([promise, new Promise<T>(resolve => { timer = setTimeout(() => resolve(fallback), ms); })]); }
  finally { clearTimeout(timer); }
}
export class RecordingError extends Error { constructor(message: string, public category: string) { super(message); } }

/** Inspect the actual encoded samples, not the elapsed recording timer. */
export async function inspectRecording(audio: Blob): Promise<RecordingQuality> {
  const view = new DataView(await audio.arrayBuffer());
  if (view.byteLength < 44) throw new RecordingError("The recording is incomplete. Please record again.", "invalid_audio");
  const rate = view.getUint32(24, true), frames = Math.floor((view.byteLength - 44) / 2);
  let peak = 0, energy = 0;
  for (let i = 0; i < frames; i++) { const sample = view.getInt16(44 + i * 2, true) / 32768; peak = Math.max(peak, Math.abs(sample)); energy += sample * sample; }
  const rms = Math.sqrt(energy / Math.max(1, frames));
  return { frames, duration: frames / rate, peak, rms, silent: peak === 0, quiet: peak > 0 && rms < 0.003 };
}
export async function requireAudibleRecording(audio: Blob) {
  const quality = await inspectRecording(audio);
  if (quality.duration < 0.2 || !quality.frames) throw new RecordingError("The microphone captured too little audio. Please record again.", "empty_audio");
  if (quality.silent) throw new RecordingError("No sound was captured. Test or change the microphone, then record again.", "silent_audio");
  return quality;
}

/** Convert once from the browser's native rate to portable, bounded mono PCM. */
function wav(chunks: Float32Array[], sampleRate: number): Blob {
  const length = Math.min(chunks.reduce((sum, chunk) => sum + chunk.length, 0), sampleRate * 45);
  const pcm = new Float32Array(length);
  let offset = 0;
  for (const chunk of chunks) { const count = Math.min(chunk.length, length - offset); if (count <= 0) break; pcm.set(chunk.subarray(0, count), offset); offset += count; }
  const rate = 16000, count = Math.floor(length * rate / sampleRate);
  const buffer = new ArrayBuffer(44 + count * 2), view = new DataView(buffer);
  const write = (at: number, text: string) => { for (let i = 0; i < text.length; i++) view.setUint8(at + i, text.charCodeAt(i)); };
  write(0, "RIFF"); view.setUint32(4, 36 + count * 2, true); write(8, "WAVE"); write(12, "fmt ");
  view.setUint32(16, 16, true); view.setUint16(20, 1, true); view.setUint16(22, 1, true);
  view.setUint32(24, rate, true); view.setUint32(28, rate * 2, true); view.setUint16(32, 2, true); view.setUint16(34, 16, true);
  write(36, "data"); view.setUint32(40, count * 2, true);
  for (let i = 0; i < count; i++) {
    // Average each native-rate interval before downsampling to reduce aliasing.
    const from = i * sampleRate / rate, to = Math.min(length, (i + 1) * sampleRate / rate);
    let value = 0;
    for (let p = Math.floor(from); p < Math.ceil(to); p++) value += (pcm[p] || 0) * (Math.min(p + 1, to) - Math.max(p, from));
    value /= Math.max(to - from, 1);
    view.setInt16(44 + i * 2, Math.max(-1, Math.min(1, value)) * 32767, true);
  }
  return new Blob([buffer], { type: "audio/wav" });
}

function decodedWav(decoded: AudioBuffer) {
  let selected = decoded.getChannelData(0), energy = 0;
  for (let channel = 0; channel < decoded.numberOfChannels; channel++) {
    const data = decoded.getChannelData(channel); let sum = 0;
    for (const sample of data) sum += sample * sample;
    if (sum > energy) { selected = data; energy = sum; }
  }
  return wav([selected], decoded.sampleRate);
}

export async function startRecorder(onTick: (seconds: number) => void, onLimit: () => void, onCheckpoint?: (audio: Blob) => void) {
  if (!navigator.mediaDevices?.getUserMedia) throw new RecordingError("Microphone recording needs a secure connection and a supported browser.", "microphone_unavailable");
  if (activeCapture) throw new RecordingError("Stop the current microphone recording first.", "microphone_busy");
  activeCapture = true;
  signal({ level: 0, label: "", state: "opening" });
  let stream: MediaStream | undefined, context: AudioContext | undefined;
  let source: MediaStreamAudioSourceNode | undefined, processor: AudioWorkletNode | undefined, analyser: AnalyserNode | undefined, silent: GainNode | undefined;
  let native: MediaRecorder | undefined, nativeFinished: Promise<Blob | null> | undefined;
  let moduleUrl: string | undefined, timer: number | undefined;
  let stopped = false, accepting = true, interruption = false, total = 0, nativeBytes = 0;
  let nativeLevel = 0, nativeAt = 0, decoding = false, nativeCheckpoint: Blob | undefined;
  let flushed: (() => void) | undefined;
  let leave = () => {}, changed = () => {};
  const chunks: Float32Array[] = [];
  const cleanup = () => {
    accepting = false; activeCapture = false; resumeCapture = undefined; clearInterval(timer);
    window.removeEventListener("pagehide", leave);
    stream?.getTracks().forEach(track => { track.removeEventListener("mute", changed); track.removeEventListener("ended", changed); });
    context?.removeEventListener("statechange", changed);
    if (native?.state === "recording") native.stop();
    if (processor) { processor.port.onmessage = null; processor.disconnect(); }
    source?.disconnect(); analyser?.disconnect(); silent?.disconnect();
    stream?.getTracks().forEach(track => track.stop());
    if (moduleUrl) URL.revokeObjectURL(moduleUrl);
    if (context && context.state !== "closed") void context.close().catch(() => {});
  };
  try {
    // Resume from the initiating gesture, but never make native capture wait on
    // a suspended render context. Some browsers leave resume() pending.
    try { context = new AudioContext(); void context.resume().catch(() => {}); } catch { /* Native recording can still work. */ }
    const deviceId = selectedMicrophone();
    let expired = false;
    const request = navigator.mediaDevices.getUserMedia({ audio: {
      echoCancellation: false, noiseSuppression: false, autoGainControl: false,
      ...(deviceId ? { deviceId: { exact: deviceId } } : {}),
    } }).then(value => { if (expired) { value.getTracks().forEach(track => track.stop()); throw new Error("Expired microphone request"); } return value; });
    const acquired = await bounded<MediaStream | null>(request, 20000, null);
    if (!acquired) { expired = true; throw new RecordingError("Microphone permission is still waiting. Allow microphone access in the browser, then try again.", "microphone_permission"); }
    stream = acquired;
    const track = stream.getAudioTracks()[0];
    if (!track) throw new RecordingError("No microphone was found. Connect a microphone and try again.", "microphone_unavailable");
    const label = track.label || "Microphone", started = performance.now();
    resumeCapture = () => { if (context) void context.resume().catch(() => {}); };
    // Offline decoding does not depend on an output device or autoplay permission.
    const decode = async (blob: Blob) => new OfflineAudioContext(1, 1, 48000).decodeAudioData(await blob.arrayBuffer());
    if (typeof MediaRecorder !== "undefined") {
      try {
        const mimeType = ["audio/webm;codecs=opus", "audio/mp4", "audio/webm"].find(type => MediaRecorder.isTypeSupported(type));
        native = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
        const parts: Blob[] = [];
        nativeFinished = new Promise(resolve => {
          native!.ondataavailable = event => {
            if (!event.data.size) return;
            parts.push(event.data); nativeBytes += event.data.size;
            if (!accepting || decoding) return;
            decoding = true;
            void decode(new Blob(parts, { type: native!.mimeType })).then(async decoded => {
              const checkpoint = decodedWav(decoded), quality = await inspectRecording(checkpoint);
              if (!accepting) return;
              nativeAt = performance.now();
              // Measure only recent samples, not accumulated earlier speech.
              let energy = 0, samples = 0;
              for (let channel = 0; channel < decoded.numberOfChannels; channel++) {
                const data = decoded.getChannelData(channel); let sum = 0;
                const from = Math.max(0, data.length - decoded.sampleRate / 4);
                for (let i = Math.floor(from); i < data.length; i++) sum += data[i] * data[i];
                if (sum > energy) { energy = sum; samples = data.length - Math.floor(from); }
              }
              nativeLevel = Math.sqrt(energy / Math.max(1, samples));
              if (!quality.silent && quality.duration >= 0.2) { nativeCheckpoint = checkpoint; onCheckpoint?.(checkpoint); }
            }).catch(() => { /* Incomplete containers may need the final chunk. */ }).finally(() => { decoding = false; });
          };
          native!.onstop = () => resolve(parts.length ? new Blob(parts, { type: native!.mimeType }) : null);
          native!.onerror = () => { interruption = true; resolve(null); };
        });
        native.start(500);
      } catch { native = undefined; nativeFinished = undefined; }
    }
    if (context) {
      try {
        source = context.createMediaStreamSource(stream);
        analyser = context.createAnalyser(); analyser.fftSize = 2048;
        silent = context.createGain(); silent.gain.value = 0;
        source.connect(analyser); analyser.connect(silent); silent.connect(context.destination);
        const code = `class Recorder extends AudioWorkletProcessor {
          constructor(){super();this.done=false;this.port.onmessage=e=>{if(e.data==='flush'){this.done=true;this.port.postMessage({flushed:true});}};}
          process(inputs){if(!this.done && inputs[0]?.length){let best=inputs[0][0],energy=-1;for(const channel of inputs[0]){let sum=0;for(const sample of channel)sum+=sample*sample;if(sum>energy){energy=sum;best=channel;}}this.port.postMessage(best.slice());}return true;}
        } registerProcessor('recorder', Recorder);`;
        moduleUrl = URL.createObjectURL(new Blob([code], { type: "application/javascript" }));
        const loaded = await bounded(context.audioWorklet.addModule(moduleUrl).then(() => true), 1500, false);
        if (!loaded) throw new Error("Audio worklet did not start");
        URL.revokeObjectURL(moduleUrl); moduleUrl = undefined;
        processor = new AudioWorkletNode(context, "recorder");
        processor.port.onmessage = event => {
          if (event.data?.flushed) { flushed?.(); return; }
          if (!(event.data instanceof Float32Array) || !accepting) return;
          if (total < context!.sampleRate * 45) { chunks.push(event.data); total += event.data.length; }
        };
        source.connect(processor); processor.connect(silent);
      } catch { /* Native recording and its decoded meter remain independent. */ }
    }
    if (!native && !processor) throw new RecordingError("This browser could not start audio capture. Try another browser or microphone.", "microphone_unavailable");
    let nextCheckpoint = 1;
    const checkpoint = () => {
      if (!onCheckpoint) return;
      if (nativeCheckpoint) onCheckpoint(nativeCheckpoint);
      else if (chunks.length && context) onCheckpoint(wav(chunks, context.sampleRate));
    };
    changed = () => { if (!stopped && (track.readyState === "ended" || track.muted)) interruption = true; };
    track.addEventListener("mute", changed); track.addEventListener("ended", changed);
    context?.addEventListener("statechange", changed);
    const samples = new Float32Array(2048);
    const feedback = () => {
      const seconds = Math.min(45, (performance.now() - started) / 1000); onTick(seconds);
      let level = performance.now() - nativeAt < 1500 ? nativeLevel : 0;
      if (analyser && context?.state === "running") {
        analyser.getFloatTimeDomainData(samples);
        let energy = 0; for (const sample of samples) energy += sample * sample;
        level = Math.max(level, Math.sqrt(energy / samples.length));
      }
      const interrupted = track.readyState === "ended" || track.muted;
      if (interrupted) interruption = true;
      const paused = !!context && context.state !== "running";
      signal({ level, label, state: interrupted ? "interrupted" : paused ? "paused" : seconds >= 2 && level === 0 ? "no_signal" : "recording",
        contextState: context?.state || "unavailable", trackState: track.readyState, muted: track.muted,
        frames: total, nativeBytes, path: native ? processor ? "native+pcm" : "native" : "pcm" });
      if (seconds >= nextCheckpoint) { checkpoint(); nextCheckpoint = Math.floor(seconds) + 1; }
      if (seconds >= 45 || track.readyState === "ended") { clearInterval(timer); onLimit(); }
    };
    leave = () => { if (stopped) return; checkpoint(); stopped = true; cleanup(); };
    window.addEventListener("pagehide", leave, { once: true });
    timer = window.setInterval(feedback, 100); feedback();
    return async () => {
      if (stopped) throw new RecordingError("Recording already stopped", "interrupted_audio");
      stopped = true; clearInterval(timer); window.removeEventListener("pagehide", leave);
      try {
        if (processor && context?.state === "running") await bounded(new Promise<boolean>(resolve => { flushed = () => resolve(true); processor!.port.postMessage("flush"); }), 700, false);
        let audio = wav(chunks, context?.sampleRate || 48000);
        if (native && nativeFinished) {
          if (native.state !== "inactive") native.stop();
          const encoded = await bounded(nativeFinished, 2000, null);
          if (encoded) {
            try {
              const decoded = await bounded<AudioBuffer | null>(decode(encoded), 4000, null);
              if (decoded) { const direct = decodedWav(decoded), quality = await inspectRecording(direct); if (!quality.silent && quality.duration >= 0.2) audio = direct; }
            } catch { /* Keep valid PCM if browser decoding fails. */ }
          }
        }
        const quality = await requireAudibleRecording(audio);
        signal({ ...microphoneState, level: quality.rms, label, state: quality.quiet ? "quiet" : "ready", message: interruption ? "The microphone was interrupted. Check the entire recording before sending." : undefined });
        return audio;
      } catch (error) { signal({ ...microphoneState, level: 0, label, state: "error", message: (error as Error).message }); throw error; }
      finally { cleanup(); }
    };
  } catch (error) {
    cleanup();
    const name = (error as Error).name;
    const message = name === "NotAllowedError" ? "Microphone access is blocked. Allow it in browser site settings and system privacy settings, then try again."
      : name === "NotFoundError" || name === "OverconstrainedError" ? "The selected microphone is unavailable. Choose Default microphone or reconnect it."
      : name === "NotReadableError" ? "The browser cannot read the microphone. Close other recording apps and try again."
      : (error as Error).message;
    signal({ level: 0, label: "", state: "error", message });
    throw new RecordingError(message, "microphone_unavailable");
  }
}
