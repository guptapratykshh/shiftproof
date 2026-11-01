const KEY = "shiftproof-offline-capture-context-v1";
export type OfflineContext = {
  userId: string;
  userName: string;
  reportedById?: string;
  reportedByName?: string;
  organizationId: string;
  organizationName: string;
  cachedAt: string;
  expiresAt: string;
  activeShiftId: string;
  items: { id: string; name: string }[];
  shifts: { id: string; name: string; starts_at?: string; ends_at?: string }[];
};
export function saveOfflineContext(
  context: Omit<OfflineContext, "cachedAt" | "expiresAt">,
) {
  const value: OfflineContext = {
    ...context,
    items: context.items.slice(0, 100),
    shifts: context.shifts.slice(0, 30),
    cachedAt: new Date().toISOString(),
    expiresAt: new Date(Date.now() + 72 * 3600000).toISOString(),
  };
  try {
    localStorage.setItem(KEY, JSON.stringify(value));
  } catch {
    /* Current capture still works when browser storage is unavailable. */
  }
}
export function readOfflineContext(
  organizationId?: string,
): OfflineContext | null {
  try {
    const value = JSON.parse(
      localStorage.getItem(KEY) || "null",
    ) as OfflineContext | null;
    if (
      !value ||
      typeof value.userId !== "string" ||
      typeof value.organizationId !== "string" ||
      !Array.isArray(value.items) ||
      !Array.isArray(value.shifts) ||
      !value.activeShiftId ||
      !Number.isFinite(Date.parse(value.expiresAt)) ||
      Date.parse(value.expiresAt) < Date.now()
    )
      return null;
    if (organizationId && value.organizationId !== organizationId) return null;
    return value;
  } catch {
    return null;
  }
}
export function clearOfflineContext() {
  try {
    localStorage.removeItem(KEY);
  } catch {}
}
