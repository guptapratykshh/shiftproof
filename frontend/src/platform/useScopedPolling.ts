import { useEffect, useRef } from "react";
// A status refresh never replaces capture state. Response fencing lives in the controller.
export function useScopedPolling(
  refresh: () => Promise<unknown>,
  organizationId: string,
) {
  const latest = useRef(refresh);
  latest.current = refresh;
  useEffect(() => {
    const update = () => {
      if (document.visibilityState === "visible" && navigator.onLine)
        void latest.current().catch(() => {});
    };
    const timer = window.setInterval(update, 4000);
    window.addEventListener("focus", update);
    window.addEventListener("online", update);
    document.addEventListener("visibilitychange", update);
    return () => {
      clearInterval(timer);
      window.removeEventListener("focus", update);
      window.removeEventListener("online", update);
      document.removeEventListener("visibilitychange", update);
    };
  }, [organizationId]);
}
