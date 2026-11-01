import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { tr } from "../i18n";
import "./ScrollArea.css";

export function ScrollArea({ label, children }: { label: string; children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  const [overflow, setOverflow] = useState(false);
  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    const measure = () => setOverflow(node.scrollHeight > node.clientHeight + 1);
    const observer = new ResizeObserver(measure);
    observer.observe(node);
    if (node.firstElementChild) observer.observe(node.firstElementChild);
    measure();
    return () => observer.disconnect();
  }, []);
  return <div ref={ref} className="content-scroll" role="region" aria-label={label} tabIndex={overflow ? 0 : undefined}>
    <div className="content-scroll-body">{children}</div>
  </div>;
}
export function Dialog({
  title,
  close,
  children,
}: {
  title: string;
  close: () => void;
  children: React.ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const dialog = ref.current;
    dialog?.showModal();
    return () => {
      dialog?.close();
      previous?.focus();
    };
  }, []);
  return (
    <dialog
      ref={ref}
      className="platform-dialog"
      onCancel={close}
      aria-labelledby={titleId}
    >
      <header>
        <h2 id={titleId}>{title}</h2>
        <button aria-label={tr("Close dialog")} onClick={close}>
          ×
        </button>
      </header>
      {children}
    </dialog>
  );
}

export function Panel({
  title,
  description,
  actions,
  children,
  className = "",
}: {
  title?: string;
  description?: string;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={"platform-panel " + className}>
      {title && (
        <div className="panel-heading">
          <div>
            <h2>{title}</h2>
            {description && <p>{description}</p>}
          </div>
          {actions}
        </div>
      )}
      {children}
    </section>
  );
}
export function SectionTabs({
  label,
  options,
  value,
  onChange,
}: {
  label: string;
  options: { id: string; label: string; disabled?: boolean }[];
  value: string;
  onChange: (id: string) => void;
}) {
  return (
    <nav className="section-tabs" aria-label={label}>
      {options.map((o) => (
        <button
          key={o.id}
          disabled={o.disabled}
          type="button"
          aria-current={value === o.id ? "page" : undefined}
          onClick={() => onChange(o.id)}
        >
          {o.label}
        </button>
      ))}
    </nav>
  );
}
export function CheckboxRow({
  children,
  ...props
}: React.InputHTMLAttributes<HTMLInputElement> & { children: ReactNode }) {
  return (
    <label className="checkbox-row">
      <input {...props} type="checkbox" />
      <span>{children}</span>
    </label>
  );
}

export function PageHeader({
  title,
  description,
  eyebrow,
  actions,
  className = "workspace-heading",
}: {
  title: string;
  description: string;
  eyebrow?: ReactNode;
  actions?: ReactNode;
  className?: string;
}) {
  return (
    <header className={className}>
      <div>
        {eyebrow}
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      {actions}
    </header>
  );
}
export function SummaryStat({
  label,
  value,
  caption,
  icon,
  color = "neutral",
}: {
  label: string;
  value: number;
  caption?: string;
  icon?: ReactNode;
  color?: string;
}) {
  return (
    <div className={"stat " + color}>
      <div className="stat-top">
        <span>{label}</span>
        {icon && <span className="stat-icon">{icon}</span>}
      </div>
      <strong className="stat-value">{String(value).padStart(2, "0")}</strong>
      {caption && <p>{caption}</p>}
    </div>
  );
}
