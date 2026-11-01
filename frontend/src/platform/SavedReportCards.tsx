import { statusLabel } from "./workspaceLabels";
import { ScrollArea } from "../components/OperationalUI";
import { label, formatTime } from "./workspaceLabels";
import { tr, claimValue } from "../i18n";
import { type Organization } from "./client";
import type { Workspace } from "../types";
type View = Workspace & {
  organization: Organization;
  next_offset?: number | null;
  notes_total?: number;
  data_mode?: "fictional" | "real" | "unconfigured";
  capture_policy_ready?: boolean;
};

import { useWorkspace } from "./WorkspaceContext";
export default function SavedReportCards() {
  const {
    call,
    session,
    org,
    view,
    setNotice,
    selected,
    busy,
    setEvidence,
    setRevision,
    base,
    shiftRef,
    workspacePath,
    setOlderNotes,
    historyOffset,
    setHistoryOffset,
    t,
    worker,
    item,
    allNotes,
    act,
    waitNote,
    openReport,
    reviewer,
    currentClaims,
  } = useWorkspace();
  return (
    <ScrollArea
      key={selected + ":reports"}
      label={t("भेजी हुई रिपोर्टें", "Submitted reports")}
    >
      {allNotes
        .filter((n) => n.batch_id === selected)
        .slice()
        .reverse()
        .map((n) => (
          <section className="platform-panel report-card" key={n.id}>
            <header>
              <strong>{n.reported_by?.name || n.actor.name}</strong>
              {n.assisted_by && (
                <small>
                  {t("रिकॉर्डिंग में मदद", "Recorded with assistance from")}:{" "}
                  {n.assisted_by.name}
                </small>
              )}
              <span className="state-tag">{label(n.status)}</span>
            </header>
            <p>
              {n.transcripts.at(-1)?.text ||
                tr("Recording awaiting transcription")}
            </p>
            <small>
              {formatTime(n.received_at, org.timezone)} ·{" "}
              {tr(n.extraction_provider || n.source)}
            </small>
            {n.error && <div className="preview-notice">{tr(n.error)}</div>}
            <div className="button-row">
              {reviewer &&
                n.transcripts.length > 0 &&
                !["queued", "processing", "discarded"].includes(n.status) && (
                  <button
                    className="button-orange"
                    onClick={() => openReport(n.id)}
                  >
                    {(n as any).review_progress?.can_reopen
                      ? t(
                          "रिपोर्ट फिर जाँच के लिए खोलें",
                          "Reopen report for review",
                        )
                      : t("सुनें और जाँचें", "Listen and check")}
                  </button>
                )}
              <button className="text-button" onClick={() => setEvidence(n)}>
                {tr("Evidence & history")}
              </button>
              {reviewer &&
                [
                  "awaiting_upload",
                  "received",
                  "failed",
                  "manual_review",
                  "authorization_required",
                ].includes(n.status) && (
                  <details className="note-recovery">
                    <summary>{tr("Recover unfinished update")}</summary>
                    {(["takeover", "carry_forward", "cancel"] as const).map(
                      (action) => (
                        <button
                          type="button"
                          key={action}
                          className="text-button"
                          disabled={busy}
                          onClick={() => {
                            const reason = prompt(
                              action === "cancel"
                                ? tr(
                                    "Why should this unfinished update be cancelled? Its evidence is preserved.",
                                  )
                                : action === "carry_forward"
                                  ? tr(
                                      "Why should this unfinished work carry into the incoming shift?",
                                    )
                                  : tr(
                                      "Why are you taking responsibility for this saved update?",
                                    ),
                            );
                            if (reason && reason.trim().length >= 3)
                              void act(() =>
                                call(base + "/notes/" + n.id + "/recover", {
                                  action,
                                  reason,
                                }),
                              );
                          }}
                        >
                          {action === "takeover"
                            ? tr("Take responsibility")
                            : action === "carry_forward"
                              ? tr("Carry to incoming shift")
                              : tr("Cancel unfinished update")}
                        </button>
                      ),
                    )}
                  </details>
                )}
              {n.actor.id === session?.user.id &&
                n.transcripts.length > 0 &&
                !["processing", "queued", "discarded"].includes(n.status) && (
                  <button
                    disabled={busy}
                    onClick={() =>
                      setRevision({
                        note: n,
                        text: n.transcripts.at(-1)!.text,
                        version: view.version,
                      })
                    }
                  >
                    {tr("Correct saved transcript")}
                  </button>
                )}
              {(reviewer || n.actor.id === session?.user.id) &&
                [
                  "failed",
                  "manual_review",
                  "received",
                  "awaiting_upload",
                ].includes(n.status) &&
                !currentClaims(n) && (
                  <>
                    <button
                      disabled={busy}
                      onClick={() =>
                        act(async () => {
                          await call(base + "/notes/" + n.id + "/process", {});
                          const r = await waitNote(n.id);
                          setNotice(r.error || "Extraction completed.");
                        })
                      }
                    >
                      {tr("Retry saved note")}
                    </button>
                    <button
                      disabled={
                        busy ||
                        n.claim_ids.length > 0 ||
                        n.actor.id !== session?.user.id
                      }
                      onClick={() =>
                        act(() =>
                          call(base + "/notes/" + n.id, undefined, "DELETE"),
                        )
                      }
                    >
                      {tr("Discard unfinished note")}
                    </button>
                  </>
                )}
              {reviewer &&
                ["manual_review", "failed"].includes(n.status) &&
                n.transcripts.length > 0 &&
                !currentClaims(n) && (
                  <button disabled={busy} onClick={() => openReport(n.id)}>
                    {tr("Interpret transcript manually")}
                  </button>
                )}
            </div>
            {item?.claim_history
              ?.filter((c) => c.note_id === n.id)
              .map((c) => (
                <article className="claim-row" key={c.id}>
                  <div>
                    <strong>
                      {label(c.property)}: {claimValue(c)}
                    </strong>
                    <span className={"state-tag " + c.status}>
                      {statusLabel(c.status)}
                    </span>
                  </div>
                  <q>{c.excerpt}</q>
                  {c.source_review_pending && (
                    <strong className="review-again">
                      {tr("Transcript changed - review again")}
                    </strong>
                  )}
                  <small>
                    {label(c.modality)}
                    {c.condition ? ` · ${tr("if")} ${c.condition}` : ""}
                  </small>
                  {reviewer &&
                    !["rejected", "superseded"].includes(c.status) && (
                      <button
                        className="text-button"
                        onClick={() => openReport(c.note_id)}
                      >
                        {tr("Review report")}
                      </button>
                    )}
                </article>
              ))}
          </section>
        ))}
      {!worker &&
        (historyOffset === undefined ? view.next_offset : historyOffset) !=
          null && (
          <button
            className="button-outline"
            disabled={busy}
            onClick={() =>
              void act(async () => {
                const offset =
                  historyOffset === undefined
                    ? view.next_offset
                    : historyOffset;
                const more = await call<View>(
                  workspacePath() +
                    (shiftRef.current ? "&" : "?") +
                    "offset=" +
                    offset +
                    "&limit=50",
                );
                setOlderNotes((previous) => [
                  ...previous,
                  ...more.notes.filter(
                    (n) => !previous.some((p) => p.id === n.id),
                  ),
                ]);
                setHistoryOffset(more.next_offset ?? null);
              })
            }
          >
            {tr("Load earlier reports")}
          </button>
        )}
    </ScrollArea>
  );
}
