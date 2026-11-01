import { useEffect, useSyncExternalStore } from "react";
import type { ReactNode } from "react";
import hindi from "./locales/hi.json";

export type Language = "en" | "hi";
const KEY = "shiftproof-language";
const listeners = new Set<() => void>();
let language: Language = "en";
let account = "";
let explicitlyChosen = false;
try {
  const saved = localStorage.getItem(KEY);
  if (saved === "hi" || saved === "en") {
    language = saved;
    explicitlyChosen = true;
  }
} catch {
  /* In-memory preference works when storage is unavailable. */
}
export const getLanguage = () => language;
export const locale = () => (language === "hi" ? "hi-IN" : "en-IN");
export function setLanguage(next: Language) {
  language = next;
  explicitlyChosen = true;
  try {
    localStorage.setItem(KEY, next);
    if (account) localStorage.setItem("shiftproof-language:" + account, next);
  } catch {
    /* Language changes must not depend on persistent storage. */
  }
  document.documentElement.lang = next;
  listeners.forEach((notify) => notify());
}
export function adoptAccountLanguage(
  userId: string,
  fallback: Language = "en",
) {
  account = userId;
  let saved: string | null = null;
  try {
    saved = localStorage.getItem("shiftproof-language:" + userId);
  } catch {
    /* optional */
  }
  if (!explicitlyChosen) {
    language = saved === "hi" || saved === "en" ? saved : fallback;
    document.documentElement.lang = language;
    listeners.forEach((notify) => notify());
  }
}
export function useLanguage() {
  return useSyncExternalStore(
    (callback) => {
      listeners.add(callback);
      return () => {
        listeners.delete(callback);
      };
    },
    getLanguage,
    () => "en" as Language,
  );
}
const catalog: Record<string, string> = hindi;
const folded = Object.fromEntries(
  Object.entries(catalog).map(([key, value]) => [key.toLowerCase(), value]),
);
const reverse = Object.fromEntries(
  Object.entries(catalog)
    .filter(([, value]) => value)
    .map(([key, value]) => [value, key]),
);
// Only interface messages belong here. Never call this on original transcripts,
// excerpts, names, identifiers or user-written task descriptions.
export function tr(text: string): string {
  if (language === "en") return reverse[text] || text;
  const key = text
    .replace(/\u2014/g, " - ")
    .replace(/\s+/g, " ")
    .trim();
  const translated = catalog[key] ?? folded[key.toLowerCase()];
  return translated === undefined ? text : translated;
}
export function msg(key: string, values: Record<string, string | number>) {
  return tr(key).replace(/\{(\w+)\}/g, (whole, name: string) =>
    String(values[name] ?? whole),
  );
}
export function claimValue(claim: { property: string; value: unknown }) {
  return claim.property === "task"
    ? String(claim.value)
    : tr(String(claim.value));
}
export function systemText(text: string) {
  if (language === "en") return text;
  const exact = tr(text);
  if (exact !== text) return exact;
  const quantity = text.match(
    /^Dispatch requires (\d+) units; the human-reviewed quantity is (\d+|unknown)$/,
  );
  if (quantity)
    return `भेजने के लिए ${quantity[1]} इकाइयाँ जरूरी हैं; व्यक्ति की जाँच में स्वीकार मात्रा ${tr(quantity[2])} है`;
  const pending = text.match(/^(\w+) is reported pending$/);
  if (pending) return `${tr(pending[1])} बाकी बताया गया है`;
  const exception = "Recorded quantity exception: ";
  if (text.startsWith(exception))
    return "मात्रा की दर्ज छूट का कारण: " + text.slice(exception.length);
  const conflict = text.match(/^Conflicting (\w+) reports(?: need review)?$/);
  if (conflict)
    return `${tr(conflict[1])} की रिपोर्टें अलग बातें बता रही हैं; जाँच जरूरी है`;
  const prerequisite = text.match(/^(\w+) (\w+) is not human-reviewed$/);
  if (prerequisite)
    return `${tr(prerequisite[1])}: ${tr(prerequisite[2])}, व्यक्ति की जाँच अभी बाकी है`;
  const report = text.match(/^Obtain and review a sourced (\w+) report$/);
  if (report) return `${tr(report[1])} की मूल जानकारी सहित रिपोर्ट लेकर जाँचें`;
  const property = text.match(
    /^(packing|quality|dispatch|quantity|operating|fault|repair|documents): (\w+)$/,
  );
  if (property) return `${tr(property[1])}: ${tr(property[2])}`;
  const signIn = text.match(/^Signed in as (.+)\.$/);
  if (signIn) return `${tr(signIn[1])} के रूप में साइन इन है।`;
  return text;
}
export function ui(value: ReactNode): ReactNode {
  return typeof value === "string" ? tr(value) : value;
}
export function bilingual(hi: string, en: string) {
  return language === "hi" ? catalog[en.replace(/\s+/g, " ").trim()] || hi : en;
}
export function LanguageButton({
  className = "text-button",
}: {
  className?: string;
}) {
  const current = useLanguage();
  return (
    <button
      type="button"
      className={className}
      onClick={() => setLanguage(current === "hi" ? "en" : "hi")}
      aria-label={current === "hi" ? "Switch to English" : "हिन्दी में बदलें"}
    >
      {current === "hi" ? "English" : "हिन्दी"}
    </button>
  );
}
export function LanguageRoot({ children }: { children: ReactNode }) {
  const current = useLanguage();
  useEffect(() => {
    document.documentElement.lang = current;
    document.title =
      current === "hi"
        ? "ShiftProof | हर शिफ्ट को पूरी जानकारी"
        : "ShiftProof - Work changes hands. The details shouldn’t.";
  }, [current]);
  useEffect(() => {
    const changed = (event: StorageEvent) => {
      if (
        event.key === KEY &&
        (event.newValue === "hi" || event.newValue === "en")
      )
        setLanguage(event.newValue);
    };
    window.addEventListener("storage", changed);
    return () => window.removeEventListener("storage", changed);
  }, []);
  return children;
}

