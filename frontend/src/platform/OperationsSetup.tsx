import { Select } from "../components/Select";
import { Dialog, CheckboxRow } from "../components/OperationalUI";
import { tr, locale } from "../i18n";
import { useEffect, useState } from "react";
import { organizationInstant } from "./timezone";
import type { Workspace } from "../types";
import { call, type Session, type Organization } from "./client";
export type Operations = {
  locations: { id: string; name: string }[];
  teams: { id: string; name: string; location_id?: string }[];
  shifts: {
    id: string;
    name: string;
    starts_at?: string;
    ends_at?: string;
    location_id?: string;
    team_id?: string;
    status?: string;
    incoming_shift_id?: string;
    supervisor_id?: string;
  }[];
  assignments?: {
    shift_id: string;
    user_id: string;
    work_item_ids: string[];
  }[];
  active_shift_id?: string;
};
export default function OperationsSetup({
  org,
  changed,
  section = "places",
}: {
  org: Organization;
  changed: () => Promise<unknown>;
  section?: "places" | "shifts";
}) {
  const [creating, setCreating] = useState<
    "location" | "team" | "shift" | null
  >(null);
  const [items, setItems] = useState<Workspace["batches"]>([]),
    [ownId, setOwnId] = useState(""),
    [newLocation, setNewLocation] = useState(""),
    [newTeam, setNewTeam] = useState(""),
    [createdShift, setCreatedShift] = useState<string | null>(null);
  const [data, setData] = useState<Operations | null>(null),
    [people, setPeople] = useState<
      { id: string; name: string; role: string }[]
    >([]),
    [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [busy, setBusy] = useState(false);
  const base = "/organizations/" + org.id;
  const load = async () => {
    setData(await call<Operations>(base + "/operations"));
    setPeople(await call<typeof people>(base + "/directory"));
    setItems((await call<Workspace>(base + "/workspace")).batches);
    setOwnId((await call<Session>("/auth/session")).user.id);
  };
  useEffect(() => {
    load().catch((e) => setError(e.message));
  }, [org.id]);
  async function submit(
    event: React.FormEvent<HTMLFormElement>,
    path: string,
    convert: (data: FormData) => unknown,
  ) {
    event.preventDefault();
    setError("");
    setBusy(true);
    try {
      const form = new FormData(event.currentTarget);
      if (path === "/shift-occurrences") {
        const result = createdShift
          ? { id: createdShift }
          : await call<{ id: string }>(base + path, convert(form));
        setCreatedShift(result.id);
        await call(
          base + path + "/" + result.id + "/assignments",
          {
            user_ids: [form.get("supervisor_id")],
            supervisor_id: form.get("supervisor_id"),
            work_item_ids: form.getAll("work_item_ids"),
          },
          "PUT",
        );
        setCreatedShift(null);
      } else
        await call(
          base + path,
          convert(form),
          path.endsWith("/assignments") ? "PUT" : "POST",
        );
      await load();
      await changed();
      setCreating(null);
      setNotice("Saved. Assigned people can now find this shift and its work.");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="platform-panel operations-setup">
      <div className="panel-heading">
        <div>
          <h2>
            {section === "places" ? tr("Locations & teams") : tr("Shifts")}
          </h2>
          <p>
            {section === "places"
              ? tr("Organize where your team works.")
              : tr("Assign people and work to a dated shift.")}
          </p>
        </div>
        <button
          className="button-orange"
          onClick={() =>
            setCreating(section === "places" ? "location" : "shift")
          }
        >
          {section === "places" ? tr("Add location") : tr("Create dated shift")}
        </button>
      </div>
      {!data && <p role="status">{tr("Loading…")}</p>}
      {section === "places" && (
        <div className="resource-columns">
          <div>
            <h3>{tr("Locations")}</h3>
            {!data?.locations.length && <p>{tr("No locations yet.")}</p>}
            {data?.locations.map((l) => (
              <article className="resource-row" key={l.id}>
                <strong>{l.name}</strong>
                <small>
                  {data.teams.filter((t) => t.location_id === l.id).length}{" "}
                  {tr("teams")}
                </small>
              </article>
            ))}
          </div>
          <div>
            <div className="panel-heading">
              <h3>{tr("Teams")}</h3>
              <button
                className="button-outline"
                onClick={() => setCreating("team")}
                disabled={!data?.locations.length}
              >
                {tr("Add team")}
              </button>
            </div>
            {!data?.teams.length && <p>{tr("No teams yet.")}</p>}
            {data?.teams.map((t) => (
              <article className="resource-row" key={t.id}>
                <strong>{t.name}</strong>
                <small>
                  {data.locations.find((l) => l.id === t.location_id)?.name}
                </small>
              </article>
            ))}
          </div>
        </div>
      )}
      {error && (
        <p className="platform-error" role="alert">
          {tr(error)}
        </p>
      )}
      {notice && <p role="status">{tr(notice)}</p>}
      {creating === "location" && (
        <Dialog title={tr("Add location")} close={() => setCreating(null)}>
          <form
            className="platform-form"
            onSubmit={(e) =>
              submit(e, "/locations", (d) => ({ name: d.get("name") }))
            }
          >
            <h3>{tr("1. Location")}</h3>
            <label>
              {tr("Name")}
              <input
                name="name"
                required
                minLength={2}
                placeholder={tr("Packing floor")}
              />
            </label>
            <button className="button-outline" disabled={busy}>
              {tr("Add location")}
            </button>
          </form>
        </Dialog>
      )}
      {creating === "team" && (
        <Dialog title={tr("Add team")} close={() => setCreating(null)}>
          <form
            className="platform-form"
            onSubmit={(e) =>
              submit(e, "/teams", (d) => ({
                name: d.get("name"),
                location_id: d.get("location_id"),
              }))
            }
          >
            <h3>{tr("2. Team")}</h3>
            <label>
              {tr("Name")}
              <input name="name" required minLength={2} />
            </label>
            <label>
              {tr("Location")}
              <Select name="location_id" required>
                <option value="">{tr("Choose location")}</option>
                {data?.locations.map((l) => (
                  <option value={l.id} key={l.id}>
                    {l.name}
                  </option>
                ))}
              </Select>
            </label>
            <button className="button-outline" disabled={busy}>
              {tr("Add team")}
            </button>
          </form>
        </Dialog>
      )}
      {creating === "shift" && (
        <Dialog
          title={tr("Create dated shift")}
          close={() => setCreating(null)}
        >
          <p>
            {tr("Times use your organization timezone.")} {org.timezone}
          </p>
          <form
            className="platform-form"
            onSubmit={(e) =>
              submit(e, "/shift-occurrences", (d) => ({
                name: d.get("name"),
                location_id: d.get("location_id"),
                team_id: d.get("team_id"),
                starts_at: organizationInstant(
                  String(d.get("starts_at")),
                  org.timezone,
                ),
                ends_at: organizationInstant(
                  String(d.get("ends_at")),
                  org.timezone,
                ),
              }))
            }
          >
            <h3>{tr("3. Dated shift")}</h3>
            <label>
              {tr("Shift name")}
              <input
                name="name"
                required
                minLength={2}
                placeholder={tr("Evening shift")}
              />
            </label>
            <label>
              {tr("Location")}
              <Select
                name="location_id"
                required
                value={newLocation}
                onChange={(e) => {
                  setNewLocation(e.target.value);
                  setNewTeam("");
                }}
                disabled={!!createdShift}
              >
                <option value="">{tr("Choose location")}</option>
                {data?.locations.map((l) => (
                  <option value={l.id} key={l.id}>
                    {l.name}
                  </option>
                ))}
              </Select>
            </label>
            <label>
              {tr("Team")}
              <Select
                name="team_id"
                required
                value={newTeam}
                onChange={(e) => setNewTeam(e.target.value)}
                disabled={!!createdShift}
              >
                <option value="">{tr("Choose team")}</option>
                {data?.teams
                  .filter((t) => t.location_id === newLocation)
                  .map((l) => (
                    <option value={l.id} key={l.id}>
                      {l.name}
                    </option>
                  ))}
              </Select>
            </label>
            <label>
              {tr("Starts")}
              <input name="starts_at" type="datetime-local" required />
            </label>
            <label>
              {tr("Ends")}
              <input name="ends_at" type="datetime-local" required />
            </label>
            <label>
              {tr("Shift supervisor")}
              <Select name="supervisor_id" required>
                <option value="">{tr("Choose supervisor")}</option>
                {people
                  .filter(
                    (p) =>
                      p.role === "supervisor" ||
                      (p.id === ownId && p.role === "quality"),
                  )
                  .map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name}
                    </option>
                  ))}
              </Select>
            </label>
            <fieldset>
              <legend>{tr("Assigned work")}</legend>
              {items
                .filter((i) => i.team_id === newTeam)
                .map((i) => (
                  <CheckboxRow
                    key={i.id}
                    name="work_item_ids"
                    value={i.id}
                    defaultChecked
                  >
                    {i.id} · {i.name}
                  </CheckboxRow>
                ))}
              <small>
                {tr(
                  "Leave all work unchecked to include all work assigned to this team.",
                )}
              </small>
            </fieldset>
            {createdShift && (
              <p role="status">
                {tr("Shift saved. Retry to finish assigning people and work.")}
              </p>
            )}
            <button className="button-orange" disabled={busy}>
              {tr("Create dated shift")}
            </button>
          </form>
        </Dialog>
      )}
      {section === "shifts" && !data?.shifts.length && (
        <p>
          {tr(
            "No shifts yet. Create your first shift to assign people and work.",
          )}
        </p>
      )}
      {section === "shifts" &&
        data?.shifts.map((s) => (
          <details key={s.id} className="shift-assignment">
            <summary>
              {s.name} ·{" "}
              {s.starts_at
                ? new Date(s.starts_at).toLocaleString(locale(), {
                    timeZone: org.timezone,
                    timeZoneName: "short",
                  })
                : tr("Current handover")}
              {s.status ? " · " + tr(s.status) : ""}
            </summary>
            <form
              className="platform-form"
              onSubmit={(e) =>
                submit(
                  e,
                  "/shift-occurrences/" + s.id + "/assignments",
                  (d) => ({
                    user_ids: d.getAll("user_ids"),
                    supervisor_id: d.get("supervisor_id") || null,
                    work_item_ids: d.getAll("work_item_ids"),
                  }),
                )
              }
            >
              <p>
                {tr(
                  "Choose who works this shift. Team work items are included; a supervisor can coordinate their reports.",
                )}
              </p>
              {people.map((p) => (
                <label className="checkbox-label" key={p.id}>
                  <input
                    type="checkbox"
                    name="user_ids"
                    value={p.id}
                    defaultChecked={data.assignments?.some(
                      (a) => a.shift_id === s.id && a.user_id === p.id,
                    )}
                  />
                  {p.name} ·{" "}
                  {p.role === "operator"
                    ? tr("Shift worker")
                    : p.role === "quality"
                      ? tr("Authorized reviewer")
                      : tr("Shift supervisor")}
                </label>
              ))}
              <fieldset>
                <legend>{tr("Assigned work")}</legend>
                {items
                  .filter((i) => i.team_id === s.team_id)
                  .map((i) => (
                    <CheckboxRow
                      key={i.id}
                      name="work_item_ids"
                      value={i.id}
                      defaultChecked={
                        !data.assignments?.some(
                          (a) => a.shift_id === s.id && a.work_item_ids.length,
                        ) ||
                        data.assignments?.some(
                          (a) =>
                            a.shift_id === s.id &&
                            a.work_item_ids.includes(i.id),
                        )
                      }
                    >
                      {i.id} · {i.name}
                    </CheckboxRow>
                  ))}
                <small>
                  {tr(
                    "Leave all work unchecked to include all work assigned to this team.",
                  )}
                </small>
              </fieldset>
              <label>
                {tr("Shift supervisor")}
                <Select
                  name="supervisor_id"
                  defaultValue={s.supervisor_id || ""}
                >
                  <option value="">{tr("No supervisor selected")}</option>
                  {people
                    .filter(
                      (p) =>
                        p.role === "supervisor" ||
                        (p.id === ownId && p.role === "quality"),
                    )
                    .map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.name}
                      </option>
                    ))}
                </Select>
              </label>
              <button className="button-orange" disabled={busy}>
                {tr("Save shift assignments")}
              </button>
            </form>
            <form
              className="platform-form"
              onSubmit={(e) =>
                submit(e, "/shift-occurrences/" + s.id + "/incoming", (d) =>
                  Object.fromEntries(d),
                )
              }
            >
              <h3>{tr("Next shift")}</h3>
              <label>
                {tr("Incoming shift")}
                <Select
                  name="incoming_shift_id"
                  required
                  defaultValue={s.incoming_shift_id || ""}
                >
                  <option value="">{tr("Choose incoming shift")}</option>
                  {data.shifts
                    .filter((next) => next.id !== s.id)
                    .map((next) => (
                      <option key={next.id} value={next.id}>
                        {next.name} ·{" "}
                        {next.starts_at
                          ? new Date(next.starts_at).toLocaleString(locale(), {
                              timeZone: org.timezone,
                              timeZoneName: "short",
                            })
                          : next.id}
                      </option>
                    ))}
                </Select>
              </label>
              <label>
                {tr("Reason")}
                <input
                  name="reason"
                  required
                  minLength={3}
                  placeholder={tr("Evening team receives outstanding work")}
                />
              </label>
              <button
                className="button-outline"
                disabled={busy || s.status === "closed"}
              >
                {tr("Set incoming shift")}
              </button>
            </form>
            {s.status !== "closed" && (
              <form
                className="platform-form"
                onSubmit={(e) => {
                  if (
                    !confirm(
                      tr(
                        "Close this shift and preserve its handover? Outstanding conditions must remain visible to the incoming team.",
                      ),
                    )
                  ) {
                    e.preventDefault();
                    return;
                  }
                  void submit(
                    e,
                    "/shift-occurrences/" + s.id + "/close",
                    (d) => ({ reason: d.get("reason") }),
                  );
                }}
              >
                <label>
                  {tr("Closing note")}
                  <input name="reason" required minLength={3} />
                </label>
                <button
                  className="button-outline"
                  disabled={busy || !s.incoming_shift_id}
                >
                  {tr("Close shift and hand over")}
                </button>
              </form>
            )}
          </details>
        ))}
    </section>
  );
}
