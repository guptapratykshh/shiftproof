import { Select } from "../components/Select";
import { statusLabel } from "./workspaceLabels";
import { AppearanceControl } from "../theme";
import WorkerHomePage from "./WorkerHomePage";
import OverviewPage from "./OverviewPage";
import ReportsPage from "./ReportsPage";
import SetupWizard from "./SetupWizard";
import Team from "./TeamPage";
import Settings from "./SettingsPage";
import { PageHeader } from "../components/OperationalUI";
import { roleLabel, accessLabel } from "./workspaceLabels";
import { tr, locale } from "../i18n";
import {
  Home,
  FileText,
  ListChecks,
  Mic,
  ShieldCheck,
  LogOut,
  RefreshCw,
  ClipboardCheck,
  LayoutDashboard,
  Users,
  Settings as SettingsIcon,
  WifiOff,
  Languages,
} from "lucide-react";
import { Brand } from "./Landing";
import { setActiveShift, type Industry } from "./client";
import { deleteDraft, listDrafts } from "./drafts";
import HandoverPage from "./HandoverPage";
import { downloadRecoveryFile } from "./recoveryFiles";
import {
  OperationalSidebar,
  SidebarNavButton,
} from "../components/OperationalShell";
import {
  useWorkspaceController,
  type WorkspaceController,
} from "./useWorkspaceController";
import { WorkspaceContext } from "./WorkspaceContext";
import WorkRegisterPage from "./WorkRegisterPage";
import CapturePage from "./CapturePage";
import MyWorkPage from "./MyWorkPage";
import WorkspaceDialogs from "./WorkspaceDialogs";
export default function OrganizationWorkspace({
  orgId,
}: {
  orgId: string;
  industries: Industry[];
}) {
  const state = useWorkspaceController(orgId);
  return (
    <WorkspaceContext.Provider value={state}>
      <WorkspaceShell state={state} />
    </WorkspaceContext.Provider>
  );
}
function WorkspaceShell({ state }: { state: WorkspaceController }) {
  const {
    orgId,
    session,
    org,
    view,
    error,
    setError,
    errorDetail,
    notice,
    setNotice,
    page,
    section,
    mobileMenu,
    setMobileMenu,
    busy,
    setPage,
    base,
    shiftId,
    setShiftId,
    shiftRef,
    setOlderNotes,
    setHistoryOffset,
    language,
    online,
    setLocalDrafts,
    arming,
    playing,
    setPlaying,
    setPersonal,
    visibleDrafts,
    setSnapshot,
    setAckPending,
    audioPlayer,
    speechSequence,
    speechVersion,
    captureContext,
    t,
    reasonText,
    nextText,
    ownerText,
    worker,
    isOwner,
    recording,
    changeLanguage,
    stopPlayback,
    navigate,
    requestSignOut,
    restoreDraft,
    refresh,
    act,
    clearCapture,
    playback,
    openReport,
    source,
    setupPending,
    reviewer,
  } = state;
  if (!org)
    return (
      <div className="platform-loading">
        <Brand />
        {error ? (
          <>
            <p role="alert">{tr(error)}</p>
            {!online && (
              <p>
                {tr(
                  "इंटरनेट आने पर कार्यस्थल खुलेगा। सहेजे गए ड्राफ़्ट इस डिवाइस पर सुरक्षित हैं। Connect to open your workspace; saved drafts stay on this device.",
                )}
              </p>
            )}
            <a href="/login">{tr("Sign in")}</a>
            <a href="/organizations">{tr("Choose another organization")}</a>
            <button
              className="button-outline"
              onClick={() => location.reload()}
            >
              {tr("Try again · फिर कोशिश करें")}
            </button>
          </>
        ) : (
          <p>{tr("Opening your private workspace…")}</p>
        )}
      </div>
    );
  return (
    <div
      className={
        "organization-app " +
        (worker ? "worker-workspace" : "reviewer-workspace")
      }
      lang={language}
      onPlayCapture={(event) => {
        speechSequence.current += 1;
        speechVersion.current = null;
        if ("speechSynthesis" in window) window.speechSynthesis.cancel();
        audioPlayer.current?.pause();
        if (audioPlayer.current?.src)
          URL.revokeObjectURL(audioPlayer.current.src);
        audioPlayer.current = null;
        setPlaying(false);
        document.querySelectorAll(".organization-app audio").forEach((a) => {
          if (a !== event.target) (a as HTMLAudioElement).pause();
        });
      }}
    >
      <OperationalSidebar
        className={"organization-sidebar" + (mobileMenu ? " menu-open" : "")}
      >
        <Brand />
        {(session?.organizations.length ?? 0) > 1 ? (
          <label className="org-switch">
            {t("संगठन", "Organization")}
            <Select
              aria-label={tr("Switch organization")}
              value={orgId}
              disabled={busy || recording || arming}
              onChange={(e) => {
                const destination = e.target.value;
                navigate(() => {
                  setActiveShift(null);
                  location.href = "/app/" + destination;
                });
              }}
            >
              {session?.organizations.map((o) => (
                <option value={o.id} key={o.id}>
                  {o.name}
                </option>
              ))}
            </Select>
          </label>
        ) : (
          <div className="org-switch current-organization">
            <span>{t("मेरा कार्यस्थल", "Your workspace")}</span>
            <strong title={org.name}>{org.name}</strong>
          </div>
        )}
        <small>
          {tr(org.profile.name)} ·{" "}
          {org.profile.status === "preview"
            ? tr("Preview")
            : tr("Private workspace")}
        </small>
        <button
          className="mobile-menu-toggle button-outline"
          aria-expanded={mobileMenu}
          onClick={() => setMobileMenu(!mobileMenu)}
        >
          {tr("Menu")}
        </button>
        <nav aria-label={t("मुख्य विकल्प", "Main navigation")}>
          {[
            ...(worker
              ? ["home", "mywork", "handover"]
              : ["overview", "work", "reports", "handover"]),
            ...(isOwner ? ["team", "settings"] : []),
          ].map((p) => (
            <SidebarNavButton
              disabled={
                busy ||
                (org.profile.status === "preview" &&
                  ["capture", "handover"].includes(p))
              }
              key={p}
              onClick={() => navigate(() => setPage(p))}
              aria-current={
                page === p || (worker && p === "home" && page === "capture")
                  ? "page"
                  : undefined
              }
              className={
                page === p || (worker && p === "home" && page === "capture")
                  ? "active"
                  : ""
              }
            >
              {p === "home" ? (
                <Home size={18} />
              ) : p === "work" || p === "mywork" ? (
                <ListChecks size={18} />
              ) : p === "reports" ? (
                <FileText size={18} />
              ) : p === "capture" ? (
                <Mic size={18} />
              ) : p === "team" ? (
                <Users size={18} />
              ) : p === "settings" ? (
                <SettingsIcon size={18} />
              ) : p === "handover" ? (
                <ClipboardCheck size={18} />
              ) : (
                <LayoutDashboard size={18} />
              )}
              {language === "hi"
                ? {
                    home: "होम",
                    work: "काम",
                    reports: "रिपोर्टें और सबूत",
                    capture: "अपडेट बोलें",
                    mywork: "मेरा काम",
                    handover: "हैंडओवर",
                    overview: "काम की स्थिति",
                    team: "टीम",
                    settings: "सेटिंग्स",
                  }[p]
                : p === "home"
                  ? "Home"
                  : p === "work"
                    ? "Work items"
                    : p === "reports"
                      ? "Reports & evidence"
                      : p === "mywork"
                        ? tr("My work")
                        : p === "capture"
                          ? tr("Voice & reports")
                          : p === "team"
                            ? tr("Team")
                            : p[0].toUpperCase() + p.slice(1)}
            </SidebarNavButton>
          ))}
        </nav>
        <div className="organization-person">
          <ShieldCheck size={20} />
          <strong>{session?.user.name}</strong>
          <small>
            {accessLabel(org.access)} · {roleLabel(org.role)}
          </small>
          <button onClick={() => void requestSignOut()}>
            <LogOut size={14} />
            {tr("Sign out")}
          </button>
        </div>
      </OperationalSidebar>
      <main className="organization-main">
        <div className="workspace-topbar">
          <span>
            {org.name} <span aria-hidden="true">/</span>{" "}
            {t("कार्यस्थल", "Workspace")}
          </span>
          <div>
            <button className="text-button" onClick={changeLanguage}>
              <Languages size={16} />
              {language === "hi" ? "English" : "हिन्दी"}
            </button>
            <AppearanceControl />
            {(!worker || page !== "home") && (
              <button
                className="text-button"
                aria-label={t("अपडेट रिकॉर्ड करें", "Record update")}
                onClick={() => navigate(() => setPage("capture"))}
                disabled={org.profile.status === "preview"}
              >
                <Mic size={19} />
              </button>
            )}
            <button
              className="person-menu-button"
              onClick={() => setPersonal(true)}
              aria-label={t("मेरा खाता", "My account")}
            >
              {session?.user.name
                .split(" ")
                .map((n) => n[0])
                .slice(0, 2)
                .join("")}
            </button>
          </div>
        </div>
        <PageHeader
          title={tr(
            (
              {
                home: "Your shift",
                work: "Work items",
                reports: "Reports & evidence",
                overview: "Shift overview",
                capture: "Record update",
                mywork: "My work",
                handover: "Shift handover",
                team: "Team",
                settings: "Organization settings",
                setup: "Set up your workspace",
              } as Record<string, string>
            )[page] || "Workspace",
          )}
          description={tr(
            (
              {
                home: "Speak, listen and send your update.",
                work: "Find a work item and see its latest status.",
                reports:
                  "Listen to reports, check updates and open their evidence.",
                overview: "See what needs attention before the next shift.",
                capture:
                  "Choose your work, record an update, then check and send.",
                mywork: "Your assigned tasks and the next step for each.",
                handover:
                  "Check outstanding work, then confirm what you received.",
                team: "Add people and give each person the right responsibility.",
                settings:
                  "Manage your workplace, shifts and recording preferences.",
                setup: "A few short steps to get your team ready.",
              } as Record<string, string>
            )[page] || "Workspace",
          )}
          eyebrow={<span className="eyebrow">{tr(org.profile.name)}</span>}
          actions={
            <button
              className="button-outline"
              onClick={() => act(async () => {})}
              disabled={busy}
            >
              <RefreshCw size={15} />
              {tr("Refresh")}
            </button>
          }
        />
        <div className="workspace-context">
          {!!view?.allowed_shifts?.length && (
            <label>
              {t("शिफ्ट", "Shift")}
              <Select
                aria-label={tr("Choose shift")}
                value={shiftId}
                disabled={busy || recording || arming}
                onChange={(e) => {
                  const next = e.target.value;
                  navigate(() => {
                    captureContext.current = null;
                    shiftRef.current = next;
                    setShiftId(next);
                    setActiveShift(next);
                    setOlderNotes([]);
                    setHistoryOffset(undefined);
                    clearCapture();
                    void act(refresh);
                  });
                }}
              >
                {view.allowed_shifts.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                    {s.starts_at
                      ? " · " +
                        new Date(s.starts_at).toLocaleDateString(locale(), {
                          timeZone: org.timezone,
                        })
                      : ""}
                  </option>
                ))}
              </Select>
            </label>
          )}
          {!online && (
            <span role="status">
              <>
                <WifiOff size={15} />
                {t(
                  "ऑफ़लाइन · ड्राफ़्ट डिवाइस पर रहेगा",
                  "Offline · drafts stay on this device",
                )}
              </>
            </span>
          )}
        </div>
        {view?.data_mode !== "real" && view?.capture_policy_ready === false && (
          <div className="preview-notice" role="status">
            {t(
              "रिकॉर्डिंग शुरू करने से पहले मालिक से डेटा सेटअप पूरा करने को कहें।",
              "Ask the organization owner to choose a data policy in Settings before recording.",
            )}
          </div>
        )}
        {!!visibleDrafts.length && (
          <details className="draft-drawer">
            <summary>
              {t("सहेजे गए ड्राफ़्ट", "Saved drafts")} ({visibleDrafts.length})
              · {t("अपने आप नहीं भेजे जाते", "Never sent automatically")}
            </summary>
            {visibleDrafts.map((d) => (
              <div key={d.id}>
                <span>
                  {d.itemId} ·{" "}
                  {new Date(d.recordedAt).toLocaleString(
                    language === "hi" ? "hi-IN" : undefined,
                    { timeZone: org.timezone },
                  )}{" "}
                  {d.audio ? "🎙" : ""}
                </span>
                <button
                  className="text-button"
                  disabled={busy || recording}
                  onClick={() => navigate(() => void restoreDraft(d))}
                >
                  {t("खोलें", "Open draft")}
                </button>
                <button
                  className="text-button"
                  disabled={busy || recording}
                  onClick={() =>
                    void downloadRecoveryFile(d).catch((e) =>
                      setError(e.message),
                    )
                  }
                >
                  {t("सुपरवाइज़र के लिए फ़ाइल", "Download recovery file")}
                </button>
                <button
                  className="text-button"
                  disabled={busy || recording}
                  onClick={() => {
                    if (
                      confirm(
                        t("यह ड्राफ़्ट हटाएँ?", "Discard this local draft?"),
                      )
                    )
                      void deleteDraft(d.id).then(
                        () =>
                          session &&
                          listDrafts(session.user.id, orgId).then(
                            setLocalDrafts,
                          ),
                      );
                  }}
                >
                  {t("हटाएँ", "Discard")}
                </button>
              </div>
            ))}
          </details>
        )}
        {error && (
          <div className="platform-error" role="alert">
            {tr(error)}
            {worker && errorDetail && tr(errorDetail) !== tr(error) && (
              <details>
                <summary>
                  {t("सहायता के लिए विवरण", "Details for support")}
                </summary>
                {tr(errorDetail)}
              </details>
            )}
            <button
              aria-label={tr("Dismiss error")}
              onClick={() => setError("")}
            >
              ×
            </button>
          </div>
        )}
        {notice && (
          <div className="platform-notice" role="status">
            {tr(notice)}
            <button
              aria-label={tr("Dismiss notification")}
              onClick={() => setNotice("")}
            >
              ×
            </button>
          </div>
        )}
        {isOwner &&
          setupPending &&
          page === "overview" &&
          org.profile.status === "available" && (
            <button
              className="setup-resume text-button"
              onClick={() => navigate(() => setPage("setup"))}
            >
              {tr("Continue setup")}
            </button>
          )}
        {page === "setup" && isOwner ? (
          <SetupWizard
            org={org}
            userId={session?.user.id || ""}
            refresh={refresh}
            finish={() => setPage("overview")}
            openTeam={() => setPage("team")}
          />
        ) : page === "settings" && isOwner ? (
          <Settings
            org={org}
            section={section}
            onSection={(next) => navigate(() => setPage("settings", next))}
            refresh={refresh}
            act={act}
            busy={busy}
          />
        ) : page === "team" && isOwner ? (
          <Team
            org={org}
            currentUser={session?.user.id || ""}
            act={act}
            busy={busy}
          />
        ) : org.profile.status === "preview" ? (
          <section className="platform-panel preview-panel">
            <span className="eyebrow">{tr("WORKFLOW PREVIEW")}</span>
            <h2>
              {tr(org.profile.name)} {tr("is on the roadmap.")}
            </h2>
            <p>
              {tr(
                "Your organization and memberships are real. Operational capture for this industry is not enabled yet. Manufacturing, maintenance and warehousing have working workflows.",
              )}
            </p>
            <button className="button-dark" onClick={() => setPage("settings")}>
              {tr("Set up your organization")}
            </button>
            <button className="button-outline" onClick={() => setPage("team")}>
              {tr("Invite your team")}
            </button>
          </section>
        ) : !view ? (
          <p>{tr("Loading reports…")}</p>
        ) : (
          <>
            {page === "home" && <WorkerHomePage />}
            {page === "overview" && <OverviewPage />}
            {page === "work" && !worker && <WorkRegisterPage />}
            {page === "reports" && !worker && <ReportsPage />}
            {page === "capture" && <CapturePage />}
            {page === "mywork" && <MyWorkPage />}
            {page === "handover" && (
              <HandoverPage
                view={view}
                worker={worker}
                busy={busy}
                playing={playing}
                language={language}
                userId={session?.user.id || ""}
                shiftId={shiftId}
                base={base}
                playback={playback}
                statusLabel={statusLabel}
                reasonText={reasonText}
                nextText={nextText}
                ownerText={ownerText}
                source={source}
                openReport={openReport}
                canReview={reviewer}
                act={act}
                setNotice={setNotice}
                setSnapshot={setSnapshot}
                refresh={refresh}
                stopPlayback={stopPlayback}
                setAckPending={setAckPending}
              />
            )}
          </>
        )}
      </main>
      <WorkspaceDialogs state={state} />
    </div>
  );
}
