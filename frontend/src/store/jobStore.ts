/**
 * Job domain Zustand slice.
 * Wraps /api/jobs endpoints: list, get, create, cancel, retry, derive, selection confirm.
 * Mutations reuse their Idempotency-Key when the same intent is retried (ADR-0019).
 */
import { createStore } from "zustand";
import { api, isApiError, isSelectionPriceChanged } from "@/lib/api";
import { createIntentKeys } from "@/lib/idempotency";
import type {
  CostBreakdown,
  CostCellTotal,
  GatePayload,
  Job,
  JobAccepted,
  JobList,
  JobSummary,
} from "@/lib/types";

export interface SubmitJobPayload {
  source: { type: "url" | "object"; url?: string; key?: string };
  source_language?: string;
  target_languages: string[];
  lip_sync: boolean;
  model_overrides: Record<string, string>;
}

export interface DerivePayload {
  mode: "copy" | "localization";
  parentJobId: string;
  target_languages?: string[];
  lip_sync?: boolean;
  model_overrides?: Record<string, string>;
  refresh_long_form?: boolean;
}

export type JobStore = {
  jobs: JobSummary[];
  nextCursor: string | null;
  loading: boolean;
  /** Error code of the last failed list/submit (`network_error` when no response). */
  error: string | null;
  selectedJob: Job | null;
  selectedLoading: boolean;
  gate: GatePayload | null;
  gateLoading: boolean;
  cost: CostBreakdown | null;
  costLoading: boolean;
  busy: boolean;

  /** Replaces `jobs` with one page; with `append: true` adds the page after the loaded jobs ("load more"). */
  listJobs: (opts?: { status?: string; limit?: number; cursor?: string | null; append?: boolean }) => Promise<void>;
  getJob: (jobId: string) => Promise<Job>;
  getGate: (jobId: string) => Promise<GatePayload>;
  getCost: (jobId: string) => Promise<CostBreakdown>;
  submitJob: (payload: SubmitJobPayload) => Promise<JobAccepted>;
  /**
   * Confirms a selection. On 409 `selection_price_changed` the gate is
   * reloaded with the new prices before the error is rethrown.
   */
  confirmSelection: (jobId: string, segmentIds: number[], languages: string[], expectedTotalUsd: string) => Promise<Job>;
  cancelJob: (jobId: string) => Promise<Job>;
  retryJob: (jobId: string) => Promise<Job>;
  deriveJob: (payload: DerivePayload) => Promise<Job>;
  rotateReviewLink: (jobId: string) => Promise<{ review_url: string; rotated_at: string }>;
  revokeReviewLink: (jobId: string) => Promise<void>;
  reset: () => void;
};

/** State patch clearing `busy` and mirroring a new review_url onto the selected Job. */
function withReviewUrl(selectedJob: Job | null, jobId: string, reviewUrl: string | null) {
  return selectedJob?.job_id === jobId
    ? { busy: false, selectedJob: { ...selectedJob, review_url: reviewUrl } }
    : { busy: false };
}

/**
 * After a 409 `selection_price_changed` the server's prices win: reload the
 * full gate (with the translation/voice/lip-sync breakdown). If that fails,
 * patch the cell totals from the error details so the live total still
 * reflects the new prices.
 */
function repricedGate(gate: GatePayload, costMatrix: CostCellTotal[]): GatePayload {
  const totals = new Map(costMatrix.map((c) => [`${c.segment_id}:${c.language}`, c.total_usd]));
  return {
    ...gate,
    cost_matrix: gate.cost_matrix.map((c) => ({
      ...c,
      total_usd: totals.get(`${c.segment_id}:${c.language}`) ?? c.total_usd,
    })),
  };
}

