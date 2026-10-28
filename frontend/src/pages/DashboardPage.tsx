/** Dashboard overview page (issue #21). */
import { useEffect, useState } from "react";
import { useStore } from "zustand";
import { jobStore } from "@/store";
import { JobCard } from "@/components/JobCard";

export function DashboardPage() {
  const jobs = useStore(jobStore, (s) => s.jobs);
  const loading = useStore(jobStore, (s) => s.loading);
  const nextCursor = useStore(jobStore, (s) => s.nextCursor);
  const loadJobs = jobStore.getState().listJobs;

  useEffect(() => {
    void (async () => {
      try { await loadJobs(); } catch { /* store handles errors */ }
    })();
  }, [loadJobs]);

  if (loading && jobs.length === 0) return <div className="p-6">Loading…</div>;

  return (
    <div className="space-y-6">
      <header className="flex items-center justify-between">
        <h2 className="text-2xl font-bold text-accent">Dashboard</h2>
        <span className="text-sm text-text-dim">{jobs.length} jobs</span>
      </header>

      {jobs.length === 0 ? (
        <div className="bg-surface rounded-xl border border-border p-8 text-center text-text-dim">
          No jobs yet. Submit your first video to get started.
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {jobs.map((job) => (
            <JobCard key={job.job_id} job={job} />
          ))}
        </div>
      )}
    </div>
  );
}