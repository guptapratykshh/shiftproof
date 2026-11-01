import {
  Children,
  isValidElement,
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
  type ReactNode,
  type SelectHTMLAttributes,
} from "react";
import { createPortal } from "react-dom";
import { Check, ChevronDown } from "lucide-react";
import { bilingual as t } from "../i18n";
import "./Select.css";

type Option = { value: string; label: string; disabled: boolean };
function text(node: ReactNode): string {
  return Children.toArray(node)
    .map((child) =>
      isValidElement<{ children?: ReactNode }>(child)
        ? text(child.props.children)
        : String(child),
    )
    .join("");
}
function optionsFrom(children: ReactNode, disabled = false): Option[] {
  return Children.toArray(children).flatMap((child) => {
    if (
      !isValidElement<{
        children?: ReactNode;
        value?: string | number;
        disabled?: boolean;
      }>(child)
    )
      return [];
    const props = child.props;
    if (child.type === "option")
      return [
        {
          value: String(props.value ?? text(props.children)),
          label: text(props.children),
          disabled: disabled || !!props.disabled,
        },
      ];
    return optionsFrom(props.children, disabled || !!props.disabled);
  });
}

/** A styled, select-only combobox. The hidden select preserves native FormData
 * and constraint validation, while every user interaction uses the listbox. */
