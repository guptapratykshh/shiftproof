import { Select } from "../components/Select";
import AssistedPermissions from "./AssistedPermissions";
import type { Operations } from "./OperationsSetup";
import { useEffect, useState } from "react";
import { tr, msg } from "../i18n";
import { call, type Organization } from "./client";
import {
  type Member,
  label,
  roleLabel,
  accessLabel,
  formatTime,
} from "./workspaceLabels";
import { Dialog, SectionTabs, ScrollArea } from "../components/OperationalUI";
export default function Team({
  org,
  currentUser,
  act,
  busy,
}: {
  org: Organization;
  currentUser: string;
  act: (fn: () => Promise<unknown>) => Promise<void>;
  busy: boolean;
}) {
  const [tab, setTab] = useState("members"),
    [search, setSearch] = useState(""),
    [editing, setEditing] = useState<string | null>(null),
    [adding, setAdding] = useState(false),
    [kind, setKind] = useState("worker");
  const [operations, setOperations] = useState<Operations | null>(null);
  const [members, setMembers] = useState<Member[]>([]),
    [link, setLink] = useState(""),
    [error, setError] = useState(""),
    [invitations, setInvitations] = useState<
      {
        id: string;
        name: string;
        email: string;
        access: string;
        role: string;
        status: string;
        expires: number;
      }[]
    >([]),
    [events, setEvents] = useState<
      {
        id: string;
        actor_name: string;
        action: string;
        created_at: number;
        target_id: string;
        details: Record<string, string>;
      }[]
    >([]);
  const base = "/organizations/" + org.id;
  const load = async () => {
    setMembers(await call<Member[]>(base + "/members"));
    if (org.profile.status === "available")
      setOperations(
        await call<Operations>(base + "/operations").catch(() => null),
      );
    if (org.access !== "member") {
      setInvitations(await call<typeof invitations>(base + "/invitations"));
      setEvents(await call<typeof events>(base + "/access-events"));
    }
  };
  useEffect(() => {
    load().catch((e) => setError(e.message));
  }, [org.id]);
  return (
    <>
      {org.access === "owner" && <AssistedPermissions base={base} members={members} operations={operations} />}
      <div className="team-toolbar">
        <SectionTabs
          label={tr("Team")}
          value={tab}
          onChange={setTab}
          options={[
            { id: "members", label: tr("Members") },
            { id: "invitations", label: tr("Invitations") },
            { id: "history", label: tr("Access history") },
          ]}
        />
        <button
          className="button-orange"
          onClick={() => {
            setAdding(true);
            setLink("");
          }}
        >
          {tr("Add team member")}
        </button>
      </div>
      {tab === "members" && (
        <section className="platform-panel">
          <h2>{tr("Members")}</h2>
          <label className="search-field">
            {tr("Find a team member")}
            <input
              type="search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder={tr("Search by name or employee ID")}
            />
          </label>
          <p>
            {tr(
              "Account administration and operational review are separate permissions.",
            )}
          </p>
          {error && <p role="alert">{tr(error)}</p>}
          {!members.length && <p>{tr("Loading team…")}</p>}
          {search &&
            !members.some((m) =>
              (m.name + " " + (m.employee_id || m.email || ""))
                .toLowerCase()
                .includes(search.toLowerCase()),
            ) && (
              <p role="status">{tr("No team members match this search.")}</p>
            )}
          <ScrollArea label={tr("Members")}>
          {members
            .filter((m) =>
              (m.name + " " + (m.employee_id || m.email || ""))
                .toLowerCase()
                .includes(search.toLowerCase()),
            )
            .map((m) => (
              <article className="team-member" key={m.id}>
                <div className="member-avatar" aria-hidden="true">
                  {m.name.slice(0, 1)}
                </div>
                <div>
                  <strong>
                    {m.name}
                    {m.id === currentUser ? tr(" (you)") : ""}
                  </strong>
                  <p>
                    {accessLabel(m.access)} · {roleLabel(m.role)}
                  </p>
                  <small>{m.employee_id || m.email}</small>
                  <p className="member-assignment">
                    {operations?.shifts
                      .filter((s) =>
                        operations.assignments?.some(
                          (a) => a.shift_id === s.id && a.user_id === m.id,
                        ),
                      )
                      .map((s) => s.name)
                      .join(" · ") || tr("No shift assigned")}
                  </p>
                </div>
                <button
                  className="button-outline"
                  onClick={() => setEditing(m.id)}
                >
                  {tr("Manage")}
                </button>
              </article>
            ))}
          </ScrollArea>
          {members
            .filter((m) => m.id === editing)
            .map((m) => (
              <Dialog key={m.id} title={m.name} close={() => setEditing(null)}>
                <form
                  className="platform-form member-editor"
                  key={m.id}
                  onSubmit={(e) => {
                    e.preventDefault();
                    const data = Object.fromEntries(
                      new FormData(e.currentTarget),
                    );
                    void act(async () => {
                      await call(base + "/members/" + m.id, data, "PUT");
                      await load();
                      setEditing(null);
                    });
                  }}
                >
                  <div>
                    <strong>
                      {m.name}
                      {m.id === currentUser ? tr(" (you)") : ""}
                    </strong>
                    <small>
                      {m.employee_id
                        ? tr("Employee ID:") + " " + m.employee_id
                        : m.email}
                    </small>
                  </div>
                  <label>
                    {tr("Access")}
                    <Select
                      name="access"
                      defaultValue={m.access}
                      disabled={org.access !== "owner"}
                    >
                      {["owner", "admin", "member"].map((r) => (
                        <option key={r} value={r}>
                          {accessLabel(r)}
                        </option>
                      ))}
                    </Select>
                  </label>
                  <label>
                    {tr("Operational role")}
                    <Select
                      name="role"
                      defaultValue={m.role}
                      disabled={org.access !== "owner"}
                    >
                      {["operator", "supervisor", "quality"].map((r) => (
                        <option value={r} key={r}>
                          {roleLabel(r)}
                        </option>
                      ))}
                    </Select>
                  </label>
                  {org.access === "owner" && (
                    <>
                      <button disabled={busy}>{tr("Save permissions")}</button>
                      {m.employee_id &&
                        m.role === "operator" &&
                        m.access === "member" && (
                          <button
                            type="button"
                            disabled={busy}
                            onClick={() =>
                              void act(async () => {
                                const r = await call<{ reset_path: string }>(
                                  base + "/members/" + m.id + "/worker-reset",
                                  {},
                                );
                                setLink(location.origin + r.reset_path);
                              })
                            }
                          >
                            {tr("Create password reset link")}
                          </button>
                        )}
                      <button
                        type="button"
                        disabled={busy}
                        onClick={() => {
                          if (
                            confirm(
                              msg("Remove {name} from this organization?", {
                                name: m.name,
                              }),
                            )
                          )
                            void act(async () => {
                              await call(
                                base + "/members/" + m.id,
                                undefined,
                                "DELETE",
                              );
                              await load();
                            });
                        }}
                      >
                        {tr("Remove")}
                      </button>
                    </>
                  )}
                </form>
              </Dialog>
            ))}
        </section>
      )}
      {org.access === "owner" && tab === "invitations" && (
        <WorkerInvitations org={org} act={act} busy={busy} showForm={false} />
      )}
      {adding && (
        <Dialog title={tr("Add team member")} close={() => setAdding(false)}>
          <label className="role-choice">
            {tr("Operational role")}
            <Select value={kind} onChange={(e) => setKind(e.target.value)}>
              <option value="worker">{tr("Shift worker")}</option>
              <option value="email">{tr("Supervisor or reviewer")}</option>
            </Select>
          </label>
          {kind === "worker" && (
            <WorkerInvitations org={org} act={act} busy={busy} showForm />
          )}
          {kind === "email" && org.access !== "member" && (
            <section className="platform-panel">
              <h2>{tr("Add supervisor or reviewer by email")}</h2>
              <p>
                {tr(
                  "Choose their responsibilities. They set their own password using a single-use activation link.",
                )}
              </p>
              <form
                className="platform-form"
                onSubmit={(e) => {
                  e.preventDefault();
                  const data = Object.fromEntries(
                    new FormData(e.currentTarget),
                  );
                  void act(async () => {
                    const result = await call<{ join_path: string }>(
                      base + "/invitations",
                      data,
                    );
                    setLink(location.origin + result.join_path);
                    await load();
                  });
                }}
              >
                <label>
                  {tr("Team member name")}
                  <input name="name" required minLength={2} maxLength={100} />
                </label>
                <label>
                  {tr("Email address")}
                  <input name="email" type="email" required />
                </label>
                <label>
                  {tr("Access")}
                  <Select name="access">
                    <option value="member">{tr("Member")}</option>
                    {org.access === "owner" && (
                      <option value="admin">{tr("Administrator")}</option>
                    )}
                  </Select>
                </label>
                <label>
                  {tr("Operational role")}
                  <Select name="role" defaultValue="supervisor">
                    {["operator", "supervisor", "quality"].map((r) => (
                      <option key={r} value={r}>
                        {roleLabel(r)}
                      </option>
                    ))}
                  </Select>
                </label>
                <button className="button-dark" disabled={busy}>
                  {tr("Create invitation link")}
                </button>
              </form>
              {link && (
                <div className="preview-notice">
                  <p>
                    {tr(
                      "Share this single-use link with the invited person. It expires in 72 hours. No email was sent.",
                    )}
                  </p>
                  <input
                    aria-label={tr("Invitation link")}
                    value={link}
                    readOnly
                  />
                  <button
                    onClick={() =>
                      void navigator.clipboard
                        .writeText(link)
                        .catch(() =>
                          setError("Select and copy the link above."),
                        )
                    }
                  >
                    {tr("Copy invitation link")}
                  </button>
                </div>
              )}
            </section>
          )}
        </Dialog>
      )}
      {!adding && link && (
        <section className="platform-panel">
          <label>
            {tr("Invitation link")}
            <input readOnly value={link} />
          </label>
          <button
            className="button-outline"
            onClick={() =>
              void navigator.clipboard
                .writeText(link)
                .catch(() => setError("Select and copy the link above."))
            }
          >
            {tr("Copy invitation link")}
          </button>
        </section>
      )}
      {tab !== "members" && org.access !== "member" && (
        <section className="platform-panel">
          {tab === "invitations" && (
            <>
              <h2>{tr("Team activation links")}</h2>
              {!invitations.length && <p>{tr("No invitations yet.")}</p>}
              <ScrollArea label={tr("Team activation links")}>
              {invitations.map((inv) => (
                <article className="invitation-row" key={inv.id}>
                  <div>
                    <strong>{inv.name || inv.email}</strong>
                    <p>
                      {inv.email} · {roleLabel(inv.role)}
                    </p>
                    <small>
                      {tr(inv.status)} {tr("· Expires")}{" "}
                      {formatTime(inv.expires * 1000, org.timezone)}
                    </small>
                  </div>
                  {["pending", "expired"].includes(inv.status) &&
                    (org.access === "owner" || inv.access === "member") && (
                      <div className="button-row">
                        <button
                          disabled={busy}
                          onClick={() =>
                            void act(async () => {
                              const result = await call<{ join_path: string }>(
                                base + "/invitations/" + inv.id + "/replace",
                                {},
                              );
                              setLink(location.origin + result.join_path);
                              await load();
                            })
                          }
                        >
                          {tr("Replace link")}
                        </button>
                        <button
                          disabled={busy}
                          onClick={() =>
                            void act(async () => {
                              await call(
                                base + "/invitations/" + inv.id,
                                undefined,
                                "DELETE",
                              );
                              setLink("");
                              await load();
                            })
                          }
                        >
                          {tr("Cancel invitation")}
                        </button>
                      </div>
                    )}
                </article>
              ))}
              </ScrollArea>
            </>
          )}
          {tab === "history" && (
            <div className="access-timeline">
              <h2>{tr("Access history")}</h2>
              {!events.length && (
                <p>
                  {tr(
                    "No recorded access changes yet. Older actions were not retroactively logged.",
                  )}
                </p>
              )}
              <ScrollArea label={tr("Access history")}>
              {events.map((e) => (
                <article key={e.id}>
                  <strong>
                    {e.actor_name} · {label(e.action.replaceAll(".", " "))}
                  </strong>
                  <p>
                    {e.details.name ||
                      e.details.email ||
                      members.find((m) => m.id === e.target_id)?.name ||
                      e.target_id}
                  </p>
                  <small>
                    {formatTime(e.created_at * 1000, org.timezone)}{" "}
                    {e.details.role ? " · " + roleLabel(e.details.role) : ""}
                  </small>
                </article>
              ))}
              </ScrollArea>
            </div>
          )}
        </section>
      )}
    </>
  );
}
function WorkerInvitations({
  org,
  act,
  busy,
  showForm = false,
}: {
  org: Organization;
  act: (fn: () => Promise<unknown>) => Promise<void>;
  busy: boolean;
  showForm?: boolean;
}) {
  const [rows, setRows] = useState<
      {
        id: string;
        name: string;
        employee_id: string;
        status: string;
        expires: number;
      }[]
    >([]),
    [link, setLink] = useState(""),
    [error, setError] = useState("");
  const base = "/organizations/" + org.id + "/worker-invitations";
  const load = async () => setRows(await call<typeof rows>(base));
  useEffect(() => {
    load().catch((e) => setError(e.message));
  }, [org.id]);
  return (
    <section className="platform-panel">
      <h2>
        {showForm ? tr("Add a shift worker") : tr("Worker activation links")}
      </h2>
      <p>
        {tr(
          "No email is needed. Share the activation link privately; the worker chooses their own password.",
        )}
      </p>
      <p>
        {tr("Organization code:")}{" "}
        <strong>
          {org.login_code || tr("Available after organization refresh")}
        </strong>
      </p>
      {error && <p role="alert">{tr(error)}</p>}
      {showForm && (
        <form
          className="platform-form"
          onSubmit={(e) => {
            e.preventDefault();
            const body = Object.fromEntries(new FormData(e.currentTarget));
            void act(async () => {
              const result = await call<{ join_path: string }>(base, body);
              setLink(location.origin + result.join_path);
              await load();
            });
          }}
        >
          <label>
            {tr("Worker name")}
            <input name="name" required minLength={2} />
          </label>
          <label>
            {tr("Employee ID")}
            <input
              name="employee_id"
              required
              autoCapitalize="none"
              placeholder="EMP-017"
            />
          </label>
          <button className="button-orange" disabled={busy}>
            {tr("Create worker activation link")}
          </button>
        </form>
      )}
      {link && (
        <div className="preview-notice">
          <label>
            {tr("Activation link")}
            <input readOnly value={link} />
          </label>
          <button
            className="button-outline"
            onClick={() =>
              void navigator.clipboard
                .writeText(link)
                .catch(() => setError("Select and copy the link above."))
            }
          >
            {tr("Copy worker link")}
          </button>
        </div>
      )}
      {!showForm && (
        <ScrollArea label={tr("Team activation links")}>
          {rows.map((r) => (
            <article className="reason-row" key={r.id}>
              <strong>
                {r.name} · {r.employee_id}
              </strong>
              <p>{tr(r.status)}</p>
              {r.status === "pending" && (
                <button
                  disabled={busy}
                  onClick={() =>
                    void act(async () => {
                      await call(base + "/" + r.id, undefined, "DELETE");
                      await load();
                    })
                  }
                >
                  {tr("Cancel activation")}
                </button>
              )}
              {r.status !== "accepted" && (
                <button
                  disabled={busy}
                  onClick={() =>
                    void act(async () => {
                      const result = await call<{ join_path: string }>(
                        base + "/" + r.id + "/replace",
                        {},
                      );
                      setLink(location.origin + result.join_path);
                      await load();
                    })
                  }
                >
                  {tr("Replace activation link")}
                </button>
              )}
            </article>
          ))}
        </ScrollArea>
      )}
    </section>
  );
}
