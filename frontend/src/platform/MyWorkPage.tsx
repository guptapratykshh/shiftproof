import { statusLabel } from "./workspaceLabels";
import { ScrollArea } from "../components/OperationalUI";
import { tr } from "../i18n";
import { Mic } from "lucide-react";
import { useWorkspace } from "./WorkspaceContext";
export default function MyWorkPage() {
  const {
    call,
    session,
    view,
    setSelected,
    busy,
    setPage,
    base,
    online,
    t,
    reasonText,
    nextText,
    ownerText,
    setTaskContext,
    navigate,
    act,
    clearCapture,
    source,
  } = useWorkspace();
  return (
    <div className="my-work-list">
      <ScrollArea
        label={t("मेरा काम और भेजे हुए अपडेट", "My work and sent updates")}
      >
        {!view.batches.length && (
          <section className="platform-panel">
            <h2>{t("अभी कोई काम असाइन नहीं है", "No work assigned yet")}</h2>
            <p>
              {t(
                "सुपरवाइज़र से अपनी शिफ्ट जाँचने को कहें।",
                "Ask your supervisor to check your shift assignment.",
              )}
            </p>
          </section>
        )}
        {view.batches.map((b) => (
          <section className="platform-panel" key={b.id}>
            <div className="section-row">
              <h2>
                {b.id} · {b.name}
              </h2>
              <span className={"state-tag " + b.status}>
                {t(
                  b.status === "hold"
                    ? "जाँच बाकी"
                    : b.status === "verified"
                      ? "जाँच पूरी"
                      : "रिपोर्ट चाहिए",
                  statusLabel(b.status),
                )}
              </span>
            </div>
            {b.readiness_reasons?.map((r, i) => (
              <div className="reason-row" key={i}>
                <strong>{reasonText(r)}</strong>
                <p>{nextText(r)}</p>
                <small>
                  {t("जिम्मेदार", "Responsible")}: {ownerText(r.owner)}
                </small>
                {r.note_ids.map((id) => (
                  <button
                    className="text-button"
                    key={id}
                    onClick={() => source(id)}
                  >
                    {t(
                      "मूल अपडेट सुनें / देखें",
                      "Listen to / view original update",
                    )}
                  </button>
                ))}
              </div>
            ))}
            {b.tasks
              .filter(
                (task) => !task.owner_id || task.owner_id === session?.user.id,
              )
              .map((task) => (
                <div className="reason-row" key={task.id}>
                  <strong>
                    {task.id.endsWith(":quality") ? tr(task.title) : task.title}
                  </strong>
                  <p>
                    {task.status === "completed"
                      ? t("सुपरवाइज़र ने पूरा माना", "Verified complete")
                      : task.status === "reported_complete"
                        ? t(
                            "पूरा बताया · जाँच बाकी",
                            "Completion reported · awaiting review",
                          )
                        : t("बाकी है", "Outstanding")}
                  </p>
                  {!["completed", "reported_complete"].includes(task.status) &&
                    task.owner_id === session?.user.id && (
                      <button
                        className="button-orange"
                        disabled={busy}
                        onClick={() =>
                          navigate(() => {
                            clearCapture();
                            setSelected(b.id);
                            setTaskContext({ id: task.id, title: task.title });
                            setPage("capture");
                          })
                        }
                      >
                        <Mic size={18} />
                        {t(
                          "काम पूरा होने का अपडेट बोलें",
                          "Record completion update",
                        )}
                      </button>
                    )}
                  {!["completed", "reported_complete"].includes(
                    task.status,
                  ) && (
                    <button
                      className="button-outline"
                      disabled={
                        busy || !online || task.owner_id !== session?.user.id
                      }
                      onClick={() =>
                        void act(() =>
                          call(base + "/tasks/" + task.id, {
                            action: "report_complete",
                            reason: "Worker reported completion",
                            expected_version: view.version,
                          }),
                        )
                      }
                    >
                      {t("काम पूरा बताया", "Report work completed")}
                    </button>
                  )}
                </div>
              ))}
            <button
              className="button-outline"
              onClick={() =>
                navigate(() => {
                  clearCapture();
                  setSelected(b.id);
                  setPage("capture");
                })
              }
            >
              <Mic size={18} />
              {t("इस काम का अपडेट बोलें", "Record an update for this work")}
            </button>
          </section>
        ))}
        <section className="platform-panel">
          <h2>{t("मेरे भेजे अपडेट", "My sent updates")}</h2>
          {view.notes
            .filter(
              (n) =>
                n.actor.id === session?.user.id && n.status !== "discarded",
            )
            .slice()
            .reverse()
            .map((n) => (
              <article className="reason-row" key={n.id}>
                <strong>{n.batch_id}</strong>
                <p>
                  {n.transcripts.at(-1)?.text ||
                    t("रिकॉर्डिंग सुरक्षित है", "Recording saved")}
                </p>
                <button className="text-button" onClick={() => source(n.id)}>
                  {t("रिकॉर्डिंग / इतिहास देखें", "View recording / history")}
                </button>
                {n.error && (
                  <p>
                    {t(
                      "इस अपडेट को दोबारा जाँचने के लिए सुपरवाइज़र से कहें।",
                      "Ask your supervisor to check this saved update again.",
                    )}
                  </p>
                )}
              </article>
            ))}
        </section>
      </ScrollArea>
    </div>
  );
}
