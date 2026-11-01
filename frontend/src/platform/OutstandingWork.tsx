import { tr, systemText } from "../i18n";
import type { Batch } from "../types";
import { Panel, ScrollArea } from "../components/OperationalUI";
export default function OutstandingWork({
  batches,
  open,
}: {
  batches: Batch[];
  open: (id: string) => void;
}) {
  const outstanding = batches.filter(
    (b) =>
      b.status !== "verified" &&
      (b.readiness_reasons?.length ||
        b.tasks.some((t) => t.status !== "completed")),
  );
  return (
    <Panel
      title={tr("Outstanding work")}
      description={tr("Start with the unresolved items.")}
      className="outstanding-work"
    >
      <ScrollArea label={tr("Outstanding work")}>
      {!outstanding.length ? (
        <p>
          {tr(
            "No outstanding reports yet. Record an update to see what needs attention.",
          )}
        </p>
      ) : (
        outstanding.map((b) => (
          <article key={b.id} className="reason-row">
            <strong>
              {b.id} · {b.name}
            </strong>
            <p>
              {b.readiness_reasons?.[0]?.code === "task"
                ? b.readiness_reasons[0].text
                : systemText(b.readiness_reasons?.[0]?.text || "")}
            </p>
            <button className="text-button" onClick={() => open(b.id)}>
              {tr("Open work item")}
            </button>
          </article>
        ))
      )}
      </ScrollArea>
    </Panel>
  );
}
