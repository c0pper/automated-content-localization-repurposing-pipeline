/** Job card for dashboard/jobs list. */
import { JobSummary } from "@/lib/types";
import { NavLink } from "@/components/NavLink";

export interface JobCardProps {
  job: JobSummary;
}

export function JobCard({ job }: JobCardProps) {
  const statusColor: Record<JobSummary["status"], string> = {
    RECEIVED: "bg-blue-900/20 text-blue-400",
    PROCESSING: "bg-purple-900/20 text-purple-400 animate-pulse",
    AWAITING_SELECTION: "bg-orange-900/20 text-orange-400 animate-pulse",
    COMPLETED: "bg-green-900/20 text-green-400",
    FAILED: "bg-red-900/20 text-red-400",
    EXPIRED: "bg-yellow-900/20 text-yellow-400",
    CANCELLED: "bg-gray-900/20 text-gray-400",
  };

  return (
    <article className="bg-surface border border-border rounded-xl p-4 hover:border-accent/50 transition cursor-pointer">
      <div className="flex items-start justify-between gap-2 mb-1">
        <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium ${statusColor[job.status]}`}>
          {job.status.charAt(0) + job.status.slice(1).toLowerCase()}
        </span>
        <NavLink to={`/jobs/${job.job_id}`} size="text-sm" underline="hover">
          Details
        </NavLink>
      </div>
      <div className="text-sm text-text">
        <div className="text-text-dim">Job ID</div>
        <code className="text-text">{job.job_id}</code>
        <div className="mt-1 text-text-dim text-xs">Stage</div>
        <span className="text-xs">{job.stage ?? "—"}</span>
      </div>
      {job.review_url && (
        <div className="mt-2 text-xs text-accent">
          Review link available
        </div>
      )}
    </article>
  );
}