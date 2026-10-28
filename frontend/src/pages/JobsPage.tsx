/** Jobs list + search + filter page (issues #21, #24). */
import { useEffect, useState } from "react";
import { useStore } from "zustand";
import { jobStore } from "@/store";
import { JobCard } from "@/components/JobCard";
import type { JobStatus } from "@/lib/types";

export function JobsPage() {
  const jobs = useStore(jobStore, (s) => s.jobs);
  const loading = useStore(jobStore, (s) => s.loading);
  const loadJobs = jobStore.getState().listJobs;
  const [statusFilter, setStatusFilter] = useState<string>("");

  useEffect(() => {
    void (async () => {
      try { await loadJobs({ status: statusFilter || undefined }); } catch { /* store */ }
    })();
  }, [loadJobs, statusFilter]);

  if (loading && jobs.length === 0) return <div className="p-6">Loading…</div>;

  const statuses: JobStatus[] = [
    "RECEIVED",
    "PROCESSING",
    "AWAITING_SELECTION",
    "COMPLETED",
    "FAILED",
    "EXPIRED",
    "CANCELLED",
  ];

  return (
    <div className="space-y-6">
      <header className="flex items-center justify-between">
        <h2 className="text-2xl font-bold text-accent">Jobs</h2>
      </header>
      <div className="flex gap-2 mb-4 overflow-x-auto pb-1">
        <button
          onClick={() => setStatusFilter("")}
          className={`text-xs px-3 py-1 rounded ${!statusFilter ? "bg-accent/15 text-accent" : "text-text-dim"}`}
        >
          All
        </button>
        {statuses.map((s) => (
          <button
            key={s}
            onClick={() => setStatusFilter(s)}
            className={`text-xs px-3 py-1 rounded ${statusFilter === s ? "bg-accent/15 text-accent" : "text-text-dim"}`}
          >
            {s}
          </button>
        ))}
      </div>

      {jobs.length === 0 ? (
        <p className="text-text-dim">No jobs match the current filter.</p>
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