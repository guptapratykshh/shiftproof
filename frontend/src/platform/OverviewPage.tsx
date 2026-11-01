import { AlertTriangle, FileAudio, Mic } from "lucide-react";
import { Panel, SummaryStat } from "../components/OperationalUI";
import { useWorkspace } from "./WorkspaceContext";
import WorkRegisterPage from "./WorkRegisterPage";

export default function OverviewPage() {
  const {
    view,
    t,
    allNotes,
    navigate,
    setSelected,
    clearCapture,
    setPage,
    openReport,
    reportProgress,
    source,
    reviewer,
    reasonText,
  } = useWorkspace();
  const needsReview = allNotes.filter(
    (n) =>
      !["discarded", "awaiting_upload"].includes(n.status) &&
      (n.status !== "processed" ||
        view.batches.some((b) =>
          b.claims.some((c) => c.note_id === n.id && c.status === "draft"),
        )),
  );
  const held = view.batches.filter(
    (b) =>
      b.status === "hold" ||
      b.readiness_reasons?.some((r) =>
        [
          "conflict",
          "quality_hold",
          "documents_pending",
          "fault_open",
        ].includes(r.code),
      ),
  );
  const openWork = (id: string) =>
    navigate(() => {
      clearCapture();
      setSelected(id);
      setPage("capture");
    });
  return (
    <>
      <div className="overview-summary">
        <Panel
          title={t("पहले इन पर ध्यान दें", "Needs attention")}
          description={t(
            "रुके हुए काम और जाँच की प्रतीक्षा करती रिपोर्टें।",
            "Unresolved work and reports waiting for a check.",
          )}
          actions={
            <button
              className="button-outline"
              onClick={() => navigate(() => setPage("capture"))}
            >
              <Mic size={18} />
              {t("अपडेट बोलें", "Record an update")}
            </button>
          }
        >
          {!held.length && !needsReview.length && (
            <p>
              {t(
                "इस सूची में अभी कोई रोक या लंबित रिपोर्ट नहीं है। काम की पूरी स्थिति नीचे देखें।",
                "No holds or pending reports in this list. Check the work register for the full status.",
              )}
            </p>
          )}
          <ul className="attention-list">
            {held.slice(0, 3).map((b) => (
              <li key={b.id}>
                <AlertTriangle className="attention-icon danger" />
                <div>
                  <strong>
                    {b.id} · {b.name}
                  </strong>
                  <p>
                    {b.readiness_reasons?.[0]
                      ? reasonText(b.readiness_reasons[0])
                      : t("जाँच बाकी है", "A check is still required")}
                  </p>
                </div>
                <button
                  className="button-outline"
                  onClick={() => openWork(b.id)}
                >
                  {t("देखें", "Open")} 
                </button>
              </li>
            ))}
            {needsReview.slice(0, 3).map((n) => (
              <li key={n.id}>
                <FileAudio className="attention-icon" />
                <div>
                  <strong>
                    {n.batch_id} · {n.reported_by?.name || n.actor.name}
                  </strong>
                  <p>
                    {reportProgress(n)}
                  </p>
                </div>
                <button
                  className="button-outline"
                  disabled={["queued", "processing"].includes(n.status)}
                  onClick={() => (reviewer ? openReport(n.id) : source(n.id))}
                >
                  {reviewer
                    ? t("रिपोर्ट जाँचें", "Check report")
                    : t("मूल रिपोर्ट देखें", "View source report")}
                </button>
              </li>
            ))}
          </ul>
          <button
            className="text-button"
            onClick={() => navigate(() => setPage("reports"))}
          >
            {t("सभी रिपोर्टें देखें", "View all reports")}{" "}
            
          </button>
        </Panel>
        <div className="workspace-stats">
          <SummaryStat
            value={view.batches.length}
            label={t("काम", "Work items")}
          />
          <SummaryStat
            value={view.counts.holds}
            label={t("रोक बाकी", "Unresolved holds")}
          />
          <SummaryStat
            value={view.counts.unreviewed}
            label={t("बातें जाँचनी हैं", "Statements to check")}
          />
          <SummaryStat
            value={view.counts.verified}
            label={t("ज़रूरी जाँच पूरी", "Requirements reviewed")}
          />
        </div>
      </div>
      <WorkRegisterPage compact />
    </>
  );
}
