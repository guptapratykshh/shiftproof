import { tr, useLanguage, bilingual } from "../i18n";
import { useId, useState } from "react";

// Local guidance only: no password leaves this component for strength scoring.
export default function PasswordFields({
  confirmation = false,
  label = "Password",
  language: preferredLanguage,
}: {
  confirmation?: boolean;
  label?: string;
  language?: "hi" | "en";
}) {
  const currentLanguage = useLanguage();
  const language = preferredLanguage ?? currentLanguage;
  const t = bilingual;
  const id = useId();
  const [password, setPassword] = useState("");
  const [repeat, setRepeat] = useState("");
  const [visible, setVisible] = useState(false);
  const common = /password|qwerty|12345|letmein|(.)\1{4}/i.test(password);
  const words = password
    .trim()
    .split(/[\s-]+/)
    .filter(Boolean).length;
  const variety = [/[a-z]/, /[A-Z]/, /[0-9]/, /[^a-zA-Z0-9]/].filter((r) =>
    r.test(password),
  ).length;
  const score = !password
    ? 0
    : password.length < 12 || common
      ? 1
      : password.length >= 20 && (words >= 4 || variety >= 3)
        ? 3
        : 2;
  const mismatch = repeat.length > 0 && password !== repeat;
  return (
    <>
      <label htmlFor={id}>{tr(label)}</label>
      <div className="password-control">
        <input
          id={id}
          name="password"
          type={visible ? "text" : "password"}
          required
          minLength={confirmation ? 12 : 1}
          maxLength={128}
          autoComplete={confirmation ? "new-password" : "current-password"}
          value={password}
          aria-describedby={confirmation ? id + "-help" : undefined}
          onChange={(e) => {
            setPassword(e.target.value);
            const other = e.currentTarget.form?.elements.namedItem(
              "confirm_password",
            ) as HTMLInputElement | null;
            other?.setCustomValidity(
              other.value && other.value !== e.target.value
                ? tr("Passwords do not match")
                : "",
            );
          }}
        />
        <button
          type="button"
          aria-pressed={visible}
          onClick={() => setVisible(!visible)}
        >
          {visible
            ? t("पासवर्ड छिपाएँ", "Hide password")
            : t("पासवर्ड दिखाएँ", "Show password")}
        </button>
      </div>
      {confirmation && (
        <>
          <div
            id={id + "-help"}
            className="password-guidance"
            aria-live="polite"
          >
            <meter
              min={0}
              max={3}
              value={score}
              aria-label={tr("Password strength estimate")}
            />
            <small>
              {
                (language === "hi"
                  ? [
                      "12–128 अक्षर इस्तेमाल करें।",
                      "पासवर्ड कमजोर लग रहा है। आम शब्द और एक ही क्रम बार-बार न रखें।",
                      "पासवर्ड कुछ मजबूत है। अलग-अलग शब्दों का और लंबा वाक्य चुनें।",
                      "पासवर्ड मजबूत लग रहा है। इसे दूसरे खातों में इस्तेमाल न करें।",
                    ]
                  : [
                      "Use 12–128 characters.",
                      "Weak estimate  -  avoid common words and repeated patterns.",
                      "Moderate estimate  -  try a longer phrase of unrelated words.",
                      "Strong estimate  -  use a unique password for this account.",
                    ])[score]
              }
            </small>
          </div>
          <label htmlFor={id + "-confirm"}>
            {t("पासवर्ड फिर से लिखें", "Confirm password")}
          </label>
          <input
            id={id + "-confirm"}
            name="confirm_password"
            type={visible ? "text" : "password"}
            required
            maxLength={128}
            autoComplete="new-password"
            value={repeat}
            aria-invalid={mismatch}
            aria-describedby={mismatch ? id + "-mismatch" : undefined}
            onChange={(e) => {
              setRepeat(e.target.value);
              e.currentTarget.setCustomValidity(
                e.target.value !== password ? tr("Passwords do not match") : "",
              );
            }}
          />
          {mismatch && (
            <small id={id + "-mismatch"} role="alert">
              {t("दोनों पासवर्ड अलग हैं।", "Passwords do not match.")}
            </small>
          )}
        </>
      )}
    </>
  );
}
