import SpokenSummary from "./SpokenSummary";
import { tr, bilingual as t } from "../i18n";
import { Play, Pause } from "lucide-react";
import { API, call } from "./client";
import VoiceAcknowledgement from "./VoiceAcknowledgement";
import type { Workspace, Batch } from "../types";
import { claimValue } from "../i18n";
import { label } from "./workspaceLabels";
import { ScrollArea } from "../components/OperationalUI";
type Reason = NonNullable<Batch["readiness_reasons"]>[number];
type Props = {
  view: Workspace;
  worker: boolean;
  busy: boolean;
  playing: boolean;
  language: "hi" | "en";
  userId: string;
  shiftId: string;
  base: string;
  playback: (kind: "clarification" | "handover", id?: string) => Promise<void>;
  statusLabel: (s: string) => string;
  reasonText: (r: Reason) => string;
  nextText: (r: Reason) => string | undefined;
  ownerText: (s?: string | null) => string;
  source: (id: string) => void;
  openReport: (id: string) => void;
  canReview: boolean;
  act: (fn: () => Promise<unknown>) => Promise<void>;
  setNotice: (s: string) => void;
  setSnapshot: (s: unknown) => void;
  refresh: () => Promise<unknown>;
  stopPlayback: () => void;
  setAckPending: (v: boolean) => void;
};
export default function HandoverPage({
  view,
  worker,
  busy,
  playing,
  language,
  userId,
  shiftId,
  base,
  playback,
  statusLabel,
  reasonText,
  nextText,
  ownerText,
  source,
  openReport,
  canReview,
  act,
  setNotice,
  setSnapshot,
  refresh,
  stopPlayback,
  setAckPending,
}: Props) {
  const blockers = view.acknowledgement_blockers || [];
  return (
    <>
      <SpokenSummary view={view} source={source} />
      <div className="section-row">
        <h2>
          {t("हैंडओवर", "Handover")}{" "}
          {worker ? "" : `${tr("v")} ${view.version}`}
        </h2>
        <button
          className="button-outline"
          disabled={busy || !view.batches.length}
          onClick={() => playback("handover", "all")}
        >
          {playing ? <Pause size={18} /> : <Play size={18} />}{" "}
          {playing
            ? t("रोकें", "Stop")
            : t("हैंडओवर सुनें", "Listen to handover")}
        </button>
      </div>
      {blockers.length > 0 && <section className="platform-panel">
        <h2>{t("प्राप्ति की पुष्टि से पहले इन रिपोर्टों की जाँच करें", "Review these reports before acknowledging")}</h2>
        <p>{canReview
          ? t("हर सहेजी हुई रिपोर्ट की जाँच करें या कारण देकर उसे अगली शिफ्ट को सौंपें। केवल ‘हो गया’ लिखने से रिपोर्ट मंज़ूर नहीं होती।", "Review each saved report or carry it forward with a reason. Writing ‘done’ does not approve reports.")
          : t("आपकी रिपोर्ट भेज दी गई है। सुपरवाइज़र उसकी जाँच करेंगे या अगली शिफ्ट को सौंपेंगे। दोबारा भेजने की ज़रूरत नहीं है।", "Your reports have been received. A supervisor must review or carry them forward; do not send them again.")}</p>
        <ScrollArea label={t("अधूरी रिपोर्टें", "Unfinished reports")}>
        {blockers.map(n => <div className="reason-row" key={n.id}>
          <strong>{n.batch_id} · {n.actor_name}</strong>
          {n.transcript_preview && <blockquote>{n.transcript_preview}</blockquote>}
          <button className="button-outline" disabled={busy} onClick={() => canReview ? openReport(n.id) : source(n.id)}>{canReview ? t("भेजी हुई रिपोर्ट की जाँच", "Review saved report") : t("भेजा हुआ अपडेट देखें", "View sent update")}</button>
        </div>)}
        </ScrollArea>
      </section>}
      <ScrollArea label={t("हैंडओवर का बाकी काम और जाँच", "Handover work and reviews")}>
      {view.batches
        .slice()
        .sort(
          (a, b) =>
            Number(b.status !== "verified") - Number(a.status !== "verified"),
        )
        .map((b) => (
          <section className="platform-panel handover-item" key={b.id}>
            <h3>
              {b.id} · {b.name}{" "}
              <span className={"state-tag " + b.status}>
                {statusLabel(b.status)}
              </span>
            </h3>
            <details className="review-progress" open={canReview}>
              <summary>{t("जाँच के फ़ैसले और बाकी काम", "Review decisions and remaining work")}</summary>
              {b.claims.map(c => {
                const decision = view.resolutions?.filter(r => r.claim_id === c.id).at(-1);
                const done = c.status === "confirmed" && !c.source_review_pending;
                return <div className="reason-row" key={c.id}>
                  <strong>{label(c.property)}: {claimValue(c)}</strong>
                  <p>{c.source_review_pending ? t("बदले हुए ट्रांसक्रिप्ट की फिर जाँच चाहिए", "Revised transcript needs another review") : statusLabel(c.status)}{decision && ` · ${decision.actor.name}`}</p>
                  {canReview && !done && <button className="button-outline" onClick={() => openReport(c.note_id)}>{t("रिपोर्ट की जाँच करें", "Review report")}</button>}
                  {done && <button className="text-button" onClick={() => source(c.note_id)}>{t("सहेजा हुआ फ़ैसला देखें", "View saved decision")}</button>}
                </div>;
              })}
            </details>
            {b.readiness_reasons?.map((r, i) => (
              <div className="reason-row" key={i}>
                <strong>{reasonText(r)}</strong>
                <p>
                  {nextText(r)} · {ownerText(r.owner)}
                </p>
                {canReview && ["unreviewed", "unfinished_notes", "source_revision", "quality_unknown", "packing_unknown"].includes(r.code) && r.note_ids.map(id => <button key={"review-" + id} className="button-outline" disabled={busy} onClick={() => openReport(id)}>{t("भेजी हुई रिपोर्ट की जाँच", "Review saved report")}</button>)}
                {r.note_ids.map((id) => (
                  <button
                    className="text-button"
                    key={id}
                    onClick={() => source(id)}
                  >
                    {tr("Source")}
                  </button>
                ))}
              </div>
            ))}
          </section>
        ))}
      </ScrollArea>
      <section className="platform-panel">
        <h2>{t("इस जानकारी की पुष्टि", "Acknowledge this version")}</h2>
        <p>
          {t(
            "यह जानकारी मिलने की पुष्टि है, काम पूरा होने की नहीं। रिपोर्टों की अलग से जाँच करें। जरूरी बदलाव पर फिर पुष्टि करें।",
            "This records what you received, not that the work is complete. Review reports separately. New material updates require another acknowledgement.",
          )}
        </p>
        {!worker && (
          <form
            className="platform-form"
            onSubmit={(e) => {
              e.preventDefault();
              const data = new FormData(e.currentTarget);
              void act(async () => {
                await call(
                  base + `/shifts/${shiftId || "shift-B"}/acknowledgements`,
                  {
                    expected_version: view.version,
                    readback: data.get("readback"),
                  },
                );
                setNotice("Acknowledged the exact stored snapshot.");
              });
            }}
          >
            <label>
              {tr("Your readback")}
              <textarea
                name="readback"
                required
                minLength={5}
                placeholder={tr("What must the incoming shift verify?")}
              />
            </label>
            <button className="button-orange" disabled={busy || blockers.length > 0}>
              {tr("Acknowledge v")}
              {view.version}
            </button>
          </form>
        )}
        {view.acknowledgements.map((a) => (
          <article className="reason-row" key={a.id}>
            <strong>
              {a.actor.name} {tr("· v")}
              {a.version} ·{" "}
              {a.current
                ? t("अभी की जानकारी", "Current")
                : t("फिर पुष्टि चाहिए", "Needs acknowledgement again")}
            </strong>
            <p>{a.readback}</p>
            {a.audio_id && (
              <audio
                controls
                src={
                  API +
                  base +
                  `/shifts/${shiftId || "shift-B"}/acknowledgements/audio/${a.audio_id}`
                }
              />
            )}
            <button
              className="text-button"
              onClick={() =>
                act(async () => {
                  const s = await call(
                    base +
                      `/shifts/${shiftId || "shift-B"}/snapshots/${a.version}`,
                  );
                  setSnapshot(s);
                })
              }
            >
              {t("उस समय का हैंडओवर देखें", "Open acknowledged snapshot")}
            </button>
          </article>
        ))}
      </section>
      <VoiceAcknowledgement
        key={shiftId}
        userId={userId}
        base={base}
        shiftId={shiftId || "shift-B"}
        version={view.version}
        blocked={blockers.length > 0}
        language={language}
        done={refresh}
        beforeRecord={stopPlayback}
        onPending={setAckPending}
      />
    </>
  );
}
