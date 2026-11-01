import { Select } from "../components/Select";
import { useEffect, useState } from "react";
import { tr, msg } from "../i18n";
import { call, type Organization } from "./client";
import type { Workspace } from "../types";
import type { Operations } from "./OperationsSetup";
import { organizationInstant } from "./timezone";
import PilotPolicy from "./PilotPolicy";
import TeamPage from "./TeamPage";
import { Panel } from "../components/OperationalUI";
type Progress = {
  step: number;
  locationId?: string;
  teamId?: string;
  itemId?: string;
  shiftId?: string;
  done?: boolean;
};
export default function SetupWizard({
  org,
  userId,
  refresh,
  finish,
}: {
  org: Organization;
  userId: string;
  refresh: () => Promise<unknown>;
  finish: () => void;
  openTeam: () => void;
}) {
  const key = `shiftproof.setup.v1:${userId}:${org.id}`,
    base = "/organizations/" + org.id;
  const [progress, setProgress] = useState<Progress>(() => {
    try {
      const p = JSON.parse(localStorage.getItem(key) || "{}");
      return {
        ...p,
        step:
          Number.isInteger(p.step) && p.step >= 0 && p.step < 5 ? p.step : 0,
      };
    } catch {
      return { step: 0 };
    }
  });
  const [ops, setOps] = useState<Operations | null>(null),
    [items, setItems] = useState<Workspace["batches"]>([]),
    [people, setPeople] = useState<
      { id: string; name: string; role: string }[]
    >([]),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [policySaved, setPolicySaved] = useState(false);
  function save(p: Partial<Progress>) {
    setProgress((old) => {
      const next = { ...old, ...p };
      try {
        localStorage.setItem(key, JSON.stringify(next));
      } catch {
        /* Resources remain saved on the server. */
      }
      return next;
    });
  }
  async function load() {
    const [o, w, p] = await Promise.all([
      call<Operations>(base + "/operations"),
      call<Workspace>(base + "/workspace"),
      call<typeof people>(base + "/directory"),
    ]);
    setOps(o);
    setItems(w.batches);
    setPeople(p);
    return { o, w };
  }
  useEffect(() => {
    if (org.profile.status !== "available") return;
    load().catch((e) => setError(e.message));
    call<{ policy: { mode?: string } }>(base + "/pilot-policy")
      .then((r) => setPolicySaved(!!r.policy.mode))
      .catch((e) => setError(e.message));
  }, [org.id]);
  async function act(fn: () => Promise<unknown>) {
    setBusy(true);
    setError("");
    try {
      await fn();
      await load();
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const d = Object.fromEntries(new FormData(e.currentTarget));
    await act(async () => {
      const { o, w } = await load();
      if (progress.step === 0) {
        if (d.org_name !== org.name)
          await call(
            base + "/settings",
            { name: d.org_name, timezone: org.timezone },
            "PUT",
          );
        let id = String(d.location_id || progress.locationId || "");
        if (!id) {
          const found = o.locations.find((l) => l.name === d.location_name);
          id =
            found?.id ||
            (
              await call<{ id: string }>(base + "/locations", {
                name: d.location_name,
              })
            ).id;
          save({ locationId: id });
        }
        save({
          locationId: id,
          step: 1,
          ...(progress.locationId && progress.locationId !== id
            ? { teamId: undefined, itemId: undefined, shiftId: undefined }
            : {}),
        });
      } else if (progress.step === 1) {
        const locationId = String(d.location_id || progress.locationId || "");
        let teamId = String(d.team_id || progress.teamId || "");
        if (!teamId) {
          teamId =
            o.teams.find(
              (t) => t.name === d.team_name && t.location_id === locationId,
            )?.id ||
            (
              await call<{ id: string }>(base + "/teams", {
                name: d.team_name,
                location_id: locationId,
              })
            ).id;
          save({ teamId });
        }
        const chosenTeam = o.teams.find((t) => t.id === teamId);
        if (chosenTeam && chosenTeam.location_id !== locationId)
          throw new Error("Choose a team in this location");
        let itemId = String(d.item_id || progress.itemId || "");
        if (
          itemId &&
          w.batches.find((i) => i.id === itemId)?.team_id !== teamId
        )
          throw new Error("Choose a work item assigned to this team.");
        if (!itemId) {
          const existing = w.batches.find((i) => i.id === d.identifier);
          if (existing) {
            if (existing.team_id !== teamId)
              throw new Error("Choose a work item assigned to this team.");
            itemId = existing.id;
          } else {
            await call(base + "/work-items", {
              id: d.identifier,
              name: d.item_name,
              line: "",
              location_id: locationId,
              team_id: teamId,
              target: 0,
            });
            itemId = String(d.identifier);
          }
          save({ itemId });
        }
        save({ teamId, locationId, itemId, step: 2 });
      } else if (progress.step === 2) {
        let shiftId = String(d.shift_id || progress.shiftId || "");
        const team = o.teams.find((t) => t.id === progress.teamId);
        if (!team) throw new Error("Choose a team first.");
        if (!shiftId) {
          const body = {
            name: d.shift_name,
            location_id: team.location_id,
            team_id: team.id,
            starts_at: organizationInstant(String(d.starts_at), org.timezone),
            ends_at: organizationInstant(String(d.ends_at), org.timezone),
          };
          shiftId =
            o.shifts.find(
              (s) =>
                s.name === body.name &&
                s.team_id === body.team_id &&
                new Date(s.starts_at || 0).getTime() ===
                  new Date(body.starts_at).getTime(),
            )?.id ||
            (await call<{ id: string }>(base + "/shift-occurrences", body)).id;
          save({ shiftId });
        }
        const previous =
          o.assignments?.filter((a) => a.shift_id === shiftId) || [];
        await call(
          base + "/shift-occurrences/" + shiftId + "/assignments",
          {
            user_ids: Array.from(
              new Set([
                ...previous.map((a) => a.user_id),
                String(d.supervisor_id),
              ]),
            ),
            supervisor_id: d.supervisor_id,
            work_item_ids: Array.from(
              new Set([
                ...previous.flatMap((a) => a.work_item_ids),
                ...(progress.itemId ? [progress.itemId] : []),
              ]),
            ),
          },
          "PUT",
        );
        save({ shiftId, step: 3 });
      }
    });
  }
  const locationId = progress.locationId || ops?.locations[0]?.id;
  const availableTeams =
    ops?.teams.filter((t) => t.location_id === locationId) || [];
  const selectedTeam =
    availableTeams.find((t) => t.id === progress.teamId)?.id ||
    availableTeams[0]?.id;
  const availableItems = items.filter((i) => i.team_id === selectedTeam);
  const titles = [
    tr("Workplace"),
    tr("Team and work"),
    tr("First shift"),
    tr("People"),
    tr("Recording setup"),
  ];
  if (org.profile.status !== "available")
    return (
      <Panel title={tr("Workflow preview")}>
        <p>
          {tr(
            "This industry is a preview. You can manage your team; operational setup is not available yet.",
          )}
        </p>
        <button className="button-outline" onClick={finish}>
          {tr("Finish later")}
        </button>
      </Panel>
    );
  return (
    <div className="setup-wizard">
      <div className="setup-progress" aria-label={tr("Setup progress")}>
        {titles.map((t, i) => (
          <span key={i} aria-current={progress.step === i ? "step" : undefined}>
            <b>{i + 1}</b>
            {t}
          </span>
        ))}
      </div>
      <div className="setup-intro">
        <p>{msg("Step {step} of 5", { step: String(progress.step + 1) })}</p>
        <button className="text-button" onClick={finish} disabled={busy}>
          {tr("Finish later")}
        </button>
      </div>
      {error && (
        <p className="platform-error" role="alert">
          {tr(error)}
        </p>
      )}
      {!ops ? (
        <p role="status">{tr("Loading…")}</p>
      ) : progress.step < 3 ? (
        <Panel
          title={titles[progress.step]}
          description={tr("Your saved details stay here when you return.")}
        >
          <form key={progress.step} className="platform-form" onSubmit={submit}>
            {progress.step === 0 && (
              <>
                <label>
                  {tr("Workspace name")}
                  <input
                    name="org_name"
                    defaultValue={org.name}
                    required
                    minLength={2}
                  />
                </label>
                {ops.locations.length ? (
                  <label>
                    {tr("Location")}
                    <Select
                      name="location_id"
                      defaultValue={progress.locationId || ops.locations[0]?.id}
                    >
                      {ops.locations.map((l) => (
                        <option key={l.id} value={l.id}>
                          {l.name}
                        </option>
                      ))}
                    </Select>
                  </label>
                ) : (
                  <label>
                    {tr("Location name")}
                    <input
                      name="location_name"
                      placeholder={tr("Packing floor")}
                      required
                      minLength={2}
                    />
                  </label>
                )}
              </>
            )}
            {progress.step === 1 && (
              <>
                <p>
                  {tr("Location")}:{" "}
                  {ops.locations.find((l) => l.id === locationId)?.name}
                </p>
                <input
                  type="hidden"
                  name="location_id"
                  value={locationId || ""}
                />
                {availableTeams.length ? (
                  <label>
                    {tr("Team")}
                    <Select
                      name="team_id"
                      value={selectedTeam || ""}
                      onChange={(e) =>
                        save({
                          teamId: e.target.value,
                          itemId: undefined,
                          shiftId: undefined,
                        })
                      }
                    >
                      {availableTeams.map((t) => (
                        <option key={t.id} value={t.id}>
                          {t.name}
                        </option>
                      ))}
                    </Select>
                  </label>
                ) : (
                  <label>
                    {tr("Team name")}
                    <input name="team_name" required minLength={2} />
                  </label>
                )}
                {availableItems.length ? (
                  <label>
                    {tr(org.profile.item)}
                    <Select
                      name="item_id"
                      defaultValue={progress.itemId || availableItems[0]?.id}
                    >
                      {availableItems.map((i) => (
                        <option key={i.id} value={i.id}>
                          {i.id} · {i.name}
                        </option>
                      ))}
                    </Select>
                  </label>
                ) : (
                  <>
                    <label>
                      {tr("Identifier")}
                      <input
                        name="identifier"
                        pattern="[A-Za-z0-9][A-Za-z0-9_-]*"
                        required
                        maxLength={64}
                        placeholder="BATCH-01"
                      />
                    </label>
                    <label>
                      {tr("Work item name")}
                      <input name="item_name" required minLength={2} />
                    </label>
                  </>
                )}
              </>
            )}
            {progress.step === 2 && (
              <>
                <p>
                  {tr("Times use your organization timezone.")} {org.timezone}
                </p>
                {ops.shifts.filter(
                  (s) => s.team_id === progress.teamId && s.status !== "closed",
                ).length ? (
                  <label>
                    {tr("Shift")}
                    <Select name="shift_id" defaultValue={progress.shiftId}>
                      {ops.shifts
                        .filter(
                          (s) =>
                            s.team_id === progress.teamId &&
                            s.status !== "closed",
                        )
                        .map((s) => (
                          <option key={s.id} value={s.id}>
                            {s.name}
                          </option>
                        ))}
                    </Select>
                  </label>
                ) : (
                  <>
                    <label>
                      {tr("Shift name")}
                      <input name="shift_name" minLength={2} required />
                    </label>
                    <label>
                      {tr("Starts")}
                      <input type="datetime-local" name="starts_at" required />
                    </label>
                    <label>
                      {tr("Ends")}
                      <input type="datetime-local" name="ends_at" required />
                    </label>
                  </>
                )}
                <label>
                  {tr("Shift supervisor")}
                  <Select name="supervisor_id" required defaultValue={userId}>
                    {people
                      .filter(
                        (p) =>
                          p.role === "supervisor" ||
                          (p.id === userId && p.role === "quality"),
                      )
                      .map((p) => (
                        <option key={p.id} value={p.id}>
                          {p.name}
                        </option>
                      ))}
                  </Select>
                </label>
                <p>
                  {tr("Assigned work")}: {progress.itemId}
                </p>
              </>
            )}
            <button className="button-orange" disabled={busy}>
              {busy ? tr("Saving…") : tr("Save and continue")}
            </button>
          </form>
        </Panel>
      ) : progress.step === 3 ? (
        <>
          <p>
            {tr(
              "Invited people are not active members yet. After they join, assign them to a shift in Settings.",
            )}
          </p>
          <TeamPage org={org} currentUser={userId} act={act} busy={busy} />
          <button className="button-outline" onClick={() => save({ step: 4 })}>
            {tr("Continue to recording setup")}
          </button>
        </>
      ) : (
        <>
          <PilotPolicy
            org={org}
            changed={async () => {
              await refresh();
              setPolicySaved(true);
            }}
          />
          <button
            className="button-outline"
            disabled={!policySaved}
            onClick={() => {
              save({ done: true });
              finish();
            }}
          >
            {tr("Finish setup")}
          </button>
        </>
      )}
      <div className="button-row">
        {progress.step > 0 && (
          <button
            className="button-outline"
            disabled={busy}
            onClick={() => save({ step: progress.step - 1 })}
          >
            {tr("Back")}
          </button>
        )}
      </div>
    </div>
  );
}
