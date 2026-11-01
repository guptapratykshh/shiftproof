import { tr, locale } from "../i18n";
import type { Organization } from "./client";
export type Member = {
  id: string;
  name: string;
  email: string | null;
  employee_id?: string | null;
  role: Organization["role"];
  access: Organization["access"];
};
export const formatTime = (value: string | number, timezone: string) =>
  new Date(value).toLocaleString(locale(), {
    timeZone: timezone,
    timeZoneName: "short",
  });
export const label = (s: string) => tr(s.replaceAll("_", " "));
export const roleLabel = (s: string) =>
  tr(
    s === "quality"
      ? "Authorized reviewer"
      : s === "supervisor"
        ? "Shift supervisor"
        : "Shift worker",
  );
export const accessLabel = (s: string) =>
  tr(
    s === "owner"
      ? "Organization owner"
      : s === "admin"
        ? "Administrator"
        : "Team member",
  );

export const statusLabel = (s: string) =>
  tr(
    {
      draft: "Reported - needs review",
      confirmed: "Human-reviewed",
      verified: "Requirements reviewed",
      hold: "Unresolved hold",
      review: "Needs review",
      unknown: "No reports",
    }[s] || label(s),
  );
