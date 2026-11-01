import "./theme";
import "./tokens.css";
import "./assets/fonts/fonts.css";
import React from "react";
import ReactDOM from "react-dom/client";
import Portal from "./platform/Portal";
import { LanguageRoot, tr } from "./i18n";
import "./styles.css";
import "./design-system.css";
// A production preview on this origin may have left an offline shell behind.
// Development must load current code without deleting saved recording drafts.
if (import.meta.env.DEV) {
  void (async () => {
    if ("serviceWorker" in navigator) {
      const registrations = await navigator.serviceWorker.getRegistrations();
      await Promise.all(
        registrations.map((registration) => {
          const worker =
            registration.active ||
            registration.waiting ||
            registration.installing;
          return worker && new URL(worker.scriptURL).pathname === "/sw.js"
            ? registration.unregister()
            : Promise.resolve(false);
        }),
      );
    }
    if ("caches" in window) {
      const names = await caches.keys();
      await Promise.all(
        names
          .filter((name) => name.startsWith("shiftproof-shell-"))
          .map((name) => caches.delete(name)),
      );
    }
  })().catch(() => {});
}
if (import.meta.env.PROD && "serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    void navigator.serviceWorker.register("/sw.js").catch(() => {});
  });
}
ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <LanguageRoot>
      <React.Suspense
        fallback={
          <div className="platform-loading" role="status">
            {tr("Opening your private workspace…")}
          </div>
        }
      >
        <Portal />
      </React.Suspense>
    </LanguageRoot>
  </React.StrictMode>,
);
