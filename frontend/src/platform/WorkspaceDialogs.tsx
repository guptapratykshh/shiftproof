import { Select } from "../components/Select";
import { statusLabel } from "./workspaceLabels";
import ReportReview from "./ReportReview";
import EvidenceTimeline from "./EvidenceTimeline";
import { Dialog } from "../components/OperationalUI";
import { label, roleLabel } from "./workspaceLabels";
import { tr, systemText, claimValue, msg } from "../i18n";
import PasswordFields from "./PasswordFields";
import { type Organization } from "./client";
import type { Workspace, Claim } from "../types";
import { clearOfflineContext } from "./offlineContext";
type View = Workspace & {
  organization: Organization;
  next_offset?: number | null;
  notes_total?: number;
  data_mode?: "fictional" | "real" | "unconfigured";
  capture_policy_ready?: boolean;
};

const isHold = (c: Claim) =>
  [
    ["quality", "pending"],
    ["fault", "open"],
    ["documents", "pending"],
    ["repair", "pending"],
  ].some(([p, v]) => c.property === p && c.value === v);
const isClearance = (c: Claim) =>
  [
    ["quality", "cleared"],
    ["fault", "resolved"],
    ["documents", "verified"],
    ["repair", "verified"],
  ].some(([p, v]) => c.property === p && c.value === v);
