import { tr, claimValue, bilingual as t } from "../i18n";
import { API, type Organization } from "./client";
import { label, formatTime } from "./workspaceLabels";
import type { Note, Workspace } from "../types";
export default function EvidenceTimeline({
  note,
  view,
  org,
}: {
  note: Note;
  view: Workspace | null;
  org: Organization;
}) {
  const claims =
    view?.batches
      .flatMap((b) => b.claim_history || [])
      .filter((c) => c.note_id === note.id) || [];
  const events = [
    ...note.transcripts.map((t) => ({
      id: "t" + t.revision,
      time: t.created_at,
      title: tr("Transcript v") + t.revision + " · " + label(t.kind),
      text: t.text,
      detail: "",
    })),
    ...claims.map((c) => ({
      id: c.id,
      time: c.received_at,
      title:
        label(c.property) +
        " / " +
        claimValue(c) +
        " · " +
        tr(
          c.status === "confirmed"
            ? "Human-reviewed"
            : c.status === "draft"
              ? "Reported - needs review"
              : c.status,
        ),
      text: c.excerpt,
      detail:
        tr("Transcript v") +
        c.transcript_revision +
        (c.supersedes.length
          ? " · " + tr("Correction targets:") + " " + c.supersedes.join(", ")
          : ""),
    })),
    ...(view?.resolutions
      .filter(
        (r) => r.note_id === note.id || claims.some((c) => c.id === r.claim_id || r.supersedes?.includes(c.id)),
      )
      .map((r) => ({
        id: r.id,
        time: r.created_at,
        title: r.actor.name + " · " + tr(r.action),
        text: r.reason,
        detail: r.supersedes?.length
          ? tr("Supersedes:") + " " + r.supersedes.join(", ")
          : "",
      })) || []),
  ].sort((a, b) => new Date(a.time).getTime() - new Date(b.time).getTime());
  return (
    <div className="evidence-detail">
      <strong>
        {note.actor.name} · {note.batch_id}
      </strong>
      <p>
        {tr("Recorded")} {formatTime(note.recorded_at, org.timezone)}
        <br />
        {tr("Received")} {formatTime(note.received_at, org.timezone)}
      </p>
      {note.has_audio && (
        <audio
          controls
          src={
            API + "/organizations/" + org.id + "/notes/" + note.id + "/audio"
          }
        />
      )}
      {note.task_context && <blockquote><strong>{tr("Completion update for")}: {note.task_context.title}</strong><p>{note.task_completion?.excerpt}</p></blockquote>}
      {note.cancelled_reason && <blockquote><strong>{t("कारण देकर बंद की गई रिपोर्ट", "Report closed with a reason")}</strong><p>{note.cancelled_reason}</p><small>{note.cancelled_by?.name}{note.cancelled_at && ` · ${formatTime(note.cancelled_at, org.timezone)}`}</small></blockquote>}
      {note.carry_forward && <blockquote><strong>{t("अधूरी रिपोर्ट अगली शिफ्ट को सौंपी गई", "Unfinished report carried forward")}</strong><p>{note.carry_forward.reason}</p><small>{note.carry_forward.actor.name} · {formatTime(note.carry_forward.created_at, org.timezone)}</small></blockquote>}
      {note.audio_quality?.silent && <p role="alert">{tr("This recording contains no sound. Test the microphone and record again.")}</p>}
      {note.clarification_context && (
        <blockquote>
          <small>
            {tr("Stored clarification · v")}
            {note.clarification_context.version}
          </small>
          <p>{note.clarification_context.text}</p>
        </blockquote>
      )}
      <ol className="evidence-timeline">
        {events.map((e) => (
          <li key={e.id}>
            <small>{formatTime(e.time, org.timezone)}</small>
            <h3>{e.title}</h3>
            <p>{e.text}</p>
            {e.detail && <small>{e.detail}</small>}
          </li>
        ))}
      </ol>
      <details>
        <summary>{tr("Provider details")}</summary>
        <pre>
          {JSON.stringify(
            {
              provider: note.extraction_provider,
              model: note.extraction_model,
              prompt: note.extraction_prompt_version,
              origin: note.extraction_origin,
              request: note.extraction_request_id,
              timings: note.timings,
              audio_quality: note.audio_quality,
              error_category: note.error_category,
            },
            null,
            2,
          )}
        </pre>
      </details>
    </div>
  );
}