export function Select({
  children,
  className = "",
  id,
  ...props
}: SelectHTMLAttributes<HTMLSelectElement>) {
  const uid = useId();
  const listId = `${uid}-options`;
  const root = useRef<HTMLSpanElement>(null);
  const native = useRef<HTMLSelectElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const menu = useRef<HTMLDivElement>(null);
  const search = useRef({ value: "", at: 0 });
  const [open, setOpen] = useState(false);
  const [invalid, setInvalid] = useState(false);
  const [active, setActive] = useState(0);
  const [value, setValue] = useState(
    String(props.value ?? props.defaultValue ?? ""),
  );
  const [position, setPosition] = useState({
    left: 0,
    top: 0,
    width: 0,
    maxHeight: 280,
  });
  const options = optionsFrom(children);
  const selected = options.findIndex((option) => option.value === value);
  useLayoutEffect(() => {
    if (native.current) setValue(native.current.value);
  });
  const close = () => setOpen(false);
  function show() {
    if (props.disabled) return;
    // Safari does not focus buttons on pointer clicks. Keyboard navigation and
    // Escape must still reach this select after opening it with a mouse/touch.
    trigger.current?.focus({ preventScroll: true });
    setActive(
      selected >= 0 && !options[selected].disabled
        ? selected
        : options.findIndex((option) => !option.disabled),
    );
    setOpen(true);
  }
  function choose(index: number) {
    const option = options[index];
    if (!option || option.disabled || !native.current) return;
    if (native.current.value !== option.value) {
      native.current.value = option.value;
      native.current.dispatchEvent(new Event("change", { bubbles: true }));
    }
    setValue(native.current.value);
    close();
    trigger.current?.focus();
  }
  useLayoutEffect(() => {
    if (!open) return;
    const place = () => {
      const r = trigger.current!.getBoundingClientRect();
      const below = window.innerHeight - r.bottom - 12;
      const above = r.top - 12;
      const up = below < 180 && above > below;
      const maxHeight = Math.max(44, Math.min(280, up ? above : below));
      const height = Math.min(maxHeight, options.length * 44 + 12);
      const width = Math.min(Math.max(r.width, 220), window.innerWidth - 24);
      setPosition({
        left: Math.max(12, Math.min(r.left, window.innerWidth - width - 12)),
        top: up ? r.top - height - 6 : r.bottom + 6,
        width,
        maxHeight,
      });
    };
    place();
    window.addEventListener("resize", place);
    // Keep the menu attached when focus or browser auto-scroll moves its field.
    const scroll = (event: Event) => {
      if (!menu.current?.contains(event.target as Node)) {
        const bounds = trigger.current?.getBoundingClientRect();
        if (!bounds || bounds.bottom < 0 || bounds.top > window.innerHeight) close();
        else place();
      }
    };
    window.addEventListener("scroll", scroll, true);
    const outside = (event: PointerEvent) => {
      if (
        !root.current?.contains(event.target as Node) &&
        !menu.current?.contains(event.target as Node)
      )
        close();
    };
    document.addEventListener("pointerdown", outside);
    return () => {
      window.removeEventListener("resize", place);
      window.removeEventListener("scroll", scroll, true);
      document.removeEventListener("pointerdown", outside);
    };
  }, [open, options.length]);
  useEffect(() => {
    const list = menu.current;
    const option = list?.querySelector<HTMLElement>(`[data-index="${active}"]`);
    if (!open || !list || !option) return;
    // Scroll only the options, never the surrounding review dialog or page.
    const top = option.offsetTop;
    const bottom = top + option.offsetHeight;
    if (top < list.scrollTop) list.scrollTop = top;
    else if (bottom > list.scrollTop + list.clientHeight)
      list.scrollTop = bottom - list.clientHeight;
  }, [active, open]);
  useEffect(() => {
    if (props.disabled) close();
  }, [props.disabled]);

  return (
    <span ref={root} className={`ui-select ${className}`}>
      <button
        ref={trigger}
        id={id || uid}
        type="button"
        role="combobox"
        className="ui-select-trigger"
        aria-label={props["aria-label"]}
        aria-labelledby={props["aria-labelledby"]}
        aria-describedby={[props["aria-describedby"], invalid ? `${uid}-error` : ""].filter(Boolean).join(" ") || undefined}
        aria-invalid={invalid || props["aria-invalid"]}
        aria-required={props.required}
        aria-expanded={open}
        aria-haspopup="listbox"
        aria-controls={open ? listId : undefined}
        aria-activedescendant={
          open && active >= 0 ? `${uid}-${active}` : undefined
        }
        disabled={props.disabled}
        title={props.title}
        onClick={() => (open ? close() : show())}
        onBlur={(event) => {
          if (!menu.current?.contains(event.relatedTarget as Node)) close();
        }}
        onKeyDown={(event) => {
          if (event.key === "Escape" && open) {
            event.preventDefault();
            event.stopPropagation();
            close();
            return;
          }
          if (event.key === "Tab") {
            close();
            return;
          }
          if (["Enter", " "].includes(event.key)) {
            event.preventDefault();
            open ? choose(active) : show();
            return;
          }
          if (["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) {
            event.preventDefault();
            if (!open) {
              show();
              return;
            }
            const enabled = options
              .map((o, i) => (o.disabled ? -1 : i))
              .filter((i) => i >= 0);
            const current = enabled.indexOf(active);
            const next =
              event.key === "Home"
                ? 0
                : event.key === "End"
                  ? enabled.length - 1
                  : Math.max(
                      0,
                      Math.min(
                        enabled.length - 1,
                        current + (event.key === "ArrowDown" ? 1 : -1),
                      ),
                    );
            setActive(enabled[next] ?? -1);
            return;
          }
          if (
            event.key.length === 1 &&
            !event.ctrlKey &&
            !event.metaKey &&
            !event.altKey
          ) {
            event.preventDefault();
            const now = Date.now();
            search.current = {
              value:
                (now - search.current.at < 700 ? search.current.value : "") +
                event.key.toLocaleLowerCase(),
              at: now,
            };
            const index = options.findIndex(
              (o) =>
                !o.disabled &&
                o.label.toLocaleLowerCase().startsWith(search.current.value),
            );
            if (index >= 0) {
              setOpen(true);
              setActive(index);
            }
          }
        }}
      >
        <span>{options[selected]?.label || "\u00a0"}</span>
        <ChevronDown size={17} aria-hidden="true" />
      </button>
      <select
        {...props}
        ref={native}
        hidden
        tabIndex={-1}
        aria-hidden="true"
        aria-label={undefined}
        aria-labelledby={undefined}
        onInvalid={(event) => {
          event.preventDefault();
          setInvalid(true);
          trigger.current?.focus();
          props.onInvalid?.(event);
        }}
        onChange={(event) => {
          setValue(event.currentTarget.value);
          setInvalid(false);
          props.onChange?.(event);
        }}
      >
        {children}
      </select>
      {invalid && <span id={`${uid}-error`} role="alert" className="ui-select-error">{t("कृपया एक विकल्प चुनें।", "Please choose an option.")}</span>}
      {open &&
        createPortal(
          <div
            ref={menu}
            id={listId}
            role="listbox"
            className="ui-select-menu"
            style={position}
            aria-label={props["aria-label"]}
            aria-labelledby={props["aria-labelledby"] || id || uid}
            onMouseDown={(event) => event.preventDefault()}
          >
            {options.map((option, index) => (
              <div
                key={`${index}-${option.value}`}
                id={`${uid}-${index}`}
                role="option"
                aria-selected={index === selected}
                aria-disabled={option.disabled || undefined}
                data-value={option.value}
                data-index={index}
                className={`ui-select-option${index === active ? " active" : ""}`}
                onPointerMove={() => {
                  if (!option.disabled) setActive(index);
                }}
                onClick={(event) => {
                  event.stopPropagation();
                  choose(index);
                }}
              >
                <span>{option.label}</span>
                {index === selected && <Check size={17} aria-hidden="true" />}
              </div>
            ))}
          </div>,
          root.current?.closest("dialog") || document.body,
        )}
    </span>
  );
}
