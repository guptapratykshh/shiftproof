// Enabled only by the private measurement harness. No storage or network telemetry.
export function studyMark(
  event: string,
  details: Record<string, unknown> = {},
) {
  if (!(window as Window & { __shiftproofStudy?: boolean }).__shiftproofStudy)
    return;
  window.dispatchEvent(
    new CustomEvent("shiftproof:study", {
      detail: { event, at_ms: performance.now(), ...details },
    }),
  );
}
