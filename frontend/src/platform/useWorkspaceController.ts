import { useDraftAutosave } from "./useDraftAutosave";
import { useScopedPolling } from "./useScopedPolling";
import { useWorkspacePlayback } from "./useWorkspacePlayback";
import { useCaptureState } from "./useCaptureState";
import { captureShiftProblem, NO_CURRENT_SHIFT } from "./captureShift";
import { readPortalRoute, portalUrl } from "./portalNavigation";
import {
  tr,
  useLanguage,
  setLanguage,
  adoptAccountLanguage,
  bilingual,
  systemText,
  type AnswerItem,
} from "../i18n";
import { useEffect, useRef, useState } from "react";
import { studyMark } from "../study";
import {
  call as apiCall,
  binary as apiBinary,
  setActiveShift,
  ApiError,
  type Session,
  type Organization,
} from "./client";
import type { Workspace, Note, Claim } from "../types";
import { startRecorder, requireAudibleRecording } from "../recorder";
import {
  saveDraft,
  deleteDraft,
  listDrafts,
  clearAccountDrafts,
  type CaptureDraft,
} from "./drafts";
import { type Operations } from "./OperationsSetup";
import { clearAccountAcknowledgements } from "./acknowledgementDrafts";
import {
  saveOfflineContext,
  readOfflineContext,
  clearOfflineContext,
} from "./offlineContext";
type View = Workspace & {
  organization: Organization;
  next_offset?: number | null;
  notes_total?: number;
  data_mode?: "fictional" | "real" | "unconfigured";
  capture_policy_ready?: boolean;
};
export function useWorkspaceController(orgId: string) {
  const {
    playing,
    setPlaying,
    audioPlayer,
    speechSequence,
    speechVersion,
    stopPlayback,
  } = useWorkspacePlayback();
  const {
    arming,
    setArming,
    captureReporter,
    captureContext,
    taskContext,
    setTaskContext,
    transcript,
    setTranscript,
    blob,
    setBlob,
    blobUrl,
    setBlobUrl,
    recording,
    setRecording,
    seconds,
    setSeconds,
    saved,
    setSaved,
    stage,
    setStage,
    reply,
    setReply,
    corrections,
    setCorrections,
    capture,
    stop,
  } = useCaptureState();
  const [session, setSession] = useState<Session | null>(null),
    [org, setOrg] = useState<Organization | null>(null),
    [view, setView] = useState<View | null>(null),
    [error, setError] = useState(""),
    [errorDetail, setErrorDetail] = useState(""),
    [notice, setNotice] = useState(""),
    [page, updatePage] = useState(readPortalRoute().page),
    [section, updateSection] = useState(readPortalRoute().section),
    [mobileMenu, setMobileMenu] = useState(false),
    [selected, setSelected] = useState(""),
    [busy, setBusy] = useState(false),
    [evidence, setEvidence] = useState<Note | null>(null),
    [revision, setRevision] = useState<{
      note: Note;
      text: string;
      version: number;
    } | null>(null);
  function setPage(next: string, nextSection = section, replace = false) {
    const url = portalUrl(next, nextSection);
    if (location.pathname + location.search !== url)
      history[replace ? "replaceState" : "pushState"](null, "", url);
    updatePage(next);
    updateSection(nextSection);
    setMobileMenu(false);
  }
  const routeRef = useRef({ page, section });
  routeRef.current = { page, section };
  const navigationRef = useRef<(go: () => void) => void>(() => {});
  const navigationBlocked = useRef(false),
    approvedPop = useRef(false);
  useEffect(() => {
    const back = () => {
      const target = readPortalRoute(),
        current = routeRef.current;
      if (approvedPop.current || !navigationBlocked.current) {
        approvedPop.current = false;
        setPage(target.page, target.section, true);
      } else {
        // Keep the previous entry intact when a recording/draft blocks Back.
        history.pushState(null, "", portalUrl(current.page, current.section));
        navigationRef.current(() => {
          approvedPop.current = true;
          history.back();
        });
      }
    };
    window.addEventListener("popstate", back);
    return () => window.removeEventListener("popstate", back);
  }, []);
  const base = "/organizations/" + orgId;
  const [shiftId, setShiftId] = useState("");
  const shiftRef = useRef("");
  const call = <T>(path: string, body?: unknown, method?: string) =>
    apiCall<T>(path, body, method, shiftRef.current);
  const binary = (path: string, body: unknown, method = "POST") =>
    apiBinary(path, body, method, shiftRef.current);
  const workspacePath = () =>
    base +
    "/workspace" +
    (shiftRef.current
      ? "?shift_id=" + encodeURIComponent(shiftRef.current)
      : "");
  const [operations, setOperations] = useState<Operations | null>(null);
  const [directory, setDirectory] = useState<
    {
      id: string;
      name: string;
      role: string;
    }[]
  >([]);
  const [olderNotes, setOlderNotes] = useState<Note[]>([]),
    [historyOffset, setHistoryOffset] = useState<number | null | undefined>(
      undefined,
    );
  const language = useLanguage();
  const [online, setOnline] = useState(navigator.onLine);
  const [search, setSearch] = useState(""),
    [statusFilter, setStatusFilter] = useState("all");
  const [localDrafts, setLocalDrafts] = useState<CaptureDraft[]>([]),
    [draftStatus, setDraftStatus] = useState("");
  const [navigation, setNavigation] = useState<null | {
    go: () => void;
  }>(null);

  const [personal, setPersonal] = useState(false);
  const [typing, setTyping] = useState(false);
  const [confirmSpeaker, setConfirmSpeaker] = useState(false);
  const speakerConfirmed = useRef(false);
  const [reportedById, setReportedById] = useState("");
  const [assistedWorkers, setAssistedWorkers] = useState<
    {
      id: string;
      name: string;
      work_item_ids: string[];
    }[]
  >([]);
  const reporterRef = useRef("");

  const visibleDrafts = localDrafts.filter(
    (d) => (d.reportedById || "") === reportedById,
  );
  useEffect(() => {
    reporterRef.current = reportedById;
    const cached = readOfflineContext(orgId);
    if (cached && navigator.onLine)
      saveOfflineContext({
        ...cached,
        reportedById: reportedById || undefined,
        reportedByName: assistedWorkers.find((w) => w.id === reportedById)
          ?.name,
      });
  }, [reportedById]);
  function readIdentity() {
    if (!("speechSynthesis" in window)) return;
    window.speechSynthesis.cancel();
    const name =
      assistedWorkers.find((w) => w.id === reportedById)?.name ||
      session?.user.name ||
      "";
    const speech = new SpeechSynthesisUtterance(`${name}. ${selected}.`);
    speech.lang = language === "hi" ? "hi-IN" : "en-IN";
    const voice = window.speechSynthesis
      .getVoices()
      .find((v) => v.localService && v.lang.startsWith(language));
    if (voice) {
      speech.voice = voice;
      window.speechSynthesis.speak(speech);
    } else
      setNotice(
        t(
          "इस फ़ोन पर नाम बोलकर नहीं पढ़ा जा सकता। सहायक नाम और काम पढ़कर पुष्टि करें।",
          "This phone cannot read the name aloud. Ask the helper to read and confirm the name and work.",
        ),
      );
  }
  const [snapshot, setSnapshot] = useState<unknown | null>(null);
  const [ackPending, setAckPending] = useState(false);

  const latestView = useRef<View | null>(null);

  const draftReady = useRef(false);
  const userIdRef = useRef("");
  const userNameRef = useRef("");
  const initializing = useRef(true);
  const t = bilingual;
  const reasonText = (r: { code: string; text: string }) =>
    r.code === "task" ? r.text : systemText(r.text);
  const nextText = (r: { code: string; next_action?: string }) =>
    r.code === "open_tasks" || r.code === "task"
      ? r.next_action
      : systemText(r.next_action || "");
  const ownerText = (owner?: string | null) =>
    !owner
      ? t("अभी तय नहीं", "Unassigned")
      : language === "hi"
        ? (
            {
              "Shift supervisor": "शिफ्ट सुपरवाइज़र",
              "Quality reviewer": "गुणवत्ता जाँच अधिकारी",
              "Authorized reviewer": "अधिकृत जाँच अधिकारी",
            } as Record<string, string>
          )[owner] || owner
        : owner;
  const worker = org?.role === "operator" && org?.access !== "owner";
  const isOwner = org?.access === "owner";
  const [review, setReview] = useState<Claim | null>(null),
    [answer, setAnswer] = useState<{
      answer: string;
      items: AnswerItem[];
      intent?: string;
      comparison_snapshot?: {
        version: number;
      } | null;
    } | null>(null),
    [showItem, setShowItem] = useState(false),
    [editingItem, setEditingItem] = useState(false);

  const alive = useRef(true);
  const item = view?.batches.find((b) => b.id === selected);
  useEffect(() => {
    window.scrollTo({ top: 0, behavior: "instant" });
  }, [page]);
  useEffect(() => {
    window.addEventListener("shiftproof:stop-playback", stopPlayback);
    return () =>
      window.removeEventListener("shiftproof:stop-playback", stopPlayback);
  }, []);
  function changeLanguage() {
    stopPlayback();
    const next = language === "hi" ? "en" : "hi";
    setLanguage(next);
    if (session)
      try {
        localStorage.setItem("shiftproof-language:" + session.user.id, next);
      } catch {}
  }
  const allNotes = [
    ...(view?.notes || []),
    ...olderNotes.filter(
      (n) => !view?.notes.some((current) => current.id === n.id),
    ),
  ];
  const [lastSubmission, setLastSubmission] = useState<Note | null>(null);
  function reportProgress(note: Note) {
    const current = view?.notes.find((n) => n.id === note.id) || note;
    const progress = (current as any).review_progress;
    if (current.status === "discarded")
      return t(
        "रिपोर्ट बंद है; मूल रिकॉर्ड सुरक्षित है",
        "Report closed; original evidence is retained",
      );
    if (current.status === "awaiting_upload")
      return t(
        "रिकॉर्डिंग अभी भेजी नहीं गई है",
        "Recording has not been uploaded yet",
      );
    if (current.processing_stage === "transcript_review" && !submitted(current))
      return t(
        "शब्द सहेजे गए हैं; रिपोर्ट अभी भेजनी है",
        "Transcript saved; report has not been sent yet",
      );
    if (["queued", "processing"].includes(current.status))
      return t(
        "भेज दिया गया है; रिपोर्ट तैयार हो रही है",
        "Sent; preparing the report",
      );
    if (progress?.state === "checked")
      return t("रिपोर्ट की जाँच हो गई है", "Report checked");
    if (progress?.state === "closed_without_update")
      return t(
        "काम का अपडेट नहीं माना गया; मदद के लिए सुपरवाइज़र से कहें",
        "Closed without a work update; ask the supervisor for help",
      );
    if (progress?.state === "needs_help")
      return t(
        "रिपोर्ट भेज दी गई है; समझने के लिए सुपरवाइज़र की मदद चाहिए",
        "Sent; supervisor help is needed to interpret this report",
      );
    if (progress?.checked_count > 0)
      return t(
        "कुछ बातें जाँची गई हैं; बाकी जाँच ज़रूरी है",
        "Some updates checked; specific checks remain",
      );
    return t(
      "भेज दिया गया है; सुपरवाइज़र की जाँच बाकी है",
      "Sent, awaiting supervisor review",
    );
  }
  const submitted = (n: Note) =>
    (!!n.submitted_at && n.submitted_revision === n.revision) ||
    ["processed", "manual_review"].includes(n.status);
  const hasDraft = !!(transcript || blob || saved || recording || arming);
  const selectedCaptureShift = view?.allowed_shifts?.find(s => s.id === shiftId);
  const newCaptureProblem = captureShiftProblem(selectedCaptureShift, new Date().toISOString()) ? NO_CURRENT_SHIFT : "";
  const draftCaptureProblem = !saved && (blob || transcript)
    ? captureShiftProblem(view?.allowed_shifts?.find(s => s.id === (captureContext.current?.shiftId || shiftId)), capture.current.at)
    : "";
  const draftShiftChoices = draftCaptureProblem && !saved && !reply && !taskContext && !corrections.length && !reportedById
    ? (view?.allowed_shifts || []).filter(s => s.id !== captureContext.current?.shiftId && s.capture_item_ids?.includes(selected) && !captureShiftProblem(s, capture.current.at))
    : [];

  async function moveDraftToShift(nextId: string) {
    const next = draftShiftChoices.find(s => s.id === nextId);
    if (!next || !session || recording || arming || !captureContext.current) return;
    if (!confirm(tr("Use this assigned shift for the saved recording? Its audio, text and recording time will stay unchanged. Nothing is sent until you press Send."))) return;
    // Re-read scope online before changing a local draft. The create endpoint
    // rechecks membership, dates and assignments at submission time too.
    const fresh = await apiCall<View>(base + "/workspace?shift_id=" + encodeURIComponent(nextId), undefined, undefined, nextId);
    const verified = fresh.allowed_shifts?.find(s => s.id === nextId);
    if (!verified || !verified.capture_item_ids?.includes(selected) || captureShiftProblem(verified, capture.current.at))
      throw new Error(tr("This work item is no longer assigned to you. Ask your supervisor."));
    const previousContext = captureContext.current;
    captureContext.current = { ...previousContext, shiftId: nextId };
    try { await persistDraft(); }
    catch (error) { captureContext.current = previousContext; throw error; }
    stopPlayback();
    shiftRef.current = nextId;
    setShiftId(nextId);
    setActiveShift(nextId);
    setOlderNotes([]);
    setHistoryOffset(undefined);
    setError("");
    setErrorDetail("");
    setNotice(tr("Recording kept. Check the selected shift, then press Send."));
  }

  async function persistDraft(expectedCaptureId = capture.current.id) {
    if (capture.current.id !== expectedCaptureId) return;
    if (!session || !captureContext.current || (!transcript && !blob && !saved))
      return;
    const context = captureContext.current;
    await saveDraft({
      id: capture.current.id,
      userId: session.user.id,
      organizationId: orgId,
      reportedById: captureReporter.current || undefined,
      itemId: context.itemId,
      shiftId: context.shiftId,
      recordedAt: capture.current.at,
      updatedAt: new Date().toISOString(),
      transcript,
      audio: blob,
      noteId: saved?.id,
      task: taskContext,
      corrections,
      reply,
    });
    setDraftStatus(t("इस डिवाइस पर सुरक्षित", "Saved on this device"));
    setLocalDrafts(await listDrafts(session.user.id, orgId));
  }
  function navigate(go: () => void) {
    if (ackPending) {
      setNotice(
        t(
          "पहले हैंडओवर की पुष्टि भेजें या उसकी रिकॉर्डिंग हटाएँ।",
          "Confirm or discard your handover recording before leaving.",
        ),
      );
      return;
    }
    if (recording || arming || busy) {
      setNotice(
        t(
          "पहले रिकॉर्डिंग रोकें या भेजने का काम पूरा होने दें।",
          "Finish recording or sending before changing pages.",
        ),
      );
      return;
    }
    stopPlayback();
    if (hasDraft) setNavigation({ go });
    else go();
  }
  async function signOut() {
    if (session) {
      await clearAccountDrafts(session.user.id);
      await clearAccountAcknowledgements(session.user.id);
    }
    clearOfflineContext();
    await call("/auth/logout", {});
    location.href = "/login";
  }
  async function requestSignOut() {
    if (recording || arming || ackPending) {
      setNotice(
        t("पहले रिकॉर्डिंग पूरी करें।", "Finish your recording first."),
      );
      return;
    }
    if (
      !confirm(
        t(
          "साइन आउट करने पर इस डिवाइस से इस खाते के सभी संगठनों के अधूरे ड्राफ़्ट और रिकॉर्डिंग हटेंगे। साइन आउट करें?",
          "Signing out removes this account’s unfinished recordings and drafts for every organization from this device. Sign out?",
        ),
      )
    )
      return;
    try {
      await signOut();
    } catch (e) {
      setError((e as Error).message);
    }
  }
  async function restoreDraft(d: CaptureDraft) {
    if ((d.reportedById || "") !== reporterRef.current) return;
    if (!session || d.userId !== session.user.id || d.organizationId !== orgId)
      return;
    if (d.shiftId && d.shiftId !== shiftRef.current) {
      shiftRef.current = d.shiftId;
      setShiftId(d.shiftId);
      setActiveShift(d.shiftId);
      await refresh();
    }
    if (!view?.batches.some((b) => b.id === d.itemId)) {
      setNotice(
        t(
          "ड्राफ़्ट खोलने से पहले इस काम की पहुँच जाँचें।",
          "Check that you still have access to this work item before sending.",
        ),
      );
    }
    // Older autosaves may predate the upload response and lack noteId. The
    // existing backend idempotency key lets us look up that capture read-only.
    const bytes = await crypto.subtle.digest(
      "SHA-256",
      new TextEncoder().encode(d.userId + ":" + d.id),
    );
    const lookupId =
      d.noteId ||
      "note_" +
        Array.from(new Uint8Array(bytes))
          .map((b) => b.toString(16).padStart(2, "0"))
          .join("")
          .slice(0, 24);
    let server: Note | null = null;
    try {
      if (navigator.onLine)
        server = await call<Note>(base + "/notes/" + lookupId);
    } catch (e) {
      if (!(e instanceof ApiError && e.status === 404)) {
        setError((e as Error).message);
        return;
      }
    }
    if (server) {
      if (
        (submitted(server) || server.status === "discarded") &&
        (!d.transcript || d.transcript === server.transcripts.at(-1)?.text) &&
        (!d.audio || server.has_audio)
      ) {
        await deleteDraft(d.id);
        clearCapture();
        setLastSubmission(server);
        setLocalDrafts(await listDrafts(session.user.id, orgId));
        setNotice(
          server.status === "discarded"
            ? t(
                "सुपरवाइज़र ने यह रिपोर्ट बंद कर दी है। रिकॉर्ड सुरक्षित है; इसे दोबारा नहीं भेजा जाएगा।",
                "This report has been closed. Its evidence is retained; it will not be sent again.",
              )
            : (server as any).review_progress?.can_reopen
              ? t(
                  "यह रिपोर्ट बिना काम का अपडेट माने बंद हुई थी। गलती हो तो सुपरवाइज़र इसे दोबारा खोल सकते हैं।",
                  "This report was closed without a work update. A supervisor can reopen it if that was a mistake.",
                )
              : server.processing_stage === "complete"
                ? t(
                    "इस अपडेट की जाँच हो चुकी है। सहेजा हुआ फ़ैसला विवरण में देखें।",
                    "This update has already been reviewed. Open its details for the saved decision.",
                  )
                : t(
                    "यह अपडेट पहले ही भेजा जा चुका है। सुपरवाइज़र को इसकी जाँच करनी है।",
                    "This update was already sent. It is waiting for supervisor review.",
                  ),
        );
        return;
      }
    }
    setLastSubmission(null);
    capture.current = { id: d.id, at: d.recordedAt };
    captureContext.current = { itemId: d.itemId, shiftId: d.shiftId };
    setSelected(d.itemId);
    captureReporter.current = d.reportedById || "";
    setReportedById(captureReporter.current);
    setTranscript(d.transcript);
    setBlob(d.audio);
    setReply(d.reply);
    setTaskContext(d.task || null);
    setCorrections(d.corrections);
    setPage("capture");
    setSaved(server);
    setNotice(
      t(
        "ड्राफ़्ट खुल गया। जाँचकर भेजें; अपने आप नहीं भेजा जाएगा।",
        "Draft restored. Check it and press Send; nothing is sent automatically.",
      ),
    );
  }
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
      stop.current?.().catch(() => {});
      audioPlayer.current?.pause();
      if (audioPlayer.current?.src)
        URL.revokeObjectURL(audioPlayer.current.src);
    };
  }, []);
  useEffect(() => {
    if (!blob) {
      setBlobUrl("");
      return;
    }
    const url = URL.createObjectURL(blob);
    setBlobUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [blob]);
  useEffect(() => {
    const guard = (e: BeforeUnloadEvent) => {
      if (transcript || blob || recording || busy || ackPending) {
        e.preventDefault();
      }
    };
    window.addEventListener("beforeunload", guard);
    return () => window.removeEventListener("beforeunload", guard);
  }, [transcript, blob, recording, busy, ackPending]);
  useEffect(() => {
    const changed = () => setOnline(navigator.onLine);
    window.addEventListener("online", changed);
    window.addEventListener("offline", changed);
    return () => {
      window.removeEventListener("online", changed);
      window.removeEventListener("offline", changed);
    };
  }, []);
  const autosaveCaptureId = capture.current.id;
  useDraftAutosave(
    draftReady.current && !!session && !recording && !arming,
    () => persistDraft(autosaveCaptureId),
    setDraftStatus,
    [
      autosaveCaptureId,
      transcript,
      blob,
      saved,
      reply,
      corrections,
      session,
      recording,
      arming,
      taskContext,
    ],
  );
  useScopedPolling(refresh, orgId);
  const refreshSequence = useRef(0);
  async function refresh() {
    const sequence = ++refreshSequence.current,
      requestedShift = shiftRef.current;
    const current = () =>
      alive.current &&
      sequence === refreshSequence.current &&
      requestedShift === shiftRef.current;
    try {
      const fresh = await call<Organization>(base);
      if (!current()) return;
      setOrg(fresh);
      setSession((s) =>
        s
          ? {
              ...s,
              organizations: s.organizations.map((o) =>
                o.id === fresh.id ? fresh : o,
              ),
            }
          : s,
      );
      if (fresh.profile.status === "available") {
        const v = await call<View>(workspacePath());
        if (!current()) return;
        call<{
          workers: typeof assistedWorkers;
        }>(base + "/assisted-capture")
          .then((r) => {
            if (current()) setAssistedWorkers(r.workers);
          })
          .catch(() => {
            if (current()) setAssistedWorkers([]);
          });
        latestView.current = v;
        if (
          speechVersion.current !== null &&
          speechVersion.current !== v.version
        ) {
          stopPlayback();
          setNotice(
            t(
              "नया अपडेट आया है। ताज़ा जानकारी सुनें।",
              "An update arrived. Listen to the latest update.",
            ),
          );
        }
        setView(v);
        if (v.active_shift_id) {
          shiftRef.current = v.active_shift_id;
          setShiftId(v.active_shift_id);
          setActiveShift(v.active_shift_id);
        }
        setSelected(
          (s) =>
            captureContext.current?.itemId ||
            (v.batches.some((b) => b.id === s) ? s : v.batches[0]?.id || ""),
        );
        if (v.capture_policy_ready === false) clearOfflineContext();
        if (
          v.capture_policy_ready !== false &&
          userIdRef.current &&
          v.active_shift_id
        )
          saveOfflineContext({
            userId: userIdRef.current,
            userName: userNameRef.current,
            reportedById: reporterRef.current || undefined,
            reportedByName: assistedWorkers.find(
              (w) => w.id === reporterRef.current,
            )?.name,
            organizationId: orgId,
            organizationName: fresh.name,
            activeShiftId: v.active_shift_id,
            items: v.batches.map((b) => ({ id: b.id, name: b.name })),
            shifts: v.allowed_shifts?.length
              ? v.allowed_shifts
              : [
                  {
                    id: v.active_shift_id,
                    name: v.shift_name || "Current handover",
                  },
                ],
          });
      }
      return fresh;
    } catch (error) {
      if (!current()) return;
      if (error instanceof ApiError && [401, 403, 404].includes(error.status)) {
        stopPlayback();
        clearOfflineContext();
        setOrg(null);
        setView(null);
        setOlderNotes([]);
        setError(error.message);
      }
      throw error;
    }
  }
  useEffect(() => {
    call<Session>("/auth/session")
      .then(async (s) => {
        setSession(s);
        userIdRef.current = s.user.id;
        userNameRef.current = s.user.name;
        if (readOfflineContext()?.userId !== s.user.id) clearOfflineContext();
        const o =
          (await refresh()) ||
          s.organizations.find((candidate) => candidate.id === orgId);
        if (!o || !alive.current) return;
        if (initializing.current) {
          adoptAccountLanguage(s.user.id, "hi");
          setPage(
            o.role === "operator" &&
              o.access !== "owner" &&
              !["home", "capture", "mywork", "handover"].includes(
                readPortalRoute().page,
              )
              ? "home"
              : readPortalRoute().page,
            readPortalRoute().section,
            true,
          );
          initializing.current = false;
        }
        setLocalDrafts(await listDrafts(s.user.id, orgId));
        draftReady.current = true;
        call<Operations>(base + "/operations")
          .then(setOperations)
          .catch(() => {});
        call<typeof directory>(base + "/directory")
          .then(setDirectory)
          .catch(() => {});
        return o;
      })
      .catch((e) => setError(e.message));
  }, [orgId]);
  useEffect(() => {
    if (!org) return;
    if (org.access !== "owner" && ["team", "settings", "setup"].includes(page))
      setPage(org.role === "operator" ? "home" : "overview");
    if (worker && ["overview", "reports", "work"].includes(page))
      setPage("home");
  }, [org?.access, org?.role, page]);
  async function act(fn: () => Promise<unknown>) {
    setBusy(true);
    setError("");
    setErrorDetail("");
    try {
      await fn();
      await refresh();
    } catch (e) {
      setErrorDetail((e as Error).message);
      setError(
        language === "hi"
          ? e instanceof ApiError && e.status === 401
            ? "कृपया दोबारा साइन इन करें। सहेजा ड्राफ़्ट इसी डिवाइस पर रहेगा।"
            : e instanceof ApiError && e.status === 403
              ? "इस काम के लिए सुपरवाइज़र की मदद चाहिए।"
              : tr((e as Error).message)
          : (e as Error).message,
      );
    } finally {
      setBusy(false);
    }
  }
  const captureBackup = useRef<{
    capture: {
      id: string;
      at: string;
    };
    context: {
      itemId: string;
      shiftId: string;
    } | null;
    saved: Note | null;
  } | null>(null);
  async function stopRecording() {
    if (!stop.current) return;
    const finish = stop.current;
    stop.current = null;
    try {
      const b = await finish();
      studyMark("recording_stopped", { capture_id: capture.current.id });
      if (alive.current) {
        setBlob(b);
        setTranscript("");
        setSaved(null);
      }
    } catch (e) {
      if (captureBackup.current) {
        capture.current = captureBackup.current.capture;
        captureContext.current = captureBackup.current.context;
        setSaved(captureBackup.current.saved);
      }
      if (alive.current) setError(tr((e as Error).message));
    } finally {
      if (alive.current) setRecording(false);
      captureBackup.current = null;
    }
  }
  async function record() {
    if (arming || (!recording && view?.capture_policy_ready === false)) return;
    if (!recording && captureShiftProblem(latestView.current?.allowed_shifts?.find(s => s.id === shiftRef.current), new Date().toISOString())) {
      setError(tr(NO_CURRENT_SHIFT));
      setErrorDetail("");
      return;
    }
    setError("");
    setLastSubmission(null);
    stopPlayback();
    if (!recording && reportedById && !speakerConfirmed.current) {
      setConfirmSpeaker(true);
      readIdentity();
      return;
    }
    speakerConfirmed.current = false;
    try {
      if (recording) {
        await stopRecording();
        return;
      }
      await persistDraft();
      captureBackup.current = {
        capture: { ...capture.current },
        context: captureContext.current,
        saved,
      };
      capture.current = {
        id: crypto.randomUUID(),
        at: new Date().toISOString(),
      };
      captureReporter.current = reporterRef.current;
      captureContext.current = { itemId: selected, shiftId: shiftRef.current };
      studyMark("capture_started", { capture_id: capture.current.id });
      setArming(true);
      const recordingCapture = { ...capture.current };
      const recordingContext = { ...captureContext.current };
      const recordingUser = session?.user.id;
      const recordingReporter = captureReporter.current;
      stop.current = await startRecorder(
        setSeconds,
        () => {
          void stopRecording();
        },
        (audio) => {
          if (!recordingUser) return;
          void saveDraft({
            id: recordingCapture.id,
            userId: recordingUser,
            reportedById: recordingReporter || undefined,
            organizationId: orgId,
            itemId: recordingContext.itemId,
            shiftId: recordingContext.shiftId,
            recordedAt: recordingCapture.at,
            updatedAt: new Date().toISOString(),
            transcript,
            audio,
            corrections: [...corrections],
            reply: reply ? { ...reply } : null,
            task: taskContext,
          })
            .then(() => {
              if (alive.current)
                setDraftStatus(
                  t(
                    "रिकॉर्डिंग का ड्राफ़्ट डिवाइस पर सुरक्षित हो रहा है।",
                    "Recording checkpoint saved on this device.",
                  ),
                );
            })
            .catch((error) => {
              if (alive.current) setDraftStatus(error.message);
            });
        },
      );
      if (!alive.current) {
        await stop.current();
        stop.current = null;
        return;
      }
      setRecording(true);
    } catch (e) {
      if (captureBackup.current) {
        capture.current = captureBackup.current.capture;
        captureContext.current = captureBackup.current.context;
        setSaved(captureBackup.current.saved);
        captureBackup.current = null;
      }
      setError(tr((e as Error).message));
      setRecording(false);
    } finally {
      setArming(false);
    }
  }
  async function waitNote(id: string) {
    for (let i = 0; i < 100; i++) {
      if (!alive.current) throw new Error("Workspace closed");
      const n = await call<Note>(base + "/notes/" + id);
      setStage(n.processing_stage || n.status);
      if (!["processing", "queued"].includes(n.status)) {
        studyMark(
          n.processing_stage === "transcript_review"
            ? "transcript_visible"
            : n.error
              ? "processing_failed"
              : "result_visible",
          {
            capture_id: capture.current.id,
            note_id: n.id,
            stage: n.processing_stage,
          },
        );
        return n;
      }
      await new Promise((r) => setTimeout(r, 800));
    }
    throw new Error(
      "Processing is taking longer. Your note is saved; refresh to check it.",
    );
  }
  async function ensureNote() {
    if (view?.capture_policy_ready === false)
      throw new Error(
        t(
          "पहले मालिक से डेटा सेटअप पूरा करने को कहें।",
          "Ask the organization owner to complete data setup first.",
        ),
      );
    if (!captureContext.current) {
      captureReporter.current = reporterRef.current;
      captureContext.current = { itemId: selected, shiftId: shiftRef.current };
    }
    if (!view?.batches.some((b) => b.id === captureContext.current!.itemId))
      throw new Error(
        t(
          "यह काम अब आपके लिए उपलब्ध नहीं है। सुपरवाइज़र से संपर्क करें।",
          "This work item is no longer assigned to you. Ask your supervisor.",
        ),
      );
    if (saved) {
      const latest = await call<Note>(base + "/notes/" + saved.id);
      setSaved(latest);
      if (latest.task_context) setTaskContext(latest.task_context);
      return latest;
    }
    const shiftProblem = captureShiftProblem(view?.allowed_shifts?.find(s => s.id === captureContext.current!.shiftId), capture.current.at);
    if (shiftProblem) throw new Error(tr(shiftProblem));
    const result = await call<{
      note: Note;
    }>(base + "/notes", {
      batch_id: captureContext.current.itemId,
      shift_id: captureContext.current.shiftId || undefined,
      reported_by_id: captureReporter.current || undefined,
      recorded_at: capture.current.at,
      idempotency_key: capture.current.id,
      supersedes: corrections,
      task_id: taskContext?.id || undefined,
      ...(reply
        ? {
            clarification_ref: reply.id,
            clarification_version: reply.version,
            clarification_context: reply,
          }
        : {}),
    });
    setSaved(result.note);
    return result.note;
  }
  async function sendRecording() {
    await act(async () => {
      if (!blob) return;
      await requireAudibleRecording(blob);
      const n = await ensureNote();
      if (!n.has_audio)
        await binary(base + "/notes/" + n.id + "/audio", blob, "PUT");
      await call(base + "/notes/" + n.id + "/process", {});
      await deleteDraft(capture.current.id);
      clearCapture();
      setLastSubmission({
        ...n,
        status: "queued",
        submitted_at: new Date().toISOString(),
      });
      setNotice(
        t(
          "आपकी रिपोर्ट भेज दी गई है। सुपरवाइज़र जाँच करेंगे।",
          "Your report was sent. Your supervisor will check it.",
        ),
      );
    });
  }
  async function uploadVoice() {
    await act(async () => {
      if (!blob) return;
      await requireAudibleRecording(blob);
      studyMark("upload_submitted", { capture_id: capture.current.id });
      setStage("Uploading");
      const n = await ensureNote();
      if (n.status === "awaiting_upload")
        await binary(base + "/notes/" + n.id + "/audio", blob, "PUT");
      setStage("Prisma transcription");
      await call(base + "/notes/" + n.id + "/process", {
        transcribe_only: true,
      });
      const finished = await waitNote(n.id);
      setSaved(finished);
      if (finished.transcripts.length) {
        setTranscript(finished.transcripts.at(-1)!.text);
        setNotice(
          t(
            "आपके शब्द सहेजे गए हैं। जाँचकर ‘अपडेट भेजें’ दबाएँ।",
            "Your transcript is saved. Check it, then press Send update.",
          ),
        );
      } else
        throw new Error(
          finished.error || "Transcription failed. Recording retained.",
        );
    });
  }
  async function extract() {
    await act(async () => {
      const n = await ensureNote();
      const current = n.transcripts.at(-1)?.text;
      if (!current)
        await call(base + "/notes/" + n.id + "/transcript", { transcript });
      else if (current !== transcript) {
        const latest = await call<View>(workspacePath());
        await call(base + "/notes/" + n.id + "/revisions", {
          transcript,
          expected_version: latest.version,
        });
      }
      studyMark("extraction_submitted", {
        capture_id: capture.current.id,
        note_id: n.id,
      });
      setStage("Claim extraction");
      await call(base + "/notes/" + n.id + "/process", {});
      // HTTP 202 means the server owns this submitted report, including failed
      // extraction. Do not keep prompting to discard it as an unsent draft.
      await deleteDraft(capture.current.id);
      clearCapture();
      setLastSubmission({
        ...n,
        submitted_at: new Date().toISOString(),
        status: "queued",
      });
      try {
        const result = await waitNote(n.id);
        setLastSubmission(result);
        setNotice(
          result.error
            ? t(
                "अपडेट भेज दिया गया है। सुपरवाइज़र सहेजे हुए जवाब की जाँच करेंगे; दोबारा भेजने की ज़रूरत नहीं है।",
                "Update sent. Your supervisor will review the saved answer; you do not need to send it again.",
              )
            : t(
                "अपडेट भेज दिया गया। सुपरवाइज़र इसकी जाँच करेंगे।",
                "Update sent. Your supervisor will review it.",
              ),
        );
      } catch {
        setNotice(
          t(
            "अपडेट भेज दिया गया है और सर्वर पर तैयार हो रहा है। दोबारा न भेजें।",
            "Update sent and still processing on the server. Do not send it again.",
          ),
        );
      }
      setStage("");
      setDraftStatus("");
    });
  }
  function clearCapture() {
    void deleteDraft(capture.current.id).then(
      () => session && listDrafts(session.user.id, orgId).then(setLocalDrafts),
    );
    captureContext.current = null;
    capture.current = { id: crypto.randomUUID(), at: new Date().toISOString() };
    setSaved(null);
    setBlob(null);
    setTranscript("");
    setReply(null);
    setCorrections([]);
    setStage("");
    setTaskContext(null);
    setDraftStatus("");
    setTyping(false);
  }
  async function playback(
    kind: "clarification" | "handover",
    batchId = selected,
  ) {
    if (playing) {
      stopPlayback();
      return;
    }
    await act(async () => {
      await refresh();
      const current = latestView.current;
      if (!current) return;
      const sequence = ++speechSequence.current,
        requestedShift = shiftRef.current;
      speechVersion.current = current.version;
      const audio = await binary(base + "/speech", {
        batch_id: batchId,
        kind,
        language,
        expected_version: current.version,
      });
      if (
        !alive.current ||
        sequence !== speechSequence.current ||
        requestedShift !== shiftRef.current ||
        latestView.current?.version !== current.version
      )
        return;
      const url = URL.createObjectURL(audio);
      document
        .querySelectorAll(".organization-app audio")
        .forEach((a) => (a as HTMLAudioElement).pause());
      const player = new Audio(url);
      audioPlayer.current = player;
      player.onended = stopPlayback;
      player.onerror = () => {
        stopPlayback();
        setError(
          t(
            "आवाज़ नहीं चल सकी। लिखे हुए अपडेट पढ़ें या दोबारा कोशिश करें।",
            "Playback failed. Read the displayed update or try again.",
          ),
        );
      };
      try {
        await player.play();
        setPlaying(true);
      } catch (e) {
        URL.revokeObjectURL(url);
        throw e;
      }
    });
  }
  const [reportReview, setReportReview] = useState<
    | (Note & {
        claims?: Claim[];
      })
    | null
  >(null);
  function openReport(id: string) {
    if (recording || arming) return;
    setError("");
    const requestedShift = shiftRef.current;
    void call<
      Note & {
        claims?: Claim[];
      }
    >(base + "/notes/" + id)
      .then((note) => {
        if (alive.current && shiftRef.current === requestedShift)
          setReportReview(note);
      })
      .catch((e) => {
        if (alive.current && shiftRef.current === requestedShift)
          setError(e.message);
      });
  }
  function source(id: string) {
    const existing = allNotes.find((n) => n.id === id);
    if (existing) setEvidence(existing);
    else {
      const requestedShift = shiftRef.current;
      call<Note>(base + "/notes/" + id)
        .then((note) => {
          if (alive.current && requestedShift === shiftRef.current)
            setEvidence(note);
        })
        .catch((e) => {
          if (alive.current && requestedShift === shiftRef.current)
            setError(e.message);
        });
    }
  }
  let setupPending = true;
  try {
    setupPending = !JSON.parse(
      localStorage.getItem(
        `shiftproof.setup.v1:${session?.user.id}:${orgId}`,
      ) || "{}",
    ).done;
  } catch {
    /* Server resources still remain available. */
  }
  const reviewer =
    org?.capabilities?.review_reports ?? org?.role !== "operator";
  const canManageWork =
    org?.capabilities?.manage_work ??
    (org?.role === "supervisor" ||
      (org?.access === "owner" && org?.role === "quality"));
  const admin = org?.access !== "member";
  const currentClaims = (n: Note) =>
    view?.batches
      .flatMap((b) => b.claim_history || [])
      .some(
        (c) =>
          c.note_id === n.id &&
          c.transcript_revision === n.transcripts.at(-1)?.revision,
      );
  navigationRef.current = navigate;
  navigationBlocked.current =
    hasDraft || busy || recording || arming || ackPending;
  return {
    call,
    binary,
    orgId,
    session,
    setSession,
    org,
    setOrg,
    view,
    setView,
    error,
    setError,
    errorDetail,
    setErrorDetail,
    notice,
    setNotice,
    page,
    updatePage,
    section,
    updateSection,
    mobileMenu,
    setMobileMenu,
    selected,
    setSelected,
    busy,
    setBusy,
    evidence,
    setEvidence,
    revision,
    setRevision,
    setPage,
    routeRef,
    navigationRef,
    navigationBlocked,
    approvedPop,
    base,
    shiftId,
    setShiftId,
    shiftRef,
    workspacePath,
    operations,
    setOperations,
    directory,
    setDirectory,
    olderNotes,
    setOlderNotes,
    historyOffset,
    setHistoryOffset,
    language,
    online,
    setOnline,
    search,
    setSearch,
    statusFilter,
    setStatusFilter,
    localDrafts,
    setLocalDrafts,
    draftStatus,
    setDraftStatus,
    navigation,
    setNavigation,
    arming,
    setArming,
    playing,
    setPlaying,
    personal,
    setPersonal,
    typing,
    setTyping,
    confirmSpeaker,
    setConfirmSpeaker,
    speakerConfirmed,
    reportedById,
    setReportedById,
    assistedWorkers,
    setAssistedWorkers,
    reporterRef,
    captureReporter,
    visibleDrafts,
    readIdentity,
    snapshot,
    setSnapshot,
    ackPending,
    setAckPending,
    audioPlayer,
    speechSequence,
    speechVersion,
    latestView,
    captureContext,
    draftReady,
    userIdRef,
    userNameRef,
    initializing,
    t,
    reasonText,
    nextText,
    ownerText,
    worker,
    isOwner,
    taskContext,
    setTaskContext,
    transcript,
    setTranscript,
    blob,
    setBlob,
    blobUrl,
    setBlobUrl,
    recording,
    setRecording,
    seconds,
    setSeconds,
    saved,
    setSaved,
    stage,
    setStage,
    reply,
    setReply,
    corrections,
    setCorrections,
    review,
    setReview,
    answer,
    setAnswer,
    showItem,
    setShowItem,
    editingItem,
    setEditingItem,
    capture,
    stop,
    alive,
    item,
    changeLanguage,
    allNotes,
    lastSubmission,
    setLastSubmission,
    reportProgress,
    submitted,
    hasDraft,
    newCaptureProblem,
    draftCaptureProblem,
    draftShiftChoices,
    moveDraftToShift,
    stopPlayback,
    persistDraft,
    navigate,
    signOut,
    requestSignOut,
    restoreDraft,
    refreshSequence,
    refresh,
    act,
    captureBackup,
    stopRecording,
    record,
    waitNote,
    ensureNote,
    sendRecording,
    uploadVoice,
    extract,
    clearCapture,
    playback,
    reportReview,
    setReportReview,
    openReport,
    source,
    setupPending,
    reviewer,
    canManageWork,
    admin,
    currentClaims,
  };
}
export type WorkspaceController = ReturnType<typeof useWorkspaceController>;
