/** Jobs list + search + filter page (issues #21, #24). */
import { useEffect, useState } from "react";
import { useStore } from "zustand";
import { jobStore } from "@/store";
import { JobCard } from "@/components/JobCard";
import { useTranslation } from "@/lib/useTranslation";
import { useJobLanguages } from "@/lib/useJobLanguages";
import { statusLabel } from "@/lib/format";
import type { JobStatus } from "@/lib/types";

const STATUSES: JobStatus[] = [
  "RECEIVED",
  "PROCESSING",
  "AWAITING_SELECTION",
  "COMPLETED",
  "FAILED",
  "EXPIRED",
  "CANCELLED",
];

export function JobsPage() {
  const t = useTranslation();
  const jobs = useStore(jobStore, (s) => s.jobs);
  const loading = useStore(jobStore, (s) => s.loading);
  const nextCursor = useStore(jobStore, (s) => s.nextCursor);
  const loadJobs = jobStore.getState().listJobs;
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [keyword, setKeyword] = useState("");
  const languages = useJobLanguages(jobs.map((j) => j.job_id));

  useEffect(() => {
    void (async () => {
      try { await loadJobs({ status: statusFilter || undefined }); } catch { /* store */ }
    })();
  }, [loadJobs, statusFilter]);

  const loadMore = async () => {
    try {
      await loadJobs({ status: statusFilter || undefined, cursor: nextCursor, append: true });
    } catch { /* store */ }
  };

  // The backend has no keyword filter: search runs client-side over the loaded page(s),
  // matching id, status, stage and the Hooks of each Job's Clips (from the per-job details).
  const needle = keyword.trim().toLowerCase();
  const visibleJobs = needle
    ? jobs.filter((j) =>
        [j.job_id, j.status, j.stage ?? "", ...(languages[j.job_id]?.hooks ?? [])].some((field) =>
          field.toLowerCase().includes(needle),
        ),
      )
    : jobs;

  return (
    <div className="space-y-6">
      <header className="flex items-center justify-between">
        <h2 className="text-2xl font-bold text-accent">{t.jobs}</h2>
      </header>
      <div className="flex flex-wrap gap-2 mb-4">
        <input
          type="search"
          aria-label={t.search}
          placeholder={t.jobSearchPlaceholder}
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
          className="flex-1 min-w-[12rem] bg-surface border border-border rounded px-2 py-1 text-sm text-text"
        />
        <label className="flex items-center gap-2 text-xs text-text-dim">
          {t.statusFilter}
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="bg-surface border border-border rounded px-2 py-1 text-text"
          >
            <option value="">{t.statusAll}</option>
            {STATUSES.map((s) => (
              <option key={s} value={s}>{statusLabel(t, s)}</option>
            ))}
          </select>
        </label>
      </div>

      {loading && jobs.length === 0 ? (
        <div className="p-6">{t.loading}</div>
      ) : visibleJobs.length === 0 ? (
        <p className="text-text-dim">{t.noJobsMatch}</p>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {visibleJobs.map((job) => (
            <JobCard key={job.job_id} job={job} languages={languages[job.job_id]} />
          ))}
        </div>
      )}

      {nextCursor && (
        <button
          type="button"
          onClick={loadMore}
          disabled={loading}
          className="text-sm px-4 py-2 rounded border border-border text-accent disabled:opacity-50"
        >
          {loading ? t.loading : t.loadMore}
        </button>
      )}
    </div>
  );
}
