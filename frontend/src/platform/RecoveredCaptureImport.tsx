import { tr } from "../i18n";
import { useState } from "react";
import { binary, call, setActiveShift } from "./client";
import {
  readRecoveryFile,
  recoveryAudio,
  type RecoveryFile,
} from "./recoveryFiles";
export default function RecoveredCaptureImport({
  organizationId,
  currentShiftId,
  parentBusy,
  done,
}: {
  organizationId: string;
  currentShiftId: string;
  parentBusy: (busy: boolean) => void;
  done: (shiftId: string) => Promise<void>;
}) {
  const [data, setData] = useState<RecoveryFile | null>(null),
    [reason, setReason] = useState(""),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [notice, setNotice] = useState("");
  return (
    <details className="platform-panel">
      <summary>{tr("Recover an older offline report")}</summary>
      <p>
        {tr(
          "Use the worker’s downloaded recovery file after the 72-hour upload window. The original author, shift, recording and question stay attached. Importing does not verify the report. Share this private file only with the organization’s authorized supervisor.",
        )}
      </p>
      {error && (
        <p className="platform-error" role="alert">
          {tr(error)}
        </p>
      )}
      {notice && <p role="status">{tr(notice)}</p>}
      <form
        className="platform-form"
        onSubmit={async (e) => {
          e.preventDefault();
          if (!data) return;
          setBusy(true);
          parentBusy(true);
          let completed = false;
          setError("");
          try {
            if (data.organizationId !== organizationId)
              throw new Error("This report belongs to another organization.");
            const audio = recoveryAudio(data);
            setActiveShift(data.shiftId);
            const result = await call<{
              note: { id: string };
              upload_url: string;
            }>(`/organizations/${organizationId}/recovered-captures`, {
              note: {
                batch_id: data.itemId,
                shift_id: data.shiftId,
                recorded_at: data.recordedAt,
                reported_by_id: data.reportedById,
                idempotency_key: data.id,
                supersedes: data.corrections,
                task_id: data.task?.id,
                ...(data.reply
                  ? {
                      clarification_ref: data.reply.id,
                      clarification_version: data.reply.version,
                      clarification_context: data.reply,
                    }
                  : {}),
              },
              original_actor_id: data.userId,
              reason,
              transcript: data.transcript || undefined,
              audio_expected: !!audio,
            });
            if (audio) await binary(result.upload_url, audio, "PUT");
            await done(data.shiftId);
            completed = true;
            setNotice(
              "Original report saved. Open it below to inspect or process the saved evidence. No review was inferred.",
            );
            setData(null);
          } catch (e) {
            setError((e as Error).message);
          } finally {
            if (!completed) setActiveShift(currentShiftId);
            parentBusy(false);
            setBusy(false);
          }
        }}
      >
        <label>
          {tr("Worker recovery file")}
          <input
            type="file"
            accept="application/json,.json"
            disabled={busy}
            onChange={async (e) => {
              setError("");
              setNotice("");
              const f = e.target.files?.[0];
              if (!f) {
                setData(null);
                return;
              }
              try {
                const d = await readRecoveryFile(f);
                if (d.organizationId !== organizationId)
                  throw new Error(
                    "This recovery file belongs to another organization.",
                  );
                setData(d);
              } catch (e) {
                setData(null);
                setError((e as Error).message);
              }
            }}
          />
        </label>
        {data && (
          <>
            <p>
              {data.itemId} · {data.shiftId} · {data.recordedAt}
              <br />
              {tr("Original author:")}
              {data.userId}
              {data.transcript && (
                <>
                  <br />
                  {data.transcript}
                </>
              )}
            </p>
            <label>
              {tr("Why is this late report being recovered?")}
              <textarea
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                minLength={10}
                maxLength={600}
                required
                disabled={busy}
              />
            </label>
            <button className="button-dark" disabled={busy}>
              {tr("Save recovery report")}
            </button>
          </>
        )}
      </form>
    </details>
  );
}
