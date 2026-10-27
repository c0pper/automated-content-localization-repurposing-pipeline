/** Shared TypeScript types mirroring the API wire shapes. */

export interface SourceLanguage {
  code: string;
  origin: "declared" | "detected";
  detected_code: string | null;
}

export interface ScoreBreakdown {
  hook_strength: number;
  standalone_clarity: number;
  emotional_payoff: number;
  business_fit: number;
}

export interface Clip {
  segment_id: number;
  start_time: string;
  end_time: string;
  hook_title: string;
  caption: string;
  selection_score: number;
  score_breakdown: ScoreBreakdown;
  rationale: string;
  video_asset_url: string;
  localized_assets: Record<string, string>;
  localized_copy: Record<string, { hook_title: string; caption: string }>;
}

export interface CopyOrigin {
  planning_model: string;
  copy_model: string;
  translation_model: string;
  source_language: string;
}

export interface JobError {
  code: string;
  message: string;
  retryable: boolean;
}

export interface JobCost {
  job_budget_usd: string;
  spent_usd: string;
  workspace_remaining_usd: string;
  projected_localization_usd: string | null;
}

export interface JobSelection {
  segment_ids: number[];
  languages: string[];
  expected_total_usd: string;
  confirmed_at: string | null;
}

export interface Job {
  job_id: string;
  status:
    | "RECEIVED"
    | "PROCESSING"
    | "AWAITING_SELECTION"
    | "COMPLETED"
    | "FAILED"
    | "EXPIRED"
    | "CANCELLED";
  stage: string | null;
  source: { type: string; url?: string; key?: string } | null;
  source_language: SourceLanguage | null;
  target_languages: string[];
  lip_sync: boolean;
  parent_job_id: string | null;
  derived_mode: string | null;
  created_at: string | null;
  updated_at: string | null;
  expires_at: string | null;
  review_url: string;
  segments: Clip[];
  content: { linkedin_post: string; newsletter: string };
  copy_origin: CopyOrigin;
  selection: JobSelection | null;
  cost: JobCost;
  error: JobError | null;
}

export interface JobSummary {
  job_id: string;
  status: Job["status"];
  stage: string | null;
  created_at: string | null;
  expires_at: string | null;
  review_url: string;
}

export interface JobList {
  items: JobSummary[];
  next_cursor: string | null;
}

export interface CostCell {
  segment_id: number;
  language: string;
  translation_usd: string;
  voice_usd: string;
  lip_sync_usd: string;
  total_usd: string;
}

export interface GatePayload {
  job_id: string;
  status: Job["status"];
  expires_at: string | null;
  source_language: SourceLanguage | null;
  target_languages: string[];
  lip_sync: boolean;
  segments: Array<{
    segment_id: number;
    start_time: string;
    end_time: string;
    hook_title: string;
    caption: string;
    selection_score: number;
    score_breakdown: ScoreBreakdown;
    rationale: string;
    base_asset_url: string;
  }>;
  cost_matrix: CostCell[];
  projected_total_usd: string;
}

export interface JobEvent {
  event_id: string;
  type: string;
  stage: string | null;
  payload: Record<string, unknown>;
  created_at: string | null;
}

export interface CostLedgerEntry {
  entry_id: string;
  stage: string;
  provider: string;
  model: string;
  units: number;
  unit_type: string;
  rate_usd: string;
  estimated_usd: string;
  actual_usd: string | null;
  rate_card_version: string;
  created_at: string | null;
}

export interface CostBreakdown {
  job_budget_usd: string;
  spent_usd: string;
  entries: CostLedgerEntry[];
}

export interface WorkspaceSettings {
  workspace_id: string;
  target_language_allowlist: string[];
  default_models: Record<string, string>;
  job_budget_usd: string;
  monthly_budget_usd: string;
  max_concurrent_jobs: number;
  current_month_spend_usd: string;
  remaining_usd: string;
  voice_profile: {
    provider: string;
    voice_id: string;
    updated_at: string | null;
  } | null;
}

export interface JobAccepted {
  job_id: string;
  status: Job["status"];
  created_at: string;
}

export interface Purge {
  purge_id: string;
  status: string;
  counts: Record<string, number>;
  created_at: string;
  completed_at: string | null;
  error: string | null;
}

export interface ReviewManifest {
  job_id: string;
  status: string;
  review_url: string;
  assets: Array<{
    asset_id: string;
    kind: string;
    segment_id: number | null;
    language: string | null;
    url: string;
  }>;
}

export interface ApiErrorDetail {
  code: string;
  message: string;
  details: Record<string, unknown>;
}