export const createJobStore = () => {
  // Retry-safe Idempotency-Keys per in-flight intent (ADR-0019).
  const withIntentKey = createIntentKeys();
  // Bumped by every list that replaces `jobs`; a page fetched under an older
  // generation (e.g. "load more" for a previous status filter) is discarded.
  let listGeneration = 0;

  return createStore<JobStore>((set, get) => ({
    jobs: [],
    nextCursor: null,
    loading: false,
    error: null,
    selectedJob: null,
    selectedLoading: false,
    gate: null,
    gateLoading: false,
    cost: null,
    costLoading: false,
    busy: false,

    listJobs: async (opts) => {
      const generation = opts?.append ? listGeneration : ++listGeneration;
      const stale = () => generation !== listGeneration;
      set({ loading: true, error: null });
      try {
        const query: { limit: number; cursor: string | null; status?: string } = {
          limit: opts?.limit ?? 50,
          cursor: opts?.cursor ?? null,
        };
        if (opts?.status) query.status = opts.status;
        const res = await api.get<JobList>("/jobs", { query });
        if (stale()) return;
        set((s) => ({
          jobs: opts?.append ? [...s.jobs, ...res.items] : res.items,
          nextCursor: res.next_cursor,
          loading: false,
        }));
      } catch (e) {
        if (stale()) return;
        set({ loading: false, error: isApiError(e) ? e.code : "network_error" });
        throw e;
      }
    },

    getJob: async (jobId) => {
      set({ selectedLoading: true });
      try {
        const job = await api.get<Job>(`/jobs/${jobId}`);
        set({ selectedJob: job, selectedLoading: false });
        return job;
      } catch (e) {
        set({ selectedLoading: false });
        throw e;
      }
    },

    getGate: async (jobId) => {
      set({ gateLoading: true });
      try {
        const gate = await api.get<GatePayload>(`/jobs/${jobId}/selection`);
        set({ gate, gateLoading: false });
        return gate;
      } catch (e) {
        set({ gateLoading: false });
        throw e;
      }
    },

    getCost: async (jobId) => {
      set({ costLoading: true });
      try {
        const cost = await api.get<CostBreakdown>(`/jobs/${jobId}/cost`);
        set({ cost, costLoading: false });
        return cost;
      } catch (e) {
        set({ costLoading: false });
        throw e;
      }
    },

    submitJob: async (payload) => {
      set({ busy: true, error: null });
      try {
        const accepted = await withIntentKey("submit", payload, (idempotencyKey) =>
          api.post<JobAccepted>("/jobs", payload, { idempotencyKey }),
        );
        set({ busy: false });
        return accepted;
      } catch (e) {
        set({ busy: false, error: isApiError(e) ? e.code : "network_error" });
        throw e;
      }
    },

    confirmSelection: async (jobId, segmentIds, languages, expectedTotalUsd) => {
      set({ busy: true, error: null });
      const body = { segment_ids: segmentIds, languages, expected_total_usd: expectedTotalUsd };
      try {
        const job = await withIntentKey(`confirm:${jobId}`, body, (idempotencyKey) =>
          api.post<Job>(`/jobs/${jobId}/selection`, body, { idempotencyKey }),
        );
        set({ selectedJob: job, busy: false });
        return job;
      } catch (e) {
        const changed = isSelectionPriceChanged(e);
        if (changed) {
          try {
            await get().getGate(jobId);
          } catch {
            const gate = get().gate;
            if (gate?.job_id === jobId) set({ gate: repricedGate(gate, changed.costMatrix) });
          }
        }
        set({ busy: false });
        throw e;
      }
    },

    cancelJob: async (jobId) => {
      set({ busy: true, error: null });
      try {
        const job = await withIntentKey(`cancel:${jobId}`, null, (idempotencyKey) =>
          api.post<Job>(`/jobs/${jobId}/cancel`, undefined, { idempotencyKey }),
        );
        set({ selectedJob: job, busy: false });
        return job;
      } catch (e) {
        set({ busy: false });
        throw e;
      }
    },

    retryJob: async (jobId) => {
      set({ busy: true, error: null });
      try {
        const job = await withIntentKey(`retry:${jobId}`, null, (idempotencyKey) =>
          api.post<Job>(`/jobs/${jobId}/retry`, undefined, { idempotencyKey }),
        );
        set({ selectedJob: job, busy: false });
        return job;
      } catch (e) {
        set({ busy: false });
        throw e;
      }
    },

    deriveJob: async (payload) => {
      set({ busy: true, error: null });
      const body = {
        mode: payload.mode,
        target_languages: payload.target_languages,
        lip_sync: payload.lip_sync,
        model_overrides: payload.model_overrides,
        refresh_long_form: payload.refresh_long_form,
      };
      try {
        const job = await withIntentKey(`derive:${payload.parentJobId}`, body, (idempotencyKey) =>
          api.post<Job>(`/jobs/${payload.parentJobId}/derive`, body, { idempotencyKey }),
        );
        set({ selectedJob: job, busy: false });
        return job;
      } catch (e) {
        set({ busy: false });
        throw e;
      }
    },

    rotateReviewLink: async (jobId) => {
      set({ busy: true, error: null });
      try {
        const res = await withIntentKey(`rotate-review:${jobId}`, null, (idempotencyKey) =>
          api.post<{ review_url: string; rotated_at: string }>(`/jobs/${jobId}/review-link`, undefined, {
            idempotencyKey,
          }),
        );
        set(withReviewUrl(get().selectedJob, jobId, res.review_url));
        return res;
      } catch (e) {
        set({ busy: false });
        throw e;
      }
    },

    revokeReviewLink: async (jobId) => {
      set({ busy: true, error: null });
      try {
        await withIntentKey(`revoke-review:${jobId}`, null, (idempotencyKey) =>
          api.delete(`/jobs/${jobId}/review-link`, { idempotencyKey }),
        );
        set(withReviewUrl(get().selectedJob, jobId, null));
      } catch (e) {
        set({ busy: false });
        throw e;
      }
    },

    reset: () => {
      set({
        jobs: [],
        nextCursor: null,
        loading: false,
        error: null,
        selectedJob: null,
        selectedLoading: false,
        gate: null,
        gateLoading: false,
        cost: null,
        costLoading: false,
        busy: false,
      });
    },
  }));
};