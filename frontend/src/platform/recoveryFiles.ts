import type { CaptureDraft } from "./drafts";
export type RecoveryFile = Omit<
  CaptureDraft,
  "audio" | "updatedAt" | "noteId"
> & { format: "shiftproof-offline-capture-v1"; audio_base64: string | null };
export async function downloadRecoveryFile(draft: CaptureDraft) {
  let audio_base64: string | null = null;
  if (draft.audio) {
    const bytes = new Uint8Array(await draft.audio.arrayBuffer());
    let value = "";
    for (let i = 0; i < bytes.length; i += 8192)
      value += String.fromCharCode(...bytes.subarray(i, i + 8192));
    audio_base64 = btoa(value);
  }
  const { audio, updatedAt, noteId, ...metadata } = draft;
  const data: RecoveryFile = {
    ...metadata,
    format: "shiftproof-offline-capture-v1",
    audio_base64,
  };
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(data)], { type: "application/json" }),
  );
  const a = document.createElement("a");
  a.href = url;
  a.download = `shiftproof-recovery-${draft.id}.json`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
export async function readRecoveryFile(file: File): Promise<RecoveryFile> {
  if (file.size > 8 * 1024 * 1024)
    throw new Error("Recovery file is too large (8 MB maximum).");
  const value = JSON.parse(await file.text()) as RecoveryFile;
  if (
    value.format !== "shiftproof-offline-capture-v1" ||
    ![
      value.id,
      value.userId,
      value.organizationId,
      value.itemId,
      value.shiftId,
      value.recordedAt,
    ].every((v) => typeof v === "string" && v.length > 0) ||
    !Number.isFinite(Date.parse(value.recordedAt)) ||
    typeof value.transcript !== "string" ||
    value.transcript.length > 4000 ||
    !Array.isArray(value.corrections) ||
    !(value.audio_base64 === null || typeof value.audio_base64 === "string")
  )
    throw new Error("This is not a valid ShiftProof recovery file.");
  if (!value.audio_base64 && !value.transcript.trim())
    throw new Error("Recovery file has no recording or report text.");
  return value;
}
export function recoveryAudio(data: RecoveryFile) {
  if (!data.audio_base64) return null;
  const bytes = Uint8Array.from(atob(data.audio_base64), (c) =>
    c.charCodeAt(0),
  );
  return new Blob([bytes], { type: "audio/wav" });
}
