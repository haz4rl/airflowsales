// Types mirror the FastAPI/Pydantic response models in backend/app/schemas/*.
// Keep them in sync with the backend — do not invent fields the API does not return.

export interface Campaign {
  id: string;
  name: string;
  product_description: string;
  target_industries: string[];
  target_company_characteristics: Record<string, unknown>;
  qualification_criteria: string;
  created_at: string;
  updated_at: string;
}

export type CampaignCreate = Omit<Campaign, "id" | "created_at" | "updated_at">;

export interface CampaignRef {
  id: string;
  name: string;
}

export interface Company {
  id: string;
  domain: string;
  name: string | null;
  description: string | null;
  industry: string | null;
  location: string | null;
}

export interface Evidence {
  id: string;
  source_url: string | null;
  source_title: string | null;
  excerpt: string;
  evidence_type: string;
  created_at: string;
}

export interface Qualification {
  score: number;
  confidence: number;
  decision: string;
  reasoning: string;
  scoring_breakdown: Record<string, unknown>;
}

export interface Prospect {
  id: string;
  campaign_id: string;
  company_id: string;
  status: string;
  created_at: string;
}

export interface DiscoveryRequest {
  campaign_id: string;
  domain: string;
}

export interface DiscoveryResponse {
  prospect: Prospect;
  company: Company;
  evidence: Evidence[];
  qualification: Qualification | null;
  workflow_run_id: string | null;
  outreach: Record<string, unknown> | null;
  critic: Record<string, unknown> | null;
}

/** Row shape of GET /v1/prospects. */
export interface ProspectListItem {
  prospect: Prospect;
  company: Company;
  qualification: Qualification | null;
  campaign: CampaignRef | null;
  research_date: string | null;
}

/** Row shape of GET /v1/workflow-runs (list — no embedded events). */
export interface WorkflowRunListItem {
  id: string;
  prospect_id: string;
  status: string;
  total_tokens: number;
  total_cost: number;
  created_at: string;
  updated_at: string;
  event_count: number;
  company_name: string | null;
  company_domain: string | null;
}

export interface WorkflowEvent {
  id: string;
  event_type: string;
  name: string;
  input: Record<string, unknown>;
  output: Record<string, unknown>;
  latency_ms: number | null;
  token_usage: Record<string, unknown>;
  created_at: string;
}

export interface WorkflowRun {
  id: string;
  prospect_id: string;
  status: string;
  total_tokens: number;
  total_cost: number;
  created_at: string;
  updated_at: string;
  events: WorkflowEvent[];
}

export interface ApprovalRequest {
  approved: boolean;
  note?: string | null;
}

export interface DashboardSummary {
  prospects: number;
  companies: number;
  qualified: number;
  awaiting_approval: number;
  workflow_runs: number;
  failed_runs: number;
  total_tokens: number;
  total_cost: number;
  statuses: Record<string, number>;
  /** Workflow-run status counts (COMPLETED, FAILED, RUNNING, …). */
  run_statuses: Record<string, number>;
}

export interface HealthResponse {
  status: string;
}