import type { WorkspaceController } from "./useWorkspaceController";
export default function WorkspaceDialogs({
  state,
}: {
  state: WorkspaceController;
}) {
  const {
    call,
    session,
    org,
    view,
    error,
    setError,
    setNotice,
    selected,
    busy,
    evidence,
    setEvidence,
    revision,
    setRevision,
    base,
    operations,
    navigation,
    setNavigation,
    personal,
    setPersonal,
    confirmSpeaker,
    setConfirmSpeaker,
    speakerConfirmed,
    reportedById,
    assistedWorkers,
    readIdentity,
    snapshot,
    setSnapshot,
    captureContext,
    t,
    setTranscript,
    setBlob,
    setSaved,
    setReply,
    setCorrections,
    review,
    setReview,
    showItem,
    setShowItem,
    editingItem,
    capture,
    item,
    persistDraft,
    navigate,
    requestSignOut,
    refresh,
    act,
    record,
    clearCapture,
    reportReview,
    setReportReview,
    openReport,
    reviewer,
  } = state;
  if (!org) return null;
  return (
    <>
      {" "}
      {navigation && (
        <Dialog
          title={t("ड्राफ़्ट का क्या करें?", "Keep your unfinished update?")}
          close={() => setNavigation(null)}
        >
          <p>
            {t(
              "अपडेट अपने आप नहीं भेजा जाएगा।",
              "Your draft will never be sent automatically.",
            )}
          </p>
          <div className="button-row">
            <button
              className="button-orange"
              onClick={() =>
                void (async () => {
                  try {
                    await persistDraft();
                    const go = navigation.go;
                    setNavigation(null);
                    capture.current = {
                      id: crypto.randomUUID(),
                      at: new Date().toISOString(),
                    };
                    captureContext.current = null;
                    setTranscript("");
                    setBlob(null);
                    setSaved(null);
                    setReply(null);
                    setCorrections([]);
                    go();
                  } catch (e) {
                    setError((e as Error).message);
                  }
                })()
              }
            >
              {t("ड्राफ़्ट रखें और जाएँ", "Save draft and leave")}
            </button>
            <button
              className="button-outline"
              onClick={() => {
                const go = navigation.go;
                setNavigation(null);
                clearCapture();
                go();
              }}
            >
              {t("हटाकर जाएँ", "Discard and leave")}
            </button>
            <button className="text-button" onClick={() => setNavigation(null)}>
              {t("यहीं रहें", "Stay here")}
            </button>
          </div>
        </Dialog>
      )}
      {personal && (
        <Dialog
          title={t("मेरा खाता", "My account")}
          close={() => setPersonal(false)}
        >
          <h3>{session?.user.name}</h3>
          {session?.capabilities?.create_organization && (
            <button
              className="text-button"
              onClick={() =>
                navigate(() => {
                  location.href = "/organizations";
                })
              }
            >
              {tr("Create another organization")}
            </button>
          )}
          <p>
            {org.name} · {roleLabel(org.role)}
          </p>
          <button
            className="button-outline"
            onClick={() => void requestSignOut()}
          >
            {t("साइन आउट करें", "Sign out")}
          </button>
          <p>
            {t(
              "साइन आउट करने पर इस खाते के डिवाइस वाले ड्राफ़्ट हटेंगे।",
              "Signing out clears this account’s local drafts from this device.",
            )}
          </p>
          <details>
            <summary>{t("पासवर्ड बदलें", "Change password")}</summary>
            <form
              className="platform-form"
              onSubmit={(e) => {
                e.preventDefault();
                const data = Object.fromEntries(new FormData(e.currentTarget));
                if (data.password !== data.confirm_password) return;
                delete data.confirm_password;
                void act(async () => {
                  await call("/auth/password", data);
                  clearOfflineContext();
                  location.href = "/login";
                });
              }}
            >
              <label>
                {t("अभी का पासवर्ड", "Current password")}
                <input
                  type="password"
                  name="current_password"
                  autoComplete="current-password"
                  required
                />
              </label>
              <PasswordFields
                confirmation
                label={t("नया पासवर्ड", "New password")}
              />
              <button className="button-orange" disabled={busy}>
                {t("पासवर्ड बदलें", "Change password")}
              </button>
            </form>
          </details>
        </Dialog>
      )}
      {snapshot !== null && (
        <Dialog
          title={t("प्राप्त हैंडओवर", "Acknowledged handover")}
          close={() => setSnapshot(null)}
        >
          <SnapshotContent value={snapshot} />
        </Dialog>
      )}
      {showItem && (
        <Dialog
          title={msg(editingItem ? "Edit {item}" : "Add {item}", {
            item: tr(org.profile.item.toLowerCase()),
          })}
          close={() => setShowItem(false)}
        >
          {error && (
            <p className="platform-error" role="alert">
              {tr(error)}
            </p>
          )}
          <form
            className="platform-form"
            onSubmit={(e) => {
              e.preventDefault();
              const d = Object.fromEntries(new FormData(e.currentTarget));
              if (!d.required_dispatch_quantity)
                delete d.required_dispatch_quantity;
              void act(async () => {
                if (editingItem) {
                  const { id, ...fields } = d;
                  await call(
                    base + "/work-items/" + id,
                    {
                      ...fields,
                      target: Number(d.target || 0),
                      expected_version: view!.version,
                    },
                    "PUT",
                  );
                } else
                  await call(base + "/work-items", {
                    ...d,
                    target: Number(d.target || 0),
                  });
                setShowItem(false);
              });
            }}
          >
            <label>
              {tr("Identifier")}
              <input
                name="id"
                defaultValue={editingItem ? item?.id : ""}
                readOnly={editingItem}
                required
                pattern="[A-Za-z0-9][A-Za-z0-9_-]*"
                maxLength={64}
                placeholder={
                  org.industry === "maintenance"
                    ? "PUMP-01"
                    : org.industry === "warehousing"
                      ? "ORD-582"
                      : "BATCH-01"
                }
              />
            </label>
            <label>
              {tr("Name")}
              <input
                name="name"
                defaultValue={editingItem ? item?.name : ""}
                required
                minLength={2}
              />
            </label>
            <label>
              {tr("Location / line")}
              <input name="line" defaultValue={editingItem ? item?.line : ""} />
            </label>
            {!!operations?.locations.length && (
              <label>
                {tr("Assigned location")}
                <Select
                  name="location_id"
                  defaultValue={editingItem ? item?.location_id || "" : ""}
                >
                  <option value="">{tr("Choose location")}</option>
                  {operations.locations.map((l) => (
                    <option value={l.id} key={l.id}>
                      {l.name}
                    </option>
                  ))}
                </Select>
              </label>
            )}
            {!!operations?.teams.length && (
              <label>
                {tr("Assigned team")}
                <Select
                  name="team_id"
                  defaultValue={editingItem ? item?.team_id || "" : ""}
                >
                  <option value="">{tr("Choose team")}</option>
                  {operations.teams.map((l) => (
                    <option value={l.id} key={l.id}>
                      {l.name}
                    </option>
                  ))}
                </Select>
              </label>
            )}
            {org.industry !== "maintenance" && (
              <label>
                {tr("Target quantity")}
                <input
                  name="target"
                  type="number"
                  min={0}
                  defaultValue={editingItem ? item?.target : 0}
                />
              </label>
            )}
            {org.industry !== "maintenance" && (
              <label>
                {tr("Required dispatch quantity (optional)")}
                <input
                  name="required_dispatch_quantity"
                  type="number"
                  min={1}
                  step={1}
                  placeholder={tr("Minimum quantity that must be reviewed")}
                />
              </label>
            )}
            <button className="button-orange" disabled={busy}>
              {editingItem
                ? tr("Save changes")
                : msg("Create {item}", {
                    item: tr(org.profile.item.toLowerCase()),
                  })}
            </button>
          </form>
        </Dialog>
      )}
      {revision && (
        <Dialog
          title={tr("Correct saved transcript")}
          close={() => setRevision(null)}
        >
          {error && <p role="alert">{tr(error)}</p>}
          <p>
            {tr(
              "The original recording and previous transcripts remain in evidence. Existing claims and human reviews remain active until explicitly reviewed or superseded.",
            )}
          </p>
          <form
            className="platform-form"
            onSubmit={(e) => {
              e.preventDefault();
              void act(async () => {
                await call(base + "/notes/" + revision.note.id + "/revisions", {
                  transcript: revision.text,
                  expected_version: revision.version,
                });
                setRevision(null);
                setNotice(
                  "Transcript revision saved. Use Retry saved note to extract new draft claims; prior reviews are preserved.",
                );
              });
            }}
          >
            <label>
              {tr("Revised transcript")}
              <textarea
                required
                maxLength={4000}
                value={revision.text}
                onChange={(e) =>
                  setRevision({ ...revision, text: e.target.value })
                }
              />
            </label>
            <button className="button-orange" disabled={busy}>
              {tr("Save transcript revision")}
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={() =>
                void act(async () => {
                  const latest = await call<View>(base + "/workspace");
                  setRevision({ ...revision, version: latest.version });
                })
              }
            >
              {tr("Refresh version, keep my text")}
            </button>
          </form>
        </Dialog>
      )}
      {reportReview && org && view && reviewer && (
        <ReportReview
          key={reportReview.id}
          note={reportReview}
          org={org}
          base={base}
          version={(reportReview as any).version ?? view.version}
          claims={view.batches
            .flatMap((b) => b.claim_history || b.claims)
            .filter((c) => c.note_id === reportReview.id)}
          allClaims={view.batches.flatMap((b) => b.claim_history || b.claims)}
          close={() => setReportReview(null)}
          done={refresh}
        />
      )}
      {confirmSpeaker && (
        <Dialog
          title={t(
            "बोलने वाले और काम की पुष्टि करें",
            "Confirm speaker and work",
          )}
          close={() => setConfirmSpeaker(false)}
        >
          <p>
            {assistedWorkers.find((w) => w.id === reportedById)?.name} ·{" "}
            {selected}
          </p>
          <button className="button-outline" onClick={readIdentity}>
            {t("नाम और काम सुनें", "Hear name and work")}
          </button>
          <button
            className="button-orange"
            onClick={() => {
              setConfirmSpeaker(false);
              speakerConfirmed.current = true;
              void record();
            }}
          >
            {t("सही है, रिकॉर्ड करें", "Correct, start recording")}
          </button>
        </Dialog>
      )}
      {evidence && (
        <Dialog
          title={tr("Evidence & history")}
          close={() => setEvidence(null)}
        >
          <EvidenceTimeline note={evidence} view={view} org={org} />
        </Dialog>
      )}
      {review && view && (
        <Dialog title={tr("Review this report")} close={() => setReview(null)}>
          {error && (
            <p className="platform-error" role="alert">
              {tr(error)}
            </p>
          )}
          <p>
            <strong>
              {label(review.property)}: {claimValue(review)}
            </strong>
          </p>
          <blockquote>{review.excerpt}</blockquote>
          <form
            className="platform-form"
            onSubmit={(e) => {
              e.preventDefault();
              const data = new FormData(e.currentTarget);
              void act(async () => {
                await call(base + "/claims/" + review.id + "/resolve", {
                  action: data.get("action"),
                  reason: data.get("reason"),
                  expected_version: view.version,
                  supersedes: data.getAll("supersedes"),
                });
                setReview(null);
                setNotice(
                  t(
                    "जाँच का फ़ैसला सहेज दिया गया है। नीचे बाकी रिपोर्ट देखें।",
                    "Review decision saved. Check the remaining reports below.",
                  ),
                );
                openReport(review.note_id);
              });
            }}
          >
            {isClearance(review) && org.role !== "quality" && (
              <p className="preview-notice">
                {t(
                  "आप सामान्य रिपोर्ट की जाँच कर सकते हैं। इस मंज़ूरी को केवल अधिकृत जाँचकर्ता स्वीकृत कर सकता है। गलत रिपोर्ट हो तो ही अस्वीकार करें।",
                  "You can review ordinary reports. Only an authorized reviewer can approve this clearance. Reject it only if the interpretation is incorrect.",
                )}
              </p>
            )}
            <label>
              {tr("Decision")}
              <Select
                name="action"
                required
                defaultValue={
                  org.role !== "quality" && isClearance(review) ? "" : "confirm"
                }
              >
                <option value="" disabled>
                  {t("फ़ैसला चुनें", "Choose a decision")}
                </option>
                <option
                  value="confirm"
                  disabled={org.role !== "quality" && isClearance(review)}
                >
                  {tr("Confirm as human-reviewed")}
                </option>
                <option
                  value="reject"
                  disabled={org.role !== "quality" && isHold(review)}
                >
                  {tr("Reject this interpretation")}
                </option>
              </Select>
            </label>
            <label>
              {tr("Reason")}
              <textarea name="reason" required minLength={3} />
            </label>
            {view.batches
              .find((b) => b.id === review.batch_id)
              ?.claims.filter(
                (c) =>
                  c.id !== review.id &&
                  c.property === review.property &&
                  !["rejected", "superseded"].includes(c.status),
              )
              .map((c) => (
                <label className="checkbox-label" key={c.id}>
                  <input type="checkbox" name="supersedes" value={c.id} />
                  {tr("Explicitly supersede")} {claimValue(c)} · {c.actor.name}{" "}
                  · “{c.excerpt}”
                </label>
              ))}
            <button className="button-orange" disabled={busy}>
              {tr("Save review")}
            </button>
            <small>
              {tr(
                "Only authorized reviewers can remove holds or confirm clearance.",
              )}
            </small>
          </form>
        </Dialog>
      )}
    </>
  );
}
function SnapshotContent({ value }: { value: unknown }) {
  const raw = value as {
    snapshot?: Workspace;
    handover?: Workspace;
    batches?: Workspace["batches"];
    version?: number;
    shift_name?: string;
  };
  const content = raw.snapshot || raw.handover || raw;
  return (
    <div className="snapshot-content">
      <p>
        {content.shift_name || tr("Handover")} {tr("· v")}
        {content.version}
      </p>
      {content.batches?.map((b) => (
        <section className="reason-row" key={b.id}>
          <h3>
            {b.id} · {b.name}
          </h3>
          <p>{statusLabel(b.status)}</p>
          {b.readiness_reasons?.map((r, i) => (
            <p key={i}>
              {systemText(r.text)}{" "}
              {r.code === "open_tasks" || r.code === "task"
                ? r.next_action
                : systemText(r.next_action || "")}{" "}
              {r.owner || tr("Unassigned")}
            </p>
          ))}
        </section>
      ))}
      {!content.batches && (
        <p>
          {tr(
            "This snapshot uses an older format. Ask your supervisor to inspect the preserved organization export.",
          )}
        </p>
      )}
    </div>
  );
}
