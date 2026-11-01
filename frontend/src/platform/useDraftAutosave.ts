import { useEffect, type DependencyList } from "react";
// Capture the current identity and values for this checkpoint. A retired capture
// is ignored by persistDraft, even if an earlier save was already in flight.
export function useDraftAutosave(
  enabled: boolean,
  checkpoint: () => Promise<void>,
  onError: (message: string) => void,
  dependencies: DependencyList,
) {
  useEffect(() => {
    if (!enabled) return;
    const timer = window.setTimeout(() => {
      void checkpoint().catch((error) => onError(error.message));
    }, 300);
    return () => window.clearTimeout(timer);
  }, [enabled, ...dependencies]);
}
