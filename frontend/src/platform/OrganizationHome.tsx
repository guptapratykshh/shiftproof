import { Select } from "../components/Select";
import { AppearanceControl } from "../theme";
import { tr, LanguageButton } from "../i18n";
import { useEffect, useState } from "react";
import { Brand } from "./Landing";
import { call, type Session, type Industry } from "./client";
export default function OrganizationHome({
  industries,
}: {
  industries: Industry[];
}) {
  const [session, setSession] = useState<Session | null>(null),
    [error, setError] = useState("");
  useEffect(() => {
    call<Session>("/auth/session")
      .then(setSession)
      .catch((e) => setError(e.message));
  }, []);
  return (
    <div className="worker-account">
      <header>
        <Brand />
        <LanguageButton /><AppearanceControl />
        <a href="/login">{tr("Sign in")}</a>
      </header>
      <main className="account-card">
        <h1>{tr("Your organizations")}</h1>
        {error && <p role="alert">{tr(error)}</p>}
        {session?.organizations.map((o) => (
          <a className="organization-choice" key={o.id} href={"/app/" + o.id}>
            {o.name}
          </a>
        ))}
        {session && !session.organizations.length && (
          <p>
            {tr(
              "Your account is active, but you do not currently belong to an organization. Ask your organization owner for an activation link.",
            )}
          </p>
        )}
        {session && session.capabilities?.create_organization !== false && (
          <details>
            <summary>{tr("Create an organization")}</summary>
            <form
              className="platform-form"
              onSubmit={async (e) => {
                e.preventDefault();
                const body = Object.fromEntries(new FormData(e.currentTarget));
                try {
                  const r = await call<{ organization_id: string }>(
                    "/organizations",
                    {
                      ...body,
                      timezone:
                        Intl.DateTimeFormat().resolvedOptions().timeZone ||
                        "Asia/Kolkata",
                    },
                  );
                  location.href =
                    "/app/" +
                    r.organization_id +
                    (body.industry === "healthcare" ||
                    !["manufacturing", "maintenance", "warehousing"].includes(
                      String(body.industry),
                    )
                      ? ""
                      : "?view=setup");
                } catch (err) {
                  setError((err as Error).message);
                }
              }}
            >
              <label>
                {tr("Organization name")}
                <input name="name" required minLength={2} />
              </label>
              <label>
                {tr("Organization type")}
                <Select name="industry">
                  {industries.map((i) => (
                    <option value={i.id} key={i.id}>
                      {tr(i.name)}
                      {i.status === "preview" ? tr("  -  preview") : ""}
                    </option>
                  ))}
                </Select>
              </label>
              <button className="button-orange">
                {tr("Create organization")}
              </button>
            </form>
          </details>
        )}
      </main>
    </div>
  );
}
