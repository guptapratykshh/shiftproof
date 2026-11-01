import { Select } from "../components/Select";
import { CheckboxRow } from "../components/OperationalUI";
import { tr, bilingual as t } from "../i18n";
import { useEffect, useState } from "react";
import { call, ApiError, type Organization } from "./client";
type Policy = {
  data_classification: "fictional" | "real";
  retention_days: number;
  recording_consent: boolean;
  factory_approval: boolean;
  provider_terms_approved: boolean;
  spending_cap_confirmed: boolean;
  max_storage_mb: number;
};
const defaults: Policy = {
  data_classification: "fictional",
  retention_days: 30,
  recording_consent: false,
  factory_approval: false,
  provider_terms_approved: false,
  spending_cap_confirmed: false,
  max_storage_mb: 1024,
};
// Stored policy also has server-only fields (for example `mode`). Never send
// them back to the strict update endpoint, even when talking to an older API.
function editablePolicy(value: Partial<Policy>): Policy {
  return Object.fromEntries(Object.entries(defaults).map(([key, fallback]) =>
    [key, value[key as keyof Policy] ?? fallback],
  )) as Policy;
}
export default function PilotPolicy({
  org,
  changed,
}: {
  org: Organization;
  changed: () => Promise<unknown>;
}) {
  const [policy, setPolicy] = useState(defaults),
    [providers, setProviders] = useState<Record<string, unknown>>({}),
    [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [busy, setBusy] = useState(false),
    [loaded, setLoaded] = useState(false),
    [reload, setReload] = useState(0);
  const path = `/organizations/${org.id}/pilot-policy`;
  useEffect(() => {
    let active = true;
    setLoaded(false);
    setError("");
    setNotice("");
    setProviders({});
    call<{ policy: Partial<Policy>; providers: Record<string, unknown> }>(path)
      .then((r) => {
        if (!active) return;
        setPolicy(editablePolicy(r.policy));
        setProviders(r.providers);
        setLoaded(true);
      })
      .catch((e) => { if (active) setError(e.message); });
    return () => { active = false; };
  }, [org.id, reload]);
  return (
    <section className="platform-panel">
      <h2>{tr("Recording and data policy")}</h2>
      <p>
        {tr(
          "Start with fictional practice data. Real factory recordings require the factory’s approval, participants’ consent and separately approved business-provider configuration. These settings alone do not approve the provider.",
        )}
      </p>
      {error && (
        <p className="platform-error" role="alert">
          {tr(error)}
        </p>
      )}
      {notice && <p role="status">{tr(notice)}</p>}
      {!loaded && (error
        ? <button className="button-outline" onClick={() => setReload(n => n + 1)}>{t("सेटिंग्स फिर लोड करें", "Reload settings")}</button>
        : <p role="status">{tr("Loading…")}</p>)}
      <form
        className="platform-form"
        onSubmit={async (e) => {
          e.preventDefault();
          if (!loaded || busy) return;
          setBusy(true);
          setError("");
          setNotice("");
          try {
            const saved = await call<Policy>(path, editablePolicy(policy), "PUT");
            setPolicy(editablePolicy(saved));
            setNotice(
              "Data policy saved. Provider access remains subject to server configuration.",
            );
            try {
              await changed();
              const r = await call<{ providers: Record<string, unknown> }>(path);
              setProviders(r.providers);
            } catch {
              setProviders({});
              setError(t("सेटिंग्स सहेज दी गई हैं, पर नई स्थिति लोड नहीं हुई। पेज ताज़ा करें।", "Settings were saved, but the updated status could not be loaded. Refresh the page."));
            }
          } catch (e) {
            setError(e instanceof ApiError && e.status === 422
              ? t("सेटिंग्स सहेजी नहीं गईं। भरे हुए मान और आवश्यक स्वीकृतियाँ जाँचें।", "Settings were not saved. Check the entered values and required approvals.")
              : (e as Error).message);
          } finally {
            setBusy(false);
          }
        }}
      >
        <label>
          {tr("Data mode")}
          <Select
            disabled={!loaded || busy}
            value={policy.data_classification}
            onChange={(e) =>
              setPolicy({
                ...policy,
                data_classification: e.target
                  .value as Policy["data_classification"],
              })
            }
          >
            <option value="fictional">{tr("Fictional practice data")}</option>
            <option value="real">
              {tr("Real factory data · approval required")}
            </option>
          </Select>
        </label>
        <div className="setup-grid">
          <label>
            {tr("Retention days")}
            <input
              disabled={!loaded || busy}
              type="number"
              min={1}
              max={3650}
              required
              value={policy.retention_days}
              onChange={(e) =>
                setPolicy({ ...policy, retention_days: Number(e.target.value) })
              }
            />
          </label>
          <label>
            {tr("Storage limit (MB)")}
            <input
              disabled={!loaded || busy}
              type="number"
              min={20}
              max={100000}
              required
              value={policy.max_storage_mb}
              onChange={(e) =>
                setPolicy({ ...policy, max_storage_mb: Number(e.target.value) })
              }
            />
          </label>
        </div>
        {(
          [
            ["factory_approval", "Factory approval obtained"],
            ["recording_consent", "Recording consent obtained"],
            [
              "provider_terms_approved",
              "Provider data terms reviewed and approved",
            ],
            ["spending_cap_confirmed", "Organization spending cap agreed"],
          ] as const
        ).map(([key, text]) => (
          <CheckboxRow
            disabled={!loaded || busy}
            key={key}
            checked={policy[key]}
            onChange={(e) => setPolicy({ ...policy, [key]: e.target.checked })}
          >
            {tr(text)}
          </CheckboxRow>
        ))}
        <button className="button-orange" disabled={!loaded || busy}>
          {tr("Save data policy")}
        </button>
      </form>
      <details>
        <summary>{tr("Provider approval status")}</summary>
        <dl>
          {Object.entries(providers).map(([k, v]) => (
            <div key={k}>
              <dt>{tr(k.replaceAll("_", " "))}</dt>
              <dd>
                {typeof v === "object" ? JSON.stringify(v) : tr(String(v))}
              </dd>
            </div>
          ))}
        </dl>
      </details>
    </section>
  );
}
