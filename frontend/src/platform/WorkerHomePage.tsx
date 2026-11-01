import {
  Mic,
  ClipboardCheck,
  ListChecks,
  FileAudio,
} from "lucide-react";
import { Panel } from "../components/OperationalUI";
import { useWorkspace } from "./WorkspaceContext";
import { formatTime } from "./workspaceLabels";

export default function WorkerHomePage() {
  const {
    view,
    session,
    t,
    navigate,
    setPage,
    setSelected,
    clearCapture,
    allNotes,
    submitted,
    source,
    reportProgress,
    org,
  } = useWorkspace();
  const recent = allNotes
    .filter(
      (n) =>
        (n.reported_by?.id || n.actor.id) === session?.user.id && submitted(n),
    )
    .sort((a, b) => b.received_at.localeCompare(a.received_at))
    .slice(0, 4);
  const outstanding = view.batches.flatMap((b) =>
    b.tasks
      .filter(
        (task) =>
          task.status !== "completed" &&
          (!task.owner_id || task.owner_id === session?.user.id),
      )
      .map((task) => ({ ...task, batch: b })),
  );
  const openCapture = (id?: string) =>
    navigate(() => {
      if (id) {
        clearCapture();
        setSelected(id);
      }
      setPage("capture");
    });
  return (
    <div className="worker-home">
      <section className="record-hero">
        <div>
          <span className="eyebrow">
            {t("आपकी शिफ्ट का अपडेट", "Your shift update")}
          </span>
          <h2>
            {t("काम की बात, आपकी आवाज़ में।", "Your work. In your words.")}
          </h2>
          <p>
            {t(
              "काम चुनें, अपनी बात बोलें, फिर सुनकर भेजें। सुपरवाइज़र रिपोर्ट की जाँच करेंगे।",
              "Choose your work, speak, then listen and send. Your supervisor will check the report.",
            )}
          </p>
          <button className="hero-record-action" onClick={() => openCapture()}>
            <Mic size={26} />
            {t("अपडेट बोलें", "Record an update")}
          </button>
        </div>
        <div className="hero-mic" aria-hidden="true">
          <Mic size={56} />
        </div>
      </section>
      <div className="home-grid">
        <Panel
          title={t("आपका काम", "Assigned work")}
          actions={
            <button
              className="text-button"
              onClick={() => navigate(() => setPage("mywork"))}
            >
              {t("सभी देखें", "View all")} 
            </button>
          }
        >
          {!view.batches.length && (
            <p>
              {t(
                "अभी काम असाइन नहीं हुआ है। सुपरवाइज़र से अपनी शिफ्ट जाँचने को कहें।",
                "No work assigned yet. Ask your supervisor to check your shift.",
              )}
            </p>
          )}
          {view.batches.slice(0, 4).map((b) => (
            <div className="task-row" key={b.id}>
              <ListChecks className="task-icon" />
              <div>
                <strong>
                  {b.id} · {b.name}
                </strong>
                <p>
                  {outstanding.filter((task) => task.batch.id === b.id).length
                    ? t("कुछ काम अभी बाकी है", "Outstanding tasks remain")
                    : t(
                        "इस काम की स्थिति बताएं",
                        "Share the latest status of this work",
                      )}
                </p>
              </div>
              <button
                className="button-outline"
                onClick={() => openCapture(b.id)}
              >
                {t("बोलें", "Record")}
              </button>
            </div>
          ))}
        </Panel>
        <Panel title={t("अगली शिफ्ट के लिए", "Before you leave")}>
          <ClipboardCheck size={30} className="attention-icon" />
          <p>
            {t(
              "बाकी काम सुनें और पुष्टि करें कि आपने हैंडओवर प्राप्त किया है।",
              "Hear outstanding work and confirm you received the handover.",
            )}
          </p>
          <button
            className="button-outline"
            onClick={() => navigate(() => setPage("handover"))}
          >
            {t("हैंडओवर देखें", "Open handover")} 
          </button>
        </Panel>
      </div>
      <Panel title={t("आपके भेजे हुए अपडेट", "Your recent updates")}>
        {!recent.length && (
          <p>
            {t(
              "आपके भेजे हुए अपडेट यहाँ दिखेंगे।",
              "Your submitted updates will appear here.",
            )}
          </p>
        )}
        {recent.map((n) => (
          <div className="activity-row" key={n.id}>
            <FileAudio className="task-icon" />
            <div>
              <strong>{n.batch_id}</strong>
              <p>{reportProgress(n)}</p>
              <p>{formatTime(n.received_at, org.timezone)}</p>
            </div>
            <button className="text-button" onClick={() => source(n.id)}>
              {t("विवरण", "Details")}
            </button>
          </div>
        ))}
      </Panel>
    </div>
  );
}
