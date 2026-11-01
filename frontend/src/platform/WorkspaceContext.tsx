import { createContext, useContext } from "react";
import type { WorkspaceController } from "./useWorkspaceController";
export const WorkspaceContext = createContext<WorkspaceController | null>(null);
export function useWorkspace() {
  const state = useContext(WorkspaceContext);
  if (!state?.org || !state.view)
    throw new Error("Operational page requires a loaded workspace");
  return { ...state, org: state.org, view: state.view };
}
