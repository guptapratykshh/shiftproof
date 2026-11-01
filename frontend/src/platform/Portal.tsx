import { Select } from "../components/Select";
import { AppearanceControl } from "../theme";
import { tr, useLanguage, LanguageButton, msg } from "../i18n";
import { lazy, useEffect, useState, type FormEvent } from "react";
import { ShieldCheck, } from "lucide-react";
import Landing, { Brand } from "./Landing";
import PasswordFields from "./PasswordFields";
const OrganizationWorkspace = lazy(() => import("./Workspace"));
import WorkerAccount from "./WorkerAccount";
import SignInChoice, { signInOptions } from "./SignInChoice";
import OrganizationHome from "./OrganizationHome";
import OfflineCapture from "./OfflineCapture";
import { readOfflineContext, clearOfflineContext } from "./offlineContext";
import { call, type Industry, type Session } from "./client";
import "./platform.css";
import "./workspace.css";

export default function Portal() {
  useLanguage();
  const path = window.location.pathname;
  const [offlineContext] = useState(() =>
    !navigator.onLine
      ? readOfflineContext(
          path.startsWith("/app/") ? path.split("/")[2] : undefined,
        )
      : null,
  );
  const [industries, setIndustries] = useState<Industry[]>([]);
  const [error, setError] = useState("");
  useEffect(() => {
    call<Industry[]>("/industries")
      .then(setIndustries)
      .catch((e) => setError(e.message));
  }, []);
  // Retire old shared links without exposing a fictional workspace.
  if (path === "/demo" || path.startsWith("/demo/")) {
    window.location.replace("/login");
    return null;
  }
  if (offlineContext && (path.startsWith("/app/") || path === "/organizations"))
    return <OfflineCapture context={offlineContext} />;
  if (path === "/signin") return <SignInChoice />;
  if (path === "/worker/login") return <WorkerAccount />;
  if (path.startsWith("/worker/activate/"))
    return <WorkerAccount token={path.split("/")[3]} />;
  if (path.startsWith("/worker/reset/"))
    return <WorkerAccount token={path.split("/")[3]} reset />;
  if (path === "/organizations")
    return <OrganizationHome industries={industries} />;
  if (path.startsWith("/app/"))
    return (
      <OrganizationWorkspace
        orgId={path.split("/")[2]}
        industries={industries}
      />
    );
  if (
    ["/login", "/signup", "/recover"].includes(path) ||
    path.startsWith("/join/")
  )
    return <AccountScreen industries={industries} path={path} />;
  if (error)
    return (
      <div className="public-site">
        <Brand />
        <LanguageButton />
        <AppearanceControl />
        <div className="account-card">
          <h1>{tr("ShiftProof is starting up.")}</h1>
          <p role="alert">{tr(error)}</p>
          <button onClick={() => location.reload()}>{tr("Try again")}</button>
        </div>
      </div>
    );
  return <Landing industries={industries} />;
}
function AccountScreen({
  industries,
  path,
}: {
  industries: Industry[];
  path: string;
}) {
  const token = path.startsWith("/join/")
    ? path.split("/")[2]
    : new URLSearchParams(location.search).get("invite");
  const signup = path === "/signup" || path.startsWith("/join/");
  const recover = path === "/recover";
  const selectedOption = signInOptions.find(option => option.id === new URLSearchParams(location.search).get("role"));
  const roleQuery = selectedOption ? "?role=" + selectedOption.id : "";
  const [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [invite, setInvite] = useState<{
      organization_name: string;
      name?: string;
      role: string;
      kind?: string;
    } | null>(null),
    [session, setSession] = useState<Session | null>(null),
    [codes, setCodes] = useState<string[]>([]),
    [destination, setDestination] = useState(""),
    [industry, setIndustry] = useState("manufacturing"),
    [recovered, setRecovered] = useState(false);
  const [pilotApproval, setPilotApproval] = useState(false);
  useEffect(() => {
    call<{ pilot_approval_required: boolean }>("/auth/options")
      .then((options) => setPilotApproval(options.pilot_approval_required))
      .catch(() => {});
  }, []);
  useEffect(() => {
    if (token) {
      call<{ organization_name: string; name?: string; role: string }>(
        "/invitations/" + token,
      )
        .then(setInvite)
        .catch((e) => setError(e.message));
      call<Session>("/auth/session")
        .then(setSession)
        .catch(() => {});
    }
  }, [token]);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const data = Object.fromEntries(new FormData(event.currentTarget));
    try {
      if ((signup || recover) && data.password !== data.confirm_password)
        throw new Error("Passwords do not match.");
      if (recover) {
        delete data.confirm_password;
        await call("/auth/recover", data);
        setRecovered(true);
      } else if (signup) {
        const result = await call<{
          recovery_codes: string[];
          organization_id: string;
        }>("/auth/signup", {
          ...data,
          ...(token
            ? { invitation_token: token }
            : {
                industry,
                timezone:
                  Intl.DateTimeFormat().resolvedOptions().timeZone ||
                  "Asia/Kolkata",
              }),
        });
        setCodes(result.recovery_codes);
        clearOfflineContext();
        setDestination(
          "/app/" + result.organization_id + (token ? "" : "?view=setup"),
        );
      } else {
        await call("/auth/login", data);
        const s = await call<Session>("/auth/session");
        clearOfflineContext();
        // The card is a destination preference, never a source of permissions.
        const preferredOrganization = s.organizations.find(org =>
          selectedOption?.id === "organization" ? ["owner", "admin"].includes(org.access)
          : selectedOption?.id === "supervisor" ? ["supervisor", "quality"].includes(org.role)
          : selectedOption?.id === "worker" ? org.role === "operator" : true
        ) || s.organizations[0];
        location.href = token
          ? "/join/" + token
          : preferredOrganization
            ? "/app/" + preferredOrganization.id
            : "/organizations";
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function accept() {
    setBusy(true);
    try {
      const r = await call<{ organization_id: string }>("/invitations/accept", {
        token,
      });
      location.href = "/app/" + r.organization_id;
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  }
  if (invite?.kind === "employee" && token)
    return <WorkerAccount token={token} />;
  return (
    <div className="account-page">
      <div className="account-story">
        <Brand />
        <div>
          <span className="eyebrow">{tr("KEEP THE NEXT SHIFT INFORMED")}</span>
          <h1>
            {tr("The context")}
            <br />
            {tr("belongs with")}
            <br />
            <em>{tr("the work.")}</em>
          </h1>
          <p>
            {tr("A private workspace for your organization.")}
            <br />
            {tr("A clear next step for every handover.")}
          </p>
          <div className="account-proof">
            <ShieldCheck />
            <span>
              {tr(
                "Original reports stay linked to their sources. Your team controls the review.",
              )}
            </span>
          </div>
        </div>
        <a href="/">
          
          {tr("Back to ShiftProof")}
        </a>
      </div>
      <main className="account-main">
        <div className="account-language">
          <LanguageButton />
          <AppearanceControl />
        </div>
        <div className="account-card">
          {codes.length ? (
            <>
              <span className="eyebrow">{tr("ACCOUNT CREATED")}</span>
              <h1>{tr("Keep your recovery codes.")}</h1>
              <p>
                {tr(
                  "These five codes are shown once. Each can reset your password once. Store them privately; email recovery is not enabled.",
                )}
              </p>
              <div className="recovery-codes">
                {codes.map((c) => (
                  <code key={c}>{c}</code>
                ))}
              </div>
              <button
                className="button-outline"
                onClick={() => {
                  const a = document.createElement("a");
                  a.href = URL.createObjectURL(
                    new Blob([codes.join("\n")], { type: "text/plain" }),
                  );
                  a.download = "shiftproof-recovery-codes.txt";
                  a.click();
                  URL.revokeObjectURL(a.href);
                }}
              >
                {tr("Download recovery codes")}
              </button>
              <a className="button-orange" href={destination}>
                {tr("I’ve saved my codes · Open workspace")}
                
              </a>
            </>
          ) : recovered ? (
            <>
              <h1>{tr("Password reset.")}</h1>
              <p>
                {tr(
                  "Previous sessions have been signed out. Your recovery code has been used.",
                )}
              </p>
              <a className="button-orange" href={"/login" + roleQuery}>
                {tr("Sign in")}
              </a>
            </>
          ) : (
            <>
              <span className="eyebrow">
                {recover
                  ? tr("ACCOUNT RECOVERY")
                  : signup
                    ? tr("START WITH YOUR TEAM")
                    : tr("WELCOME BACK")}
              </span>
              <h1>
                {recover
                  ? tr("Recover your account")
                  : invite
                    ? msg("Join {organization}", {
                        organization: invite.organization_name,
                      })
                    : signup
                      ? tr("Create your organization")
                      : tr(selectedOption?.title || "Sign in to ShiftProof")}
              </h1>
              <p>
                {recover
                  ? tr("Use one of the recovery codes you saved at signup.")
                  : invite
                    ? msg("You have been invited as {role}.", {
                        role: tr(
                          invite.role === "quality"
                            ? "Authorized reviewer"
                            : invite.role,
                        ),
                      })
                    : signup
                      ? tr(
                          "Select your industry. We’ll shape your workspace around it.",
                        )
                      : tr(
                          selectedOption?.loginDescription || "Your organizations, reports and handovers are waiting.",
                        )}
              </p>
              {error && (
                <div role="alert" className="platform-error">
                  {tr(error)}
                </div>
              )}
              {signup && !token && pilotApproval && (
                <p className="preview-notice">
                  {tr(
                    "Organization signup is currently available to approved pilot owners. Use your approved email address; ask your pilot contact if you need access. Workers join through their organization’s activation links.",
                  )}
                </p>
              )}
              {session && token ? (
                <>
                  <p>
                    {tr("Signed in as")} {session.user.email}
                  </p>
                  <button
                    className="button-orange"
                    disabled={busy || !invite}
                    onClick={accept}
                  >
                    {tr("Accept invitation")}
                  </button>
                  <button
                    className="text-button"
                    onClick={async () => {
                      await call("/auth/logout", {});
                      setSession(null);
                    }}
                  >
                    {tr("Use another account")}
                  </button>
                </>
              ) : (
                <form onSubmit={submit} className="platform-form">
                  {signup && (
                    <label>
                      {tr("Your name")}
                      <input
                        name="name"
                        defaultValue={invite?.name || ""}
                        required
                        minLength={2}
                        maxLength={100}
                        autoComplete="name"
                      />
                    </label>
                  )}
                  <label>
                    {tr("Email address")}
                    <input
                      name="email"
                      type="email"
                      required
                      autoComplete="email"
                    />
                  </label>
                  {recover && (
                    <label>
                      {tr("Recovery code")}
                      <input name="code" required autoComplete="off" />
                    </label>
                  )}
                  <PasswordFields
                    confirmation={signup || recover}
                    label={recover ? "New password" : "Password"}
                  />
                  {signup && !token && (
                    <>
                      <label>
                        {tr("Organization type")}
                        <Select
                          value={industry}
                          onChange={(e) => setIndustry(e.target.value)}
                        >
                          {industries.map((i) => (
                            <option key={i.id} value={i.id}>
                              {tr(i.name)}
                              {i.status === "preview" ? tr("  -  preview") : ""}
                            </option>
                          ))}
                        </Select>
                      </label>
                      {industries.find((i) => i.id === industry)?.status ===
                        "preview" && (
                        <div className="preview-notice">
                          {tr(
                            "You can create your organization and invite your team. Operational capture for this industry is planned and is not enabled yet.",
                          )}
                        </div>
                      )}
                    </>
                  )}
                  <button
                    className="button-orange"
                    disabled={busy || (!!token && !invite)}
                  >
                    {busy
                      ? tr("Please wait…")
                      : recover
                        ? tr("Reset password")
                        : signup
                          ? token
                            ? tr("Create account and join")
                            : tr("Create organization")
                          : tr("Sign in")}{" "}
                    
                  </button>
                </form>
              )}
              {!signup && !recover && !token && <a className="login-choice-link" href="/signin">{tr("Choose another sign-in option")}</a>}
              <div className="account-links">
                {!signup && (!selectedOption || selectedOption.id === "worker") && (
                  <a href="/worker/login">
                    {tr("कर्मचारी ID से साइन इन करें · Worker sign in")}
                  </a>
                )}
                {signup ? (
                  <span>
                    {tr("Already have an account?")}{" "}
                    <a href={"/login" + (token ? "?invite=" + token : "")}>
                      {tr("Sign in")}
                    </a>
                  </span>
                ) : (
                  <>
                    <a href={"/recover" + roleQuery}>{tr("Forgot password?")}</a>
                    {selectedOption && selectedOption.id !== "organization" ? <span>{tr("Need access? Ask your organisation owner for an invitation.")}</span> : <span>
                      {tr("New here?")}
                      <a href="/signup">{tr("Create an organization")}</a>
                    </span>}
                  </>
                )}
              </div>
              <small className="account-disclosure">
                {tr(
                  "Email ownership is not verified. Invitations are shared by your organization; ShiftProof does not send email.",
                )}
              </small>
            </>
          )}
        </div>
      </main>
    </div>
  );
}
