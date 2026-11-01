import { Select } from "../components/Select";
import { useState } from "react";
import { Panel, ScrollArea } from "../components/OperationalUI";
import { useWorkspace } from "./WorkspaceContext";
import { formatTime } from "./workspaceLabels";

export default function ReportsPage() {
  const {
    view,
    allNotes,
    t,
    org,
    source,
    openReport,
    reviewer,
    reportProgress,
    navigate,
    setPage,
    setSelected,
    clearCapture,
    historyOffset,
    act,
    workspacePath,
    shiftRef,
    setOlderNotes,
    setHistoryOffset,
    call,
  } = useWorkspace();
  const [query, setQuery] = useState(""),
    [item, setItem] = useState("all"),
    [status, setStatus] = useState("all");
  const pending = (id: string) =>
    view.batches.some((b) =>
      b.claims.some((c) => c.note_id === id && c.status === "draft"),
    );
  const notes = allNotes
    .filter(
      (n) =>
        (item === "all" || n.batch_id === item) &&
        (status === "all" ||
          (status === "review" &&
            n.status !== "discarded" &&
            (n.status !== "processed" || pending(n.id))) ||
          (status === "checked" &&
            n.status === "processed" &&
            !pending(n.id))) &&
        (
          n.batch_id +
          " " +
          n.actor.name +
          " " +
          (n.reported_by?.name || "") +
          " " +
          (n.transcripts.at(-1)?.text || "")
        )
          .toLowerCase()
          .includes(query.toLowerCase()),
    )
    .sort((a, b) => b.received_at.localeCompare(a.received_at));
  return (
    <Panel
      title={t("रिपोर्टें और रिकॉर्डिंग", "Reports & evidence")}
      description={t(
        "रिकॉर्डिंग सुनें, रिपोर्ट जाँचें और हर फ़ैसले का आधार देखें।",
        "Listen, check each report and follow decisions back to their sources.",
      )}
    >
      <div className="reports-filters">
        <label>
          {t("रिपोर्ट खोजें", "Search reports")}
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={t("नाम, काम या शब्द", "Name, work or words")}
          />
        </label>
        <label>
          {t("काम", "Work item")}
          <Select value={item} onChange={(e) => setItem(e.target.value)}>
            <option value="all">{t("सभी काम", "All work")}</option>
            {view.batches.map((b) => (
              <option value={b.id} key={b.id}>
                {b.id} · {b.name}
              </option>
            ))}
          </Select>
        </label>
        <label>
          {t("स्थिति", "Status")}
          <Select value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="all">{t("सभी रिपोर्टें", "All reports")}</option>
            <option value="review">{t("जाँच बाकी", "Needs review")}</option>
            <option value="checked">
              {t("निपटाई गई रिपोर्टें", "Processed reports")}
            </option>
          </Select>
        </label>
      </div>
      <ScrollArea label={t("रिपोर्टों की सूची", "Report list")}>
        {!notes.length && (
          <p className="empty-state">
            {t(
              "इस चयन में कोई रिपोर्ट नहीं है।",
              "No reports match this selection.",
            )}
          </p>
        )}
        {notes.map((n) => (
          <article className="report-list-row" key={n.id}>
            <div>
              <h3>
                {n.batch_id} · {n.reported_by?.name || n.actor.name}
              </h3>
              <small>{formatTime(n.received_at, org.timezone)}</small>
              <p>
                {n.transcripts.at(-1)?.text ||
                  t(
                    "रिकॉर्डिंग सहेजी गई है; लिखे हुए शब्द अभी उपलब्ध नहीं हैं।",
                    "Recording saved; transcript not available yet.",
                  )}
              </p>
              <span className="status-badge info">{reportProgress(n)}</span>
            </div>
            <div className="report-row-actions">
              {reviewer && n.status !== "discarded" && (
                <button
                  className="button-outline"
                  disabled={[
                    "queued",
                    "processing",
                    "awaiting_upload",
                  ].includes(n.status)}
                  onClick={() => openReport(n.id)}
                >
                  {t("सुनें और जाँचें", "Listen and check")}
                </button>
              )}
              <button className="text-button" onClick={() => source(n.id)}>
                {t("रिकॉर्डिंग और इतिहास", "Evidence & history")}
              </button>
              {reviewer && n.status !== "discarded" && n.error && (
                <button
                  className="text-button"
                  onClick={() =>
                    navigate(() => {
                      clearCapture();
                      setSelected(n.batch_id);
                      setPage("capture");
                    })
                  }
                >
                  {t("सहेजी रिपोर्ट की मदद करें", "Recover saved report")}
                </button>
              )}
            </div>
          </article>
        ))}
      </ScrollArea>
      {(historyOffset === undefined ? view.next_offset : historyOffset) !=
        null && (
        <button
          className="button-outline"
          onClick={() =>
            act(async () => {
              const r = await call<{
                notes: typeof allNotes;
                next_offset?: number | null;
              }>(
                workspacePath() +
                  `${shiftRef.current ? "&" : "?"}offset=${historyOffset === undefined ? view.next_offset : historyOffset}&limit=50`,
              );
              setOlderNotes((old) => [
                ...old,
                ...r.notes.filter((n) => !old.some((o) => o.id === n.id)),
              ]);
              setHistoryOffset(r.next_offset);
            })
          }
        >
          {t("पुरानी रिपोर्टें देखें", "Load older reports")}
        </button>
      )}
    </Panel>
  );
}
