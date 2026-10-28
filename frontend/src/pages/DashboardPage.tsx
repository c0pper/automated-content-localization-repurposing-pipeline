/** Dashboard overview page (issue #21). */
import { useEffect } from "react";
import { useStore } from "zustand";
import { jobStore } from "@/store";
import { JobCard } from "@/components/JobCard";
import { useJobLanguages } from "@/lib/useJobLanguages";
import { interpolate, useTranslation } from "@/lib/useTranslation";

export function DashboardPage() {
  const t = useTranslation();
  const jobs = useStore(jobStore, (s) => s.jobs);
  const loading = useStore(jobStore, (s) => s.loading);
  const nextCursor = useStore(jobStore, (s) => s.nextCursor);
  const languages = useJobLanguages(jobs.map((j) => j.job_id));

  const loadMore = async (cursor: string) => {
    try {
      await jobStore.getState().listJobs({ cursor, append: true });
    } catch {
      /* store handles errors */
    }
  };

  useEffect(() => {
    void (async () => {
      try {
        await jobStore.getState().listJobs();
      } catch {
        /* store handles errors */
      }
    })();
  }, []);

  if (loading && jobs.length === 0) return <div className="p-6">{t.loading}</div>;

  return (
    <div className="space-y-6">
      <header className="flex items-center justify-between">
        <h2 className="text-2xl font-bold text-accent">{t.dashboard}</h2>
        <span className="text-sm text-text-dim">
          {interpolate(t.dashboardJobCount, { count: jobs.length })}
        </span>
      </header>

      {jobs.length === 0 ? (
        <div className="bg-surface rounded-xl border border-border p-8 text-center text-text-dim">
          {t.noJobs}
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {jobs.map((job) => (
            <JobCard key={job.job_id} job={job} languages={languages[job.job_id]} />
          ))}
        </div>
      )}

      {nextCursor && (
        <div className="text-center">
          <button
            type="button"
            className="px-4 py-2 rounded-lg border border-border text-accent hover:border-accent disabled:opacity-50"
            disabled={loading}
            onClick={() => void loadMore(nextCursor)}
          >
            {loading ? t.loading : t.loadMore}
          </button>
        </div>
      )}
    </div>
  );
}
