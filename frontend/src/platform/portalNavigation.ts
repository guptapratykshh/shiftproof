export const portalPages = [
  "home",
  "work",
  "reports",
  "overview",
  "capture",
  "mywork",
  "handover",
  "team",
  "settings",
  "setup",
];
export const portalSections = [
  "general",
  "places",
  "shifts",
  "recording",
  "downloads",
];
export function readPortalRoute() {
  const q = new URLSearchParams(location.search);
  const page = q.get("view") || "overview",
    section = q.get("section") || "general";
  return {
    page: portalPages.includes(page) ? page : "overview",
    section: portalSections.includes(section) ? section : "general",
  };
}
export function portalUrl(page: string, section = "general") {
  const u = new URL(location.href);
  u.searchParams.set("view", portalPages.includes(page) ? page : "overview");
  if (page === "settings")
    u.searchParams.set(
      "section",
      portalSections.includes(section) ? section : "general",
    );
  else u.searchParams.delete("section");
  return u.pathname + u.search;
}
