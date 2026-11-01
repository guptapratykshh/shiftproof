export type Industry = {
  id: string;
  name: string;
  item: string;
  status: "available" | "preview";
  version: number;
  properties: Record<string, string[]>;
};
export type Organization = {
  id: string;
  name: string;
  industry: string;
  timezone: string;
  access: "owner" | "admin" | "member";
  role: "operator" | "supervisor" | "quality";
  login_code?: string;
  capabilities?: {
    manage_people?: boolean;
    manage_settings?: boolean;
    invite_workers?: boolean;
    review_reports?: boolean;
    clear_holds?: boolean;
    export_data?: boolean;
    manage_work?: boolean;
  };
  profile: Industry;
  setup: { locations?: string[]; teams?: string[]; shifts?: string[] };
};
export type Session = {
  user: { id: string; name: string; email: string | null };
  csrf_token: string;
  organizations: Organization[];
  auth_kind?: "email" | "employee";
  scoped_organization_id?: string | null;
  no_organization_access?: boolean;
  capabilities?: { create_organization: boolean; change_password: boolean };
};
let csrf = "";
let activeShift: string | null = null;
export function setActiveShift(id: string | null) {
  activeShift = id;
}
export const API = import.meta.env.VITE_API_URL || "/api";
export function setCsrf(value: string) {
  csrf = value;
}
export class ApiError extends Error {
  constructor(
    message: string,
    public status = 0,
  ) {
    super(message);
  }
}
async function request(path: string, init: RequestInit) {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 45000);
  try {
    const response = await fetch(API + path, {
      ...init,
      credentials: "same-origin",
      signal: controller.signal,
    });
    if (!response.ok) {
      const data = await response.json().catch(() => null);
      const detail = data?.detail;
      throw new ApiError(
        typeof detail === "string"
          ? detail
          : detail?.message ||
              (response.status === 401
                ? "Please sign in again. Your saved draft stays on this device."
                : response.status === 403
                  ? "You do not have permission for this action. Ask your supervisor."
                  : response.status === 409
                    ? "The handover changed. Refresh and check the latest information; your draft is retained."
                    : "The service could not complete this request. Your draft is retained. Try again."),
        response.status,
      );
    }
    return response;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    throw new ApiError(
      navigator.onLine
        ? "The connection was interrupted. Your draft is retained. Try again."
        : "You are offline. Keep recording or writing; send your saved draft when connected.",
    );
  } finally {
    window.clearTimeout(timeout);
  }
}
export async function call<T>(
  path: string,
  body?: unknown,
  method?: string,
  shift: string | null = activeShift,
): Promise<T> {
  const response = await request(path, {
    method: method || (body === undefined ? "GET" : "POST"),
    credentials: "same-origin",
    headers: {
      "X-CSRF-Token": csrf,
      ...(shift && path.startsWith("/organizations/")
        ? { "X-Shift-ID": shift }
        : {}),
      ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await response.json();
  if (!response.ok)
    throw new Error(
      typeof data.detail === "string"
        ? data.detail
        : data.detail?.message || "Please check the submitted fields.",
    );
  if (data.csrf_token) setCsrf(data.csrf_token);
  return data;
}
export async function binary(
  path: string,
  body: Blob | unknown,
  method = "POST",
  shift: string | null = activeShift,
) {
  const isBlob = body instanceof Blob;
  const response = await request(path, {
    method,
    credentials: "same-origin",
    headers: {
      "X-CSRF-Token": csrf,
      ...(shift && path.startsWith("/organizations/")
        ? { "X-Shift-ID": shift }
        : {}),
      "Content-Type": isBlob ? "audio/wav" : "application/json",
    },
    body: isBlob ? body : JSON.stringify(body),
  });
  if (!response.ok) {
    const data = await response.json();
    throw new Error(
      data.detail || "Audio request failed. The text remains available.",
    );
  }
  return response.blob();
}
export const industryExamples: Record<
  string,
  { issue: string; update: string; action: string }
> = {
  manufacturing: {
    issue: "Quality inspection pending",
    update: "Packing complete",
    action: "Quality reviewer to verify the batch",
  },
  maintenance: {
    issue: "Vibration remains unresolved",
    update: "Machine running",
    action: "Technician to verify the permanent repair",
  },
  warehousing: {
    issue: "Invoice verification pending",
    update: "Order packed",
    action: "Reviewer to check dispatch documents",
  },
  quality_assurance: {
    issue: "Seal finding unresolved",
    update: "Inspection recorded",
    action: "Authorized reviewer to record the outcome",
  },
  food_processing: {
    issue: "Temperature log unchecked",
    update: "Batch in cold storage",
    action: "Review the original monitoring record",
  },
  construction: {
    issue: "Electrical inspection pending",
    update: "Installation complete",
    action: "Inspector to verify the installation",
  },
  healthcare: {
    issue: "Handover task outstanding",
    update: "Routine update recorded",
    action: "Specialized clinical workflow  -  planned",
  },
  facilities: {
    issue: "Pump noise unresolved",
    update: "Pump operational",
    action: "Maintenance team to verify the repair",
  },
};
