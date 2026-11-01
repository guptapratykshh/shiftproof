// Convert an entered wall-clock time in the organization zone, independent of device timezone.
// Reject DST gaps and duplicate wall-clock times instead of silently selecting an instant.
export function organizationInstant(local: string, timeZone: string): string {
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(local))
    throw new Error("Choose a complete date and time.");
  const nominal = Date.parse(local + ":00Z");
  const formatter = new Intl.DateTimeFormat("en-CA", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  });
  const wall = (instant: number) => {
    const p = Object.fromEntries(
      formatter.formatToParts(new Date(instant)).map((p) => [p.type, p.value]),
    );
    return `${p.year}-${p.month}-${p.day}T${p.hour}:${p.minute}`;
  };
  const candidates = new Set<number>();
  // Modern IANA UTC offsets are minute-granular. This also detects DST overlap explicitly.
  for (let offset = -14 * 60; offset <= 14 * 60; offset++) {
    const instant = nominal + offset * 60000;
    if (wall(instant) === local) candidates.add(instant);
  }
  if (candidates.size !== 1)
    throw new Error(
      candidates.size
        ? "This local time occurs twice because of daylight saving. Choose an unambiguous start/end time."
        : "This local time does not exist in the organization timezone. Choose another time.",
    );
  return new Date([...candidates][0]).toISOString();
}
