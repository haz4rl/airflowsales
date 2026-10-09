import type {
  ApprovalRequest,
  Campaign,
  CampaignCreate,
  DashboardSummary,
  DiscoveryRequest,
  DiscoveryResponse,
  HealthResponse,
  Prospect,
  ProspectListItem,
  WorkflowRun,
  WorkflowRunListItem,
} from "./types";

export const API_BASE = (
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"
).replace(/\/+$/, "");

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function readDetail(res: Response): Promise<string> {
  let body: unknown;
  try {
    body = await res.json();
  } catch {
    return `Request failed with status ${res.status}`;
  }
  const detail = (body as { detail?: unknown }).detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const messages = detail.map((item) => {
      const entry = item as { loc?: unknown[]; msg?: string };
      const where = Array.isArray(entry.loc)
        ? entry.loc.filter((part) => part !== "body").join(".")
        : "";
      const msg = entry.msg ?? "invalid";
      return where ? `${where}: ${msg}` : msg;
    });
    if (messages.length) return messages.join(" · ");
  }
  return `Request failed with status ${res.status}`;
}

async function request<T>(
  path: string,
  init?: RequestInit,
  timeoutMs = 20_000,
): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      cache: "no-store",
      ...init,
      signal: AbortSignal.timeout(timeoutMs),
      headers: {
        Accept: "application/json",
        ...(init?.body ? { "Content-Type": "application/json" } : {}),
        ...(init?.headers ?? {}),
      },
    });
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === "TimeoutError") {
      throw new ApiError(0, `The API at ${API_BASE} did not respond in time`);
    }
    throw new ApiError(0, `Cannot reach the API at ${API_BASE}`);
  }
  if (!res.ok) throw new ApiError(res.status, await readDetail(res));
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export function apiErrorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return "Something went wrong";
}

export const api = {
  health: () => request<HealthResponse>("/health"),

  listCampaigns: () => request<Campaign[]>("/v1/campaigns"),

  createCampaign: (payload: CampaignCreate) =>
    request<Campaign>("/v1/campaigns", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  deleteCampaign: (id: string) =>
    request<void>(`/v1/campaigns/${id}`, { method: "DELETE" }),

  discover: (payload: DiscoveryRequest) =>
    // The agent pipeline runs inside this request (search + LLM calls with
    // retries) and can legitimately take minutes — allow a long timeout.
    request<DiscoveryResponse>("/v1/prospects/discover", {
      method: "POST",
      body: JSON.stringify(payload),
    }, 300_000),

  getProspect: (id: string) => request<DiscoveryResponse>(`/v1/prospects/${id}`),

  listProspects: (options: { skip?: number; limit?: number } = {}) => {
    const params = new URLSearchParams();
    if (options.skip) params.set("skip", String(options.skip));
    if (options.limit) params.set("limit", String(options.limit));
    const query = params.toString();
    return request<ProspectListItem[]>(`/v1/prospects${query ? `?${query}` : ""}`);
  },

  listRuns: (
    options: { prospectId?: string; status?: string; skip?: number; limit?: number } = {},
  ) => {
    const params = new URLSearchParams();
    if (options.prospectId) params.set("prospect_id", options.prospectId);
    if (options.status) params.set("status", options.status);
    if (options.skip) params.set("skip", String(options.skip));
    if (options.limit) params.set("limit", String(options.limit));
    const query = params.toString();
    return request<WorkflowRunListItem[]>(`/v1/workflow-runs${query ? `?${query}` : ""}`);
  },

  getRun: (id: string) => request<WorkflowRun>(`/v1/workflow-runs/${id}`),

  approveRun: (id: string, payload: ApprovalRequest) =>
    request<WorkflowRun>(`/v1/workflow-runs/${id}/approval`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  dashboard: () => request<DashboardSummary>("/v1/dashboard/summary"),
};

export type { Prospect };
