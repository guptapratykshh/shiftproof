import { useState } from "react";
import { tr } from "../i18n";
import { call, type Organization } from "./client";
import OperationsSetup from "./OperationsSetup";
import PilotPolicy from "./PilotPolicy";
import { Dialog, Panel, SectionTabs } from "../components/OperationalUI";
export const settingsSections = [
  "general",
  "places",
  "shifts",
  "recording",
  "downloads",
];
export default function Settings({
  org,
  refresh,
  act,
  busy,
  section,
  onSection,
}: {
  org: Organization;
  refresh: () => Promise<unknown>;
  act: (fn: () => Promise<unknown>) => Promise<void>;
  busy: boolean;
  section: string;
  onSection: (s: string) => void;
}) {
  const [edit, setEdit] = useState(false);
  return (
    <div className="settings-page">
      <SectionTabs
        label={tr("Organization settings")}
        value={section}
        onChange={onSection}
        options={[
          { id: "general", label: tr("General") },
          {
            id: "places",
            label: tr("Locations & teams"),
            disabled: org.profile.status !== "available",
          },
          {
            id: "shifts",
            label: tr("Shifts"),
            disabled: org.profile.status !== "available",
          },
          {
            id: "recording",
            label: tr("Recording & data"),
            disabled: org.profile.status !== "available",
          },
          {
            id: "downloads",
            label: tr("Downloads"),
            disabled: org.profile.status !== "available",
          },
        ]}
      />
      {section !== "general" && org.profile.status !== "available" && (
        <Panel title={tr("Workflow preview")}>
          <p>
            {tr(
              "This industry is a preview. You can manage your team; operational setup is not available yet.",
            )}
          </p>
        </Panel>
      )}
      {section === "general" && (
        <Panel
          title={tr("Workspace details")}
          description={tr("The name your team sees when they sign in.")}
          actions={
            <button className="button-outline" onClick={() => setEdit(true)}>
              {tr("Edit")}
            </button>
          }
        >
          <dl className="detail-list">
            <div>
              <dt>{tr("Workspace name")}</dt>
              <dd>{org.name}</dd>
            </div>
            <div>
              <dt>{tr("Organization type")}</dt>
              <dd>{tr(org.profile.name)}</dd>
            </div>
          </dl>
          <p>
            {tr(
              "Industry is fixed for this workspace so existing reports retain their meaning.",
            )}
          </p>
          <details>
            <summary>{tr("Advanced settings")}</summary>
            <p>
              {tr("Display timezone")}: {org.timezone}
            </p>
            <button className="text-button" onClick={() => setEdit(true)}>
              {tr("Edit timezone")}
            </button>
          </details>
        </Panel>
      )}
      {org.profile.status === "available" && section === "places" && (
        <OperationsSetup org={org} changed={refresh} section="places" />
      )}
      {org.profile.status === "available" && section === "shifts" && (
        <OperationsSetup org={org} changed={refresh} section="shifts" />
      )}
      {section === "recording" && <PilotPolicy org={org} changed={refresh} />}
      {org.profile.status === "available" && section === "downloads" && (
        <Panel
          title={tr("Download organization data")}
          description={tr(
            "Export includes records and evidence references; audio files remain available through authenticated playback.",
          )}
        >
          <button
            className="button-orange"
            disabled={busy || org.profile.status !== "available"}
            onClick={() =>
              void act(async () => {
                const data = await call("/organizations/" + org.id + "/export");
                const url = URL.createObjectURL(
                  new Blob([JSON.stringify(data, null, 2)], {
                    type: "application/json",
                  }),
                );
                const a = document.createElement("a");
                a.href = url;
                a.download = "shiftproof-" + org.id + ".json";
                a.click();
                setTimeout(() => URL.revokeObjectURL(url), 1000);
              })
            }
          >
            {tr("Download organization data")}
          </button>
        </Panel>
      )}
      {edit && (
        <Dialog title={tr("Workspace details")} close={() => setEdit(false)}>
          <form
            className="platform-form"
            onSubmit={(e) => {
              e.preventDefault();
              const data = Object.fromEntries(new FormData(e.currentTarget));
              void act(async () => {
                await call(
                  "/organizations/" + org.id + "/settings",
                  data,
                  "PUT",
                );
                await refresh();
                setEdit(false);
              });
            }}
          >
            <label>
              {tr("Workspace name")}
              <input
                name="name"
                defaultValue={org.name}
                minLength={2}
                maxLength={120}
                required
              />
            </label>
            <details>
              <summary>{tr("Advanced settings")}</summary>
              <label>
                {tr("Display timezone")}
                <input name="timezone" defaultValue={org.timezone} required />
              </label>
            </details>
            <button className="button-orange" disabled={busy}>
              {tr("Save workspace details")}
            </button>
          </form>
        </Dialog>
      )}
    </div>
  );
}
