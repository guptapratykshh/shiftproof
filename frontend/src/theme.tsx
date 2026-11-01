import { useSyncExternalStore } from "react";
import { Sun, Moon } from "lucide-react";
import { bilingual as t, useLanguage } from "./i18n";

export type Appearance = "light" | "dark" | "system";
const key = "shiftproof-theme";
const listeners = new Set<() => void>();
const media = window.matchMedia("(prefers-color-scheme: dark)");
let appearance: Appearance = "system";
try {
  const saved = localStorage.getItem(key);
  if (saved === "light" || saved === "dark" || saved === "system")
    appearance = saved;
} catch {
  /* Appearance still works without storage. */
}

function apply() {
  const dark =
    appearance === "dark" || (appearance === "system" && media.matches);
  document.documentElement.dataset.theme = dark ? "dark" : "light";
  document
    .querySelector('link[rel="icon"]')
    ?.setAttribute("href", dark ? "/favicon-dark.svg" : "/favicon.svg");
  document.documentElement.style.colorScheme = dark ? "dark" : "light";
  document
    .querySelector('meta[name="theme-color"]')
    ?.setAttribute("content", dark ? "#211a30" : "#352653");
}
apply();
media.addEventListener("change", () => {
  apply();
  listeners.forEach((notify) => notify());
});
window.addEventListener("storage", (event) => {
  if (event.key !== key) return;
  appearance =
    event.newValue === "light" || event.newValue === "dark"
      ? event.newValue
      : "system";
  apply();
  listeners.forEach((notify) => notify());
});
export function setAppearance(next: Appearance) {
  appearance = next;
  try {
    localStorage.setItem(key, next);
  } catch {
    /* optional persistence */
  }
  apply();
  listeners.forEach((notify) => notify());
}
export function useResolvedTheme(): "light" | "dark" {
  return useSyncExternalStore(
    (callback) => {
      listeners.add(callback);
      return () => {
        listeners.delete(callback);
      };
    },
    () =>
      appearance === "system" ? (media.matches ? "dark" : "light") : appearance,
  );
}
export function AppearanceControl() {
  useLanguage();
  const dark = useResolvedTheme() === "dark";
  const Icon = dark ? Sun : Moon;
  const label = dark
    ? t("हल्की थीम अपनाएँ", "Switch to light theme")
    : t("गहरी थीम अपनाएँ", "Switch to dark theme");
  return (
    <button
      type="button"
      className="appearance-control"
      aria-label={label}
      title={label}
      onClick={() => setAppearance(dark ? "light" : "dark")}
    >
      <Icon size={20} aria-hidden="true" />
    </button>
  );
}
