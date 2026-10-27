/**
 * Job domain Zustand slice.
 * Wraps /api/jobs endpoints: list, get, create, cancel, retry, derive, selection confirm.
 */
import { createStore } from "zustand";
import { api } from "@/lib/api";
import type {
  CostBreakdown,
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
  error: string | null;
  selectedJob: Job | null;
  selectedLoading: boolean;
  gate: GatePayload | null;
  gateLoading: boolean;
  cost: CostBreakdown | null;
  costLoading: boolean;
  busy: boolean;
  listJobs: (opts?: { status?: string; limit?: number; cursor?: string | null }) => Promise<void>;
  getJob: (jobId: string) => Promise<Job>;
  getGate: (jobId: string) => Promise<GatePayload>;
  getCost: (jobId: string) => Promise<CostBreakdown>;
  submitJob: (payload: SubmitJobPayload) => Promise<JobAccepted>;
  confirmSelection: (jobId: string, segmentIds: number[], languages: string[], expectedTotalUsd: string) => Promise<Job>;
  cancelJob: (jobId: string) => Promise<Job>;
  retryJob: (jobId: string) => Promise<Job>;
  deriveJob: (payload: DerivePayload) => Promise<Job>;
  rotateReviewLink: (jobId: string) => Promise<{ review_url: string; rotated_at: string }>;
  revokeReviewLink: (jobId: string) => Promise<void>;
  reset: () => void;
};

export const createJobStore = () =>
  createStore<JobStore>((set, get) => ({
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
      set({ loading: true, error: null }, false, "job/listJobs");
      try {
        const query: Record<string, string | number | null | undefined> = {
          limit: opts?.limit ?? 50,
          cursor: opts?.cursor ?? null,
        };
        if (opts?.status) query.status = opts.status;
        const res = await api.get<JobList>("/jobs", { query });
        set({ jobs: res.items, nextCursor: res.next_cursor, loading: false }, false, "job/listJobs-success");
      } catch (e) {
        set({ loading: false, error: e instanceof Error ? e.message : "Failed to load jobs" }, false, "job/listJobs-error");
        throw e;
      }
    },

    getJob: async (jobId) => {
      set({ selectedLoading: true }, false, "job/getJob");
      try {
        const job = await api.get<Job>(`/jobs/${jobId}`);
        set({ selectedJob: job, selectedLoading: false }, false, "job/getJob-success");
        return job;
      } catch (e) {
        set({ selectedLoading: false }, false, "job/getJob-error");
        throw e;
      }
    },

    getGate: async (jobId) => {
      set({ gateLoading: true }, false, "job/getGate");
      try {
        const gate = await api.get<GatePayload>(`/jobs/${jobId}/selection`);
        set({ gate, gateLoading: false }, false, "job/getGate-success");
        return gate;
      } catch (e) {
        set({ gateLoading: false }, false, "job/getGate-error");
        throw e;
      }
    },

    getCost: async (jobId) => {
      set({ costLoading: true }, false, "job/getCost");
      try {
        const cost = await api.get<CostBreakdown>(`/jobs/${jobId}/cost`);
        set({ cost, costLoading: false }, false, "job/getCost-success");
        return cost;
      } catch (e) {
        set({ costLoading: false }, false, "job/getCost-error");
        throw e;
      }
    },

    submitJob: async (payload) => {
      set({ busy: true, error: null }, false, "job/submitJob");
      try {
        const accepted = await api.post<JobAccepted>("/jobs", payload);
        set({ busy: false }, false, "job/submitJob-success");
        return accepted;
      } catch (e) {
        set({ busy: false, error: e instanceof Error ? e.message : "Failed to submit job" }, false, "job/submitJob-error");
        throw e;
      }
    },

    confirmSelection: async (jobId, segmentIds, languages, expectedTotalUsd) => {
      set({ busy: true, error: null }, false, "job/confirmSelection");
      try {
        const job = await api.post<Job>(`/jobs/${jobId}/selection`, {
          segment_ids: segmentIds,
          languages,
          expected_total_usd: expectedTotalUsd,
        });
        set({ selectedJob: job, busy: false }, false, "job/confirmSelection-success");
        return job;
      } catch (e) {
        set({ busy: false }, false, "job/confirmSelection-error");
        throw e;
      }
    },

    cancelJob: async (jobId) => {
      set({ busy: true, error: null }, false, "job/cancelJob");
      try {
        const job = await api.post<Job>(`/jobs/${jobId}/cancel`);
        set({ selectedJob: job, busy: false }, false, "job/cancelJob-success");
        return job;
      } catch (e) {
        set({ busy: false }, false, "job/cancelJob-error");
        throw e;
      }
    },

    retryJob: async (jobId) => {
      set({ busy: true, error: null }, false, "job/retryJob");
      try {
        const job = await api.post<Job>(`/jobs/${jobId}/retry`);
        set({ selectedJob: job, busy: false }, false, "job/retryJob-success");
        return job;
      } catch (e) {
        set({ busy: false }, false, "job/retryJob-error");
        throw e;
      }
    },

    deriveJob: async (payload) => {
      set({ busy: true, error: null }, false, "job/deriveJob");
      try {
        const job = await api.post<Job>(`/jobs/${payload.parentJobId}/derive`, {
          mode: payload.mode,
          target_languages: payload.target_languages,
          lip_sync: payload.lip_sync,
          model_overrides: payload.model_overrides,
          refresh_long_form: payload.refresh_long_form,
        });
        set({ selectedJob: job, busy: false }, false, "job/deriveJob-success");
        return job;
      } catch (e) {
        set({ busy: false }, false, "job/deriveJob-error");
        throw e;
      }
    },

    rotateReviewLink: async (jobId) => {
      set({ busy: true, error: null }, false, "job/rotateReviewLink");
      try {
        const res = await api.post<{ review_url: string; rotated_at: string }>(`/jobs/${jobId}/review-link`);
        set({ busy: false }, false, "job/rotateReviewLink-success");
        return res;
      } catch (e) {
        set({ busy: false }, false, "job/rotateReviewLink-error");
        throw e;
      }
    },

    revokeReviewLink: async (jobId) => {
      set({ busy: true, error: null }, false, "job/revokeReviewLink");
      try {
        await api.delete(`/jobs/${jobId}/review-link`);
        set({ busy: false }, false, "job/revokeReviewLink-success");
      } catch (e) {
        set({ busy: false }, false, "job/revokeReviewLink-error");
        throw e;
      }
    },

    reset: () => {
      set(
        { jobs: [], nextCursor: null, loading: false, error: null, selectedJob: null, selectedLoading: false, gate: null, gateLoading: false, cost: null, costLoading: false, busy: false },
        false,
        "job/reset",
      );
    },
  }));