// The API separates generated explanations from verbatim task/condition text.
// This lets language changes preserve names and evidence without parsing prose.
export type AnswerItem = {
  text: string;
  note_ids: string[];
  claim_ids?: string[];
  kind?: string;
  presentation?: {
    type: string;
    property?: string;
    value?: string | number;
    status?: string;
    kind?: string;
    modality?: string;
    condition?: string | null;
    action?: string;
    reason?: string;
    owner?: string | null;
    code?: string;
    generated?: boolean;
  } | null;
};
export function answerItem(item: AnswerItem) {
  if (language === "en" || !item.presentation) return systemText(item.text);
  const p = item.presentation;
  if (p.type === "history") {
    const value = p.property === "task" ? String(p.value) : tr(String(p.value));
    return (
      `${tr(p.property || "")}: ${value} · ${tr(p.status || "")} · ${tr(p.kind || "")}` +
      (p.modality && p.modality !== "actual" ? ` · ${tr(p.modality)}` : "") +
      (p.condition ? ` · ${tr("Condition:")} ${p.condition}` : "")
    );
  }
  const task =
    p.type === "task"
      ? !p.generated
      : ["open_tasks", "task"].includes(p.code || "");
  return (
    (p.reason
      ? (p.code === "task" ? p.reason : systemText(p.reason)) + "। "
      : "") +
    `${tr("Next action:")} ${task ? p.action : systemText(p.action || "")}। ${tr("Responsible:")} ${tr(p.owner || "Unassigned")}`
  );
}
export function answerHeading(answer: {
  answer: string;
  intent?: string;
  comparison_snapshot?: { version: number } | null;
  items?: AnswerItem[];
}) {
  if (answer.intent === "changes")
    return answer.comparison_snapshot
      ? msg("Changes since previous-shift snapshot v{version}", {
          version: answer.comparison_snapshot.version,
        })
      : tr("Recorded history (no previous-shift snapshot)");
  if (
    answer.items?.length &&
    answer.answer === answer.items.map((i) => i.text).join("; ")
  )
    return tr("From the recorded evidence");
  return systemText(answer.answer);
}
