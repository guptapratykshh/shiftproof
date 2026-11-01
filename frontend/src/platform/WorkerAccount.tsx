import { AppearanceControl } from "../theme";
import {
  tr,
  useLanguage,
  setLanguage,
  adoptAccountLanguage,
  bilingual,
} from "../i18n";
import { useEffect, useState, type FormEvent } from "react";
import { Brand } from "./Landing";
import PasswordFields from "./PasswordFields";
import { call } from "./client";
import { clearOfflineContext } from "./offlineContext";

export default function WorkerAccount({
  token,
  reset = false,
}: {
  token?: string;
  reset?: boolean;
}) {
  const english = useLanguage() === "en";
  const setEnglish = (value: boolean) => setLanguage(value ? "en" : "hi");
  useEffect(() => {
    adoptAccountLanguage("", "hi");
  }, []);
  const [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const [invitation, setInvitation] = useState<{
    name: string;
    organization_name: string;
    employee_id: string;
    organization_code?: string;
  } | null>(null);
  const t = bilingual;
  useEffect(() => {
    if (token && !reset)
      call<typeof invitation>("/invitations/" + token)
        .then(setInvitation)
        .catch((e) => setError(e.message));
  }, [token, reset]);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const data = Object.fromEntries(new FormData(event.currentTarget));
    try {
      if (token && data.password !== data.confirm_password)
        throw new Error(
          t("दोनों पासवर्ड एक जैसे होने चाहिए।", "Passwords must match."),
        );
      const result = await call<{ organization_id: string }>(
        token
          ? reset
            ? "/auth/worker/reset"
            : "/auth/worker/activate"
          : "/auth/worker/login",
        token ? { token, ...data } : data,
      );
      clearOfflineContext();
      location.href = "/app/" + result.organization_id;
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="worker-account" lang={english ? "en" : "hi"}>
      <header>
        <Brand />
        <AppearanceControl />
        <button className="button-outline" onClick={() => setEnglish(!english)}>
          {english ? "हिन्दी" : "English"}
        </button>
      </header>
      <main className="account-card">
        <span className="eyebrow">
          {tr("SHIFTPROOF ·")}
          {t("आपकी टीम", "YOUR TEAM")}
        </span>
        <h1>
          {token
            ? t("अपना पासवर्ड बनाएँ", "Set your password")
            : tr("Sign in as a worker")}
        </h1>
        {invitation && (
          <p>
            {invitation.name} · {invitation.organization_name}
            <br />
            {t("कर्मचारी ID", "Employee ID")}:{" "}
            <strong>{invitation.employee_id}</strong>
          </p>
        )}
        <p>
          {t(
            "आपके संगठन ने आपको जो जानकारी दी है, वही भरें।",
            "Use the details provided by your organization.",
          )}
        </p>
        {error && (
          <p role="alert" className="platform-error">
            {tr(error)}
          </p>
        )}
        <form onSubmit={submit} className="platform-form">
          {!token && (
            <>
              <label>
                {t("संगठन कोड", "Organization code")}
                <input
                  name="organization_code"
                  required
                  autoComplete="organization"
                  autoCapitalize="characters"
                />
              </label>
              <label>
                {t("कर्मचारी ID", "Employee ID")}
                <input
                  name="employee_id"
                  required
                  autoComplete="username"
                  autoCapitalize="none"
                />
              </label>
            </>
          )}
          <PasswordFields
            confirmation={!!token}
            label={t("पासवर्ड", "Password")}
            language={english ? "en" : "hi"}
          />
          <button
            className="button-orange"
            disabled={busy || (!!token && !reset && !invitation)}
          >
            {busy ? t("रुकिए…", "Please wait…") : t("आगे बढ़ें", "Continue")}
          </button>
        </form>
        <p className="account-links">
          {t(
            "पासवर्ड भूल गए? संगठन के मालिक से नया लिंक माँगें।",
            "Forgot your password? Ask your organization owner for a reset link.",
          )}
        </p>
        <a href="/login?role=worker">{t("ईमेल से साइन इन करें", "Sign in with email")}</a>
        {!token && <a className="login-choice-link" href="/signin">{tr("Choose another sign-in option")}</a>}
      </main>
    </div>
  );
}
