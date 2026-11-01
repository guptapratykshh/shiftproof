import { Select } from "../components/Select";
import SavedReportCards from "./SavedReportCards";
import SpokenSummary from "./SpokenSummary";
import { ScrollArea } from "../components/OperationalUI";
import { label, formatTime } from "./workspaceLabels";
import { tr, claimValue, answerItem, answerHeading } from "../i18n";
import { Mic, Square, Play, Pause, Check } from "lucide-react";
import { setActiveShift } from "./client";
import MicrophonePanel from "../components/MicrophonePanel";
import RecoveredCaptureImport from "./RecoveredCaptureImport";
import { useWorkspace } from "./WorkspaceContext";
export default function CapturePage() {
  const {
    call,
    orgId,
    session,
    org,
    view,
    setError,
    selected,
    setSelected,
    busy,
    setBusy,
    setPage,
    base,
    shiftId,
    setShiftId,
    shiftRef,
    directory,
    online,
    draftStatus,
    arming,
    playing,
    typing,
    setTyping,
    reportedById,
    setReportedById,
    assistedWorkers,
    reporterRef,
    captureReporter,
    readIdentity,
    captureContext,
    t,
    reasonText,
    nextText,
    ownerText,
    worker,
    taskContext,
    transcript,
    setTranscript,
    blob,
    blobUrl,
    recording,
    seconds,
    saved,
    setSaved,
    stage,
    reply,
    setReply,
    corrections,
    setCorrections,
    answer,
    setAnswer,
    setShowItem,
    setEditingItem,
    capture,
    item,
    allNotes,
    lastSubmission,
    setLastSubmission,
    reportProgress,
    submitted,
    hasDraft,
    navigate,
    refresh,
    act,
    record,
    sendRecording,
    uploadVoice,
    extract,
    clearCapture,
    playback,
    openReport,
    source,
    canManageWork,
    newCaptureProblem,
    draftCaptureProblem,
    draftShiftChoices,
    moveDraftToShift,
  } = useWorkspace();
  return (
    <>
      {!view.batches.length ? (
        <div className="platform-panel">
          <h2>{t("अभी कोई काम असाइन नहीं हुआ", "No work assigned yet")}</h2>
          <p>
            {worker
              ? t(
                  "अपने सुपरवाइज़र से इस शिफ्ट का काम असाइन करने को कहें।",
                  "Ask your supervisor to assign your work for this shift.",
                )
              : tr(
                  "Create a work item and assign it to a team and shift to start recording.",
                )}
          </p>
          {!worker && (
            <button onClick={() => setPage("overview")}>
              {tr("Open overview")}
            </button>
          )}
        </div>
      ) : (
        <>
          <label className="item-select">
            {t("किस काम का अपडेट है?", org.profile.item)}
            <Select
              value={selected}
              disabled={busy || recording || arming}
              onChange={(e) => {
                const next = e.target.value;
                navigate(() => {
                  setSelected(next);
                  if (
                    reportedById &&
                    !assistedWorkers
                      .find((w) => w.id === reportedById)
                      ?.work_item_ids.includes(next)
                  ) {
                    setReportedById("");
                    reporterRef.current = "";
                  }
                  clearCapture();
                  setAnswer(null);
                });
              }}
            >
              {view.batches.map((b) => (
                <option key={b.id} value={b.id}>
                  {b.id} · {b.name}
                </option>
              ))}
            </Select>
          </label>
          {(draftCaptureProblem || newCaptureProblem) && !recording && (
            <section className="preview-notice" role="status">
              <strong>{tr("Check the shift date")}</strong>
              <p>{tr(draftCaptureProblem || newCaptureProblem)}</p>
              {view.allowed_shifts?.find(s => s.id === shiftId)?.ends_at && (
                <p>{tr("Shift ends at")}: {new Date(view.allowed_shifts.find(s => s.id === shiftId)!.ends_at!).toLocaleString(org.timezone ? undefined : "en-IN", {timeZone: org.timezone})}</p>
              )}
              {!!draftShiftChoices.length && (
                <div>
                  <p>{tr("Keep this recording and choose its assigned shift:")}</p>
                  {draftShiftChoices.map(s => <button key={s.id} className="button-outline" disabled={busy || !online} onClick={() => void act(() => moveDraftToShift(s.id))}>
                    {tr("Use shift")}: {s.name} · {new Date(s.starts_at!).toLocaleDateString(undefined, {timeZone: org.timezone})}
                  </button>)}
                </div>
              )}
              {org.access === "owner" && <button className="button-outline" onClick={() => navigate(() => setPage("settings", "shifts"))}>{tr("Open shift settings")}</button>}
            </section>
          )}
          {canManageWork && (
            <details className="capture-tools">
              <summary>{tr("More actions")}</summary>
              <button
                className="text-button"
                disabled={busy || recording}
                onClick={() => {
                  setEditingItem(true);
                  setShowItem(true);
                }}
              >
                {tr("Edit work item details")}
              </button>
              <RecoveredCaptureImport
                organizationId={orgId}
                currentShiftId={shiftId}
                parentBusy={setBusy}
                done={async (sid) => {
                  shiftRef.current = sid;
                  setShiftId(sid);
                  setActiveShift(sid);
                  await refresh();
                }}
              />
            </details>
          )}
          {lastSubmission && (
            <section className="platform-panel submission-receipt">
              <strong>{t("अपडेट भेज दिया गया", "Update sent")}</strong>
              <p>{reportProgress(lastSubmission)}</p>
              <button
                className="text-button"
                onClick={() => source(lastSubmission.id)}
              >
                {t("भेजा हुआ अपडेट देखें", "View sent update")}
              </button>
            </section>
          )}
          <div className="capture-columns">
            <section className="platform-panel capture-panel">
              <h2>{t("नया अपडेट", "New voice note")}</h2>
              {!!assistedWorkers.length && (
                <label>
                  {t("कौन बोल रहा है?", "Who is speaking?")}
                  <Select
                    value={reportedById}
                    disabled={recording || arming || busy}
                    onChange={(e) => {
                      const next = e.target.value;
                      navigate(() => {
                        clearCapture();
                        setReportedById(next);
                        reporterRef.current = next;
                        setLastSubmission(null);
                      });
                    }}
                  >
                    <option value="">
                      {session?.user.name} · {t("मैं", "Myself")}
                    </option>
                    {assistedWorkers
                      .filter((w) => w.work_item_ids.includes(selected))
                      .map((w) => (
                        <option key={w.id} value={w.id}>
                          {w.name} · {w.id.slice(-4)}
                        </option>
                      ))}
                  </Select>
                </label>
              )}
              <p>
                <strong>
                  {assistedWorkers.find((w) => w.id === reportedById)?.name ||
                    session?.user.name}{" "}
                  · {selected}
                </strong>
              </p>
              <button
                className="text-button"
                onClick={readIdentity}
                disabled={recording || arming}
              >
                {t("नाम और काम सुनें", "Hear name and work")}
              </button>
              <p className="capture-steps">
                {t(
                  "१. बोलें  ·  २. सुनें  ·  ३. भेजें",
                  "1. Speak  ·  2. Listen  ·  3. Send",
                )}
              </p>
              <p>
                {t(
                  "हिन्दी / हिंग्लिश · 45 सेकंड तक",
                  "Hindi / Hinglish · up to 45 seconds",
                )}
              </p>
              {reply && (
                <div className="preview-notice">
                  <strong>
                    {t("इस सवाल का जवाब", "Answering this question")}
                  </strong>
                  <p>{reply.text}</p>
                  {reply.version !== view.version && !hasDraft && (
                    <button
                      disabled={busy}
                      onClick={() => {
                        if (item?.clarification) {
                          setReply({
                            ...item.clarification,
                            version: view.version,
                          });
                          capture.current = {
                            ...capture.current,
                            id: crypto.randomUUID(),
                          };
                          setSaved(null);
                        } else setReply(null);
                      }}
                    >
                      {tr("Use latest clarification")}
                    </button>
                  )}
                  {reply.version !== view.version && hasDraft && (
                    <p>
                      {t(
                        "सवाल बदल गया है। इस रिकॉर्डिंग के साथ पुराना सवाल सुरक्षित रहेगा और जाँच ज़रूरी होगी।",
                        "The question changed. This recording keeps its original question and will need review.",
                      )}
                    </p>
                  )}
                </div>
              )}
              <button
                className={"record-circle " + (recording ? "recording" : "")}
                disabled={
                  busy ||
                  (!recording && !!newCaptureProblem) ||
                  view.capture_policy_ready === false ||
                  (!recording && !!saved) ||
                  arming ||
                  (!recording && !!(blob || transcript))
                }
                onClick={record}
                aria-label={
                  recording
                    ? t("रिकॉर्डिंग रोकें", "Stop recording")
                    : t("रिकॉर्ड करें", "Start recording")
                }
              >
                {recording ? <Square /> : <Mic />}
              </button>
              <p className="record-caption">
                {recording
                  ? `${seconds.toFixed(0)} / 45 ${tr("seconds")}`
                  : arming
                    ? t("माइक खुल रहा है…", "Opening microphone…")
                    : blob
                      ? t("रिकॉर्डिंग तैयार है", "Your recording is ready")
                      : t("बोलने के लिए माइक दबाएँ", "Tap to record an update")}
              </p>
              <MicrophonePanel
                simple={worker || !!reportedById}
                disabled={busy || recording || arming}
                audio={blob}
              />
              {taskContext && (
                <p className="offline-note">
                  {t("इस काम का पूरा होने का अपडेट", "Completion update for")}:{" "}
                  <strong>{taskContext.title}</strong>
                </p>
              )}
              {blobUrl && !recording && (
                <audio
                  controls
                  src={blobUrl}
                  onError={() =>
                    setError(
                      t(
                        "रिकॉर्डिंग नहीं चल सकी। माइक जाँचें या दोबारा रिकॉर्ड करें।",
                        "Recording playback failed. Test the microphone or record again.",
                      ),
                    )
                  }
                />
              )}
              {blob && !recording && (
                <button
                  className="text-button"
                  disabled={busy || arming || !!newCaptureProblem}
                  onClick={record}
                >
                  {t("दोबारा रिकॉर्ड करें", "Record again")}
                </button>
              )}
              {(worker || reportedById) &&
                blob &&
                !saved?.transcripts.length &&
                !recording && (
                  <details className="optional-transcript">
                    <summary>
                      {t(
                        "भेजने से पहले लिखे हुए शब्द देखें (वैकल्पिक)",
                        "Check transcript before sending (optional)",
                      )}
                    </summary>
                    <p>
                      {t(
                        "रिकॉर्डिंग से शब्द लिखने के लिए इंटरनेट चाहिए। आप बिना लिखे शब्द बदले भी रिकॉर्डिंग भेज सकते हैं।",
                        "An internet connection is needed to transcribe. You can also send the recording without editing a transcript.",
                      )}
                    </p>
                    <button
                      className="button-outline"
                      disabled={
                        busy || !online || !!draftCaptureProblem || view.capture_policy_ready === false
                      }
                      onClick={uploadVoice}
                    >
                      {t("मेरे शब्द दिखाएँ", "Show my transcript")}
                    </button>
                  </details>
                )}
              {saved?.processing_stage === "transcript_review" && (
                <p>
                  {t(
                    "शब्द सहेजे गए हैं। जाँचकर अपडेट भेजें।",
                    "Transcript saved. Check it, then send the update.",
                  )}
                </p>
              )}
              {(!worker ||
                typing ||
                transcript ||
                saved?.transcripts.length) && (
                <label>
                  {t("आपके शब्द", "Transcript")}
                  <textarea
                    aria-label={tr("Transcript")}
                    value={transcript}
                    onChange={(e) => {
                      if (
                        !transcript &&
                        !saved &&
                        !blob &&
                        !captureContext.current
                      ) {
                        capture.current = {
                          id: crypto.randomUUID(),
                          at: new Date().toISOString(),
                        };
                        captureReporter.current = reporterRef.current;
                        captureContext.current = {
                          itemId: selected,
                          shiftId: shiftRef.current,
                        };
                      }
                      setTranscript(e.target.value);
                    }}
                    rows={5}
                    placeholder={t(
                      "बोलें या यहाँ अपने शब्द लिखें…",
                      "Record an update or enter the exact words here…",
                    )}
                    disabled={busy || recording || (!hasDraft && !!newCaptureProblem)}
                  />
                </label>
              )}
              {worker &&
                !typing &&
                !transcript &&
                !saved?.transcripts.length &&
                !blob && (
                  <button
                    className="text-button"
                    disabled={!!newCaptureProblem}
                    onClick={() => setTyping(true)}
                  >
                    {t("बोलने के बजाय लिखें", "Write instead of speaking")}
                  </button>
                )}
              {!!item?.claim_history?.length && !saved && (
                <details>
                  <summary>
                    {t(
                      "पहले के अपडेट में सुधार करें",
                      "Correct an earlier report",
                    )}
                  </summary>
                  {item.claims.map((c) => (
                    <label className="checkbox-label" key={c.id}>
                      <input
                        type="checkbox"
                        checked={corrections.includes(c.id)}
                        onChange={(e) =>
                          setCorrections(
                            e.target.checked
                              ? [...corrections, c.id]
                              : corrections.filter((id) => id !== c.id),
                          )
                        }
                      />
                      {label(c.property)}: {claimValue(c)} · {c.actor.name}
                    </label>
                  ))}
                </details>
              )}
              {(!worker || blob || transcript || saved) && (
                <div className="capture-actions">
                  {blob && !saved?.transcripts.length && (
                    <button
                      className="button-orange"
                      disabled={
                        busy ||
                        !!draftCaptureProblem ||
                        recording ||
                        !online ||
                        view.capture_policy_ready === false
                      }
                      onClick={
                        worker || reportedById ? sendRecording : uploadVoice
                      }
                    >
                      {worker || reportedById
                        ? t("भेजें", "Send update")
                        : t(
                            "रिकॉर्डिंग भेजें और शब्द देखें",
                            "Upload & transcribe",
                          )}
                    </button>
                  )}
                  {(!blob || !!saved?.transcripts.length) && (
                    <button
                      className="button-orange"
                      disabled={
                        busy ||
                        !!draftCaptureProblem ||
                        !online ||
                        recording ||
                        !transcript.trim() ||
                        view.capture_policy_ready === false ||
                        (!!blob && !saved?.transcripts.length)
                      }
                      onClick={extract}
                    >
                      {busy
                        ? t("अपडेट तैयार हो रहा है…", "Processing…")
                        : t("जाँच लिया · अपडेट भेजें", "Send update")}
                    </button>
                  )}
                  <button
                    className="text-button"
                    disabled={busy || recording}
                    onClick={() => {
                      if (
                        confirm(
                          t(
                            "यह अधूरा ड्राफ़्ट हटाएँ? भेजी गई रिपोर्ट सुरक्षित रहेंगी।",
                            "Discard this unfinished draft? Saved reports stay.",
                          ),
                        )
                      )
                        clearCapture();
                    }}
                  >
                    {t("नया अपडेट शुरू करें", "Start a new update")}
                  </button>
                </div>
              )}
              {stage && (
                <div role="status" className="processing-status">
                  {worker
                    ? t(
                        stage.toLowerCase().includes("transcri")
                          ? "आपके शब्द लिखे जा रहे हैं…"
                          : stage.toLowerCase().includes("upload")
                            ? "रिकॉर्डिंग भेजी जा रही है…"
                            : "अपडेट तैयार हो रहा है…",
                        label(stage),
                      )
                    : label(stage)}
                </div>
              )}
              <small>
                {t(
                  "आपकी रिपोर्ट सुपरवाइज़र की जाँच के लिए जाएगी।",
                  "Your report goes to your supervisor for review.",
                )}
              </small>
              {draftStatus && (
                <p className="local-save-status" role="status">
                  <Check size={14} />
                  {tr(draftStatus)}
                </p>
              )}
              {!online && (
                <p className="offline-note">
                  {t(
                    "ड्राफ़्ट सुरक्षित है। इंटरनेट आने पर आप खुद भेजें।",
                    "Your draft stays here. Send it yourself when the connection returns.",
                  )}
                </p>
              )}
            </section>
            <div className="reports-column">
              {item?.clarification && (
                <section className="platform-panel clarification-panel">
                  <span className="eyebrow">
                    {t("बस एक सवाल", "ONE QUESTION TO MOVE THIS FORWARD")}
                  </span>
                  <h3 lang="hi">{item.clarification.text}</h3>
                  {item.clarification.response_status &&
                  item.clarification.response_status !== "needs_answer" ? (
                    <>
                      <p>
                        {item.clarification.response_status === "reviewed"
                          ? t(
                              "जवाब की जाँच हो चुकी है। बाकी काम और रोक नीचे दिखते रहेंगे।",
                              "The answer has been reviewed. Outstanding work and holds remain visible.",
                            )
                          : t(
                              "जवाब मिल गया है। सुपरवाइज़र की जाँच बाकी है; वही जवाब दोबारा न भेजें।",
                              "Answer received. Waiting for supervisor review; do not send the same answer again.",
                            )}
                      </p>
                      {item.clarification.response_note_ids?.map((id) => (
                        <button
                          key={id}
                          className="text-button"
                          onClick={() => (worker ? source(id) : openReport(id))}
                        >
                          {worker
                            ? t("भेजा हुआ जवाब देखें", "View sent answer")
                            : t("जवाब की जाँच करें", "Review saved answer")}
                        </button>
                      ))}
                    </>
                  ) : (
                    <div className="button-row">
                      <button
                        disabled={busy}
                        className="button-outline"
                        onClick={() => playback("clarification")}
                      >
                        {playing ? <Pause size={16} /> : <Play size={16} />}{" "}
                        {playing ? t("रोकें", "Stop") : t("सुनें", "Listen")}
                      </button>
                      <button
                        disabled={
                          busy || recording || !!transcript || !!blob || !!saved
                        }
                        className="button-dark"
                        onClick={() =>
                          setReply({
                            ...item.clarification!,
                            version: view.version,
                          })
                        }
                      >
                        {t("जवाब बोलें", "Answer this question")}
                      </button>
                    </div>
                  )}
                </section>
              )}
              {!worker && (
                <section className="platform-panel">
                  <h2>{tr("What still needs attention")}</h2>
                  <ScrollArea label={tr("What still needs attention")}>
                    {item?.readiness_reasons?.map((r, i) => (
                      <article className="reason-row" key={i}>
                        <strong>{reasonText(r)}</strong>
                        <p>
                          {tr("Next:")} {nextText(r)}
                        </p>
                        <small>
                          {tr("Responsible:")} {ownerText(r.owner)}
                        </small>
                        <div>
                          {r.note_ids.map((id) => (
                            <button
                              className="text-button"
                              key={id}
                              onClick={() => source(id)}
                            >
                              {tr("View source")}
                            </button>
                          ))}
                        </div>
                      </article>
                    ))}
                    {!item?.readiness_reasons?.length && (
                      <p>{tr("No unresolved conditions recorded.")}</p>
                    )}
                  </ScrollArea>
                  <div className="question-buttons">
                    {[
                      "What is pending?",
                      "Why is this held?",
                      "What changed?",
                    ].map((q) => (
                      <button
                        key={q}
                        onClick={() =>
                          act(async () =>
                            setAnswer(
                              await call(base + "/questions", {
                                batch_id: selected,
                                question: q,
                              }),
                            ),
                          )
                        }
                      >
                        {tr(q)}
                      </button>
                    ))}
                  </div>
                  {answer && (
                    <div className="answer-output">
                      <p>{answerHeading(answer)}</p>
                      {answer.items.map((i, k) => (
                        <div key={k}>
                          <p>{answerItem(i)}</p>
                          {i.note_ids.map((id) => (
                            <button
                              className="text-button"
                              key={id}
                              onClick={() => source(id)}
                            >
                              {tr("Supporting report")}
                            </button>
                          ))}
                        </div>
                      ))}
                    </div>
                  )}
                </section>
              )}
              {worker &&
                allNotes.some(
                  (n) =>
                    (n.actor.id === session?.user.id ||
                      n.reported_by?.id === session?.user.id) &&
                    submitted(n),
                ) && (
                  <section className="platform-panel">
                    <h2>{t("आपके भेजे हुए अपडेट", "Your sent updates")}</h2>
                    {allNotes
                      .filter(
                        (n) =>
                          (n.actor.id === session?.user.id ||
                            n.reported_by?.id === session?.user.id) &&
                          n.batch_id === selected &&
                          submitted(n),
                      )
                      .slice(0, 5)
                      .map((n) => (
                        <article className="reason-row" key={n.id}>
                          <strong>
                            {formatTime(n.received_at, org.timezone)}
                          </strong>
                          <p>{reportProgress(n)}</p>
                          <button
                            className="text-button"
                            onClick={() => source(n.id)}
                          >
                            {t("भेजा हुआ अपडेट देखें", "View sent update")}
                          </button>
                        </article>
                      ))}
                  </section>
                )}
              <SpokenSummary view={view} itemId={selected} source={source} />
              {!worker && <SavedReportCards />}
              {!worker && !!item?.tasks.length && (
                <ScrollArea label={t("बाकी काम", "Outstanding tasks")}>
                  {item.tasks.map((t) => (
                    <section className="platform-panel" key={t.id}>
                      <strong>
                        {t.id.endsWith(":quality") ? tr(t.title) : t.title}
                      </strong>
                      <p>
                        {ownerText(t.owner)} · {label(t.status)}
                      </p>
                      {canManageWork && !t.id.startsWith(item.id + ":") && (
                        <form
                          className="button-row"
                          onSubmit={(e) => {
                            e.preventDefault();
                            const data = new FormData(e.currentTarget);
                            void act(() =>
                              call(base + "/tasks/" + t.id, {
                                action: "assign",
                                owner_id: data.get("owner_id"),
                                reason: "Assigned during handover review",
                                expected_version: view.version,
                              }),
                            );
                          }}
                        >
                          <Select
                            name="owner_id"
                            required
                            aria-label={tr("Responsible team member")}
                            defaultValue={t.owner_id || ""}
                          >
                            <option value="">
                              {tr("Choose responsible person")}
                            </option>
                            {directory.map((p) => (
                              <option key={p.id} value={p.id}>
                                {p.name}
                              </option>
                            ))}
                          </Select>
                          <button disabled={busy}>{tr("Assign")}</button>
                          <button
                            type="button"
                            disabled={busy}
                            onClick={() =>
                              act(() =>
                                call(base + "/tasks/" + t.id, {
                                  action:
                                    t.status === "completed"
                                      ? "reopen"
                                      : "verify",
                                  reason:
                                    "Task status reviewed during handover",
                                  expected_version: view.version,
                                }),
                              )
                            }
                          >
                            {t.status === "completed"
                              ? tr("Reopen")
                              : tr("Verify completion")}
                          </button>
                        </form>
                      )}
                    </section>
                  ))}
                </ScrollArea>
              )}
            </div>
          </div>
        </>
      )}
    </>
  );
}
