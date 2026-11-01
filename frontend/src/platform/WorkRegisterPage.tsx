import { Select } from "../components/Select";
import { statusLabel } from "./workspaceLabels";
import OutstandingWork from "./OutstandingWork";
import { ScrollArea } from "../components/OperationalUI";
import { tr, msg } from "../i18n";
import { Mic, Plus, ClipboardCheck, Search } from "lucide-react";
import { useWorkspace } from "./WorkspaceContext";
export default function WorkRegisterPage({
  compact = false,
}: {
  compact?: boolean;
}) {
  const {
    org,
    view,
    setSelected,
    setPage,
    operations,
    search,
    setSearch,
    statusFilter,
    setStatusFilter,
    t,
    reasonText,
    setShowItem,
    setEditingItem,
    navigate,
    clearCapture,
    reviewer,
    canManageWork,
    admin,
  } = useWorkspace();
  return (
    <>
      <div className="section-row">
        <h2>
          {msg("Your {items}", {
            items: tr(
              org.profile.item === "Batch" ? "Batches" : org.profile.item + "s",
            ),
          })}
        </h2>
        <button
          className="button-outline"
          onClick={() => navigate(() => setPage("capture"))}
        >
          <Mic size={17} />
          {tr("Add voice note")}
        </button>
        {canManageWork && (
          <button
            className="button-dark"
            onClick={() => {
              setEditingItem(false);
              setShowItem(true);
            }}
          >
            <Plus size={16} />{" "}
            {msg("Add {item}", {
              item: tr(org.profile.item.toLowerCase()),
            })}
          </button>
        )}
      </div>
      {view.batches.length === 0 && (
        <div className="platform-panel empty-workspace">
          <ClipboardCheck size={36} />
          <h2>
            {msg("Start with your first {item}.", {
              item: tr(org.profile.item.toLowerCase()),
            })}
          </h2>
          <p>
            {tr("This workspace contains no fictional reports.")}{" "}
            {reviewer
              ? tr("Create a work item, then record an update.")
              : tr("Ask your supervisor to create a work item.")}
          </p>
          {admin && (
            <button
              className="button-outline"
              onClick={() => setPage("settings")}
            >
              {tr("Configure locations, teams and shifts")}
            </button>
          )}
        </div>
      )}
      <div className={"overview-work-grid" + (compact ? " register-only" : "")}>
        <section className="work-register platform-panel">
          <div className="register-heading">
            <h2>{msg("{item} register", { item: tr(org.profile.item) })}</h2>
            <p>{tr("The latest reports, with nothing left behind.")}</p>
          </div>
          <div className="register-filters">
            <label>
              <Search size={16} />
              <input
                aria-label={tr("Search work items")}
                placeholder={tr("Search work items…")}
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </label>
            <Select
              aria-label={tr("Filter status")}
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
            >
              <option value="all">{tr("All statuses")}</option>
              <option value="hold">{tr("On hold")}</option>
              <option value="review">{tr("Needs review")}</option>
              <option value="verified">{tr("Requirements reviewed")}</option>
              <option value="unknown">{tr("No reports")}</option>
            </Select>
          </div>
          <ScrollArea label={t("काम की सूची", "Work register")}>
            <div className="item-register">
              {view.batches
                .filter(
                  (b) =>
                    (b.id + " " + b.name + " " + b.line)
                      .toLowerCase()
                      .includes(search.toLowerCase()) &&
                    (statusFilter === "all" || b.status === statusFilter),
                )
                .map((b) => (
                  <button
                    className="item-card"
                    key={b.id}
                    onClick={() =>
                      navigate(() => {
                        setSelected(b.id);
                        setPage("capture");
                        clearCapture();
                      })
                    }
                  >
                    <div>
                      <span>
                        {b.id} ·{" "}
                        {b.line ||
                          operations?.locations.find(
                            (l) => l.id === b.location_id,
                          )?.name ||
                          tr("Location unassigned")}
                      </span>
                      
                    </div>
                    <h3>{b.name}</h3>
                    <span className={"state-tag " + b.status}>
                      {statusLabel(b.status)}
                    </span>
                    <p>
                      {(b.readiness_reasons?.[0]
                        ? reasonText(b.readiness_reasons[0])
                        : "") || tr("Open this item to inspect the evidence.")}
                    </p>
                    <footer>
                      {b.claims.length} {tr("active reports ·")}{" "}
                      {b.tasks.filter((t) => t.status === "open").length}{" "}
                      {tr("open tasks")}
                    </footer>
                  </button>
                ))}
            </div>
          </ScrollArea>
        </section>
        {!compact && (
          <OutstandingWork
            batches={view.batches}
            open={(id) =>
              navigate(() => {
                setSelected(id);
                setPage("capture");
                clearCapture();
              })
            }
          />
        )}
      </div>
    </>
  );
}
