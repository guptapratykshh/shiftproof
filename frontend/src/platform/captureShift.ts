export type CaptureShift = {
  id: string;
  name: string;
  starts_at?: string;
  ends_at?: string;
  capture_allowed?: boolean;
  capture_item_ids?: string[];
};
export const WRONG_CAPTURE_SHIFT = "This recording belongs to a different date than the selected shift. Keep the draft and ask your organization owner to assign a shift covering the recording time.";
export const NO_CURRENT_SHIFT = "This shift is not available for a new update now. Choose a current assigned shift, or ask your organization owner to create and assign one.";
export const LATE_CAPTURE = "This report is over 72 hours late. Keep the recording and ask your supervisor to import it.";

// Mirrors server time-window checks. These hints never grant upload permission.
export function captureShiftProblem(shift: CaptureShift | undefined, recordedAt: string, now = Date.now()): string {
  if (!shift) return ""; // Legacy owner workspace has no dated shift.
  if (shift.capture_allowed === false) return "You can read this handover but were not assigned to record in its shift";
  const recorded = Date.parse(recordedAt), start = Date.parse(shift.starts_at || ""), end = Date.parse(shift.ends_at || "");
  const hour = 3600000;
  if (recorded < start - hour || recorded > end + hour) return WRONG_CAPTURE_SHIFT;
  if (now > end + 72 * hour) return LATE_CAPTURE;
  return "";
}
