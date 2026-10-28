/** Job card for dashboard/jobs list. */
import type { JobSummary } from "@/lib/types";
import { EMPTY_VALUE, formatDateTime, joinOrEmpty, orEmpty, statusLabel } from "@/lib/format";
import { NavLink } from "@/components/NavLink";
import { useTranslation } from "@/lib/useTranslation";
import { openReviewLink } from "@/lib/review";
import type { JobLanguages } from "@/lib/useJobLanguages";

export interface JobCardProps {
  job: JobSummary;
  /**
   * Source/target languages, resolved separately because GET /api/jobs
   * summaries do not include them. `undefined` = not requested / loading,
   * `null` = lookup failed. Both render as a placeholder.
   */
  languages?: JobLanguages | null;
}

const statusColor: Record<JobSummary["status"], string> = {
  RECEIVED: "bg-blue-900/20 text-blue-400",
  PROCESSING: "bg-purple-900/20 text-purple-400 animate-pulse",
  AWAITING_SELECTION: "bg-orange-900/20 text-orange-400 animate-pulse",
  COMPLETED: "bg-green-900/20 text-green-400",
  FAILED: "bg-red-900/20 text-red-400",
  EXPIRED: "bg-yellow-900/20 text-yellow-400",
  CANCELLED: "bg-gray-900/20 text-gray-400",
};

function formatLanguages(codes: string[]): string {
  return joinOrEmpty(codes.map((c) => c.toUpperCase()));
}

export function JobCard({ job, languages }: JobCardProps) {
  const t = useTranslation();
  const reviewHref = openReviewLink(job.review_url);

  return (
    <article className="bg-surface border border-border rounded-xl p-4 hover:border-accent/50 transition">
      <div className="flex items-start justify-between gap-2 mb-1">
        <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium ${statusColor[job.status]}`}>
          {statusLabel(t, job.status)}
        </span>
        <NavLink to={`/jobs/${job.job_id}`} size="text-sm" underline="hover">
          {t.details}
        </NavLink>
      </div>
      <dl className="text-sm text-text grid grid-cols-[auto_1fr] gap-x-3 gap-y-1">
        <dt className="text-text-dim">{t.jobId}</dt>
        <dd>
          <code className="text-text">{job.job_id}</code>
        </dd>
        <dt className="text-text-dim">{t.stage}</dt>
        <dd>{orEmpty(job.stage)}</dd>
        <dt className="text-text-dim">{t.createdAt}</dt>
        <dd>
          <time dateTime={job.created_at ?? undefined}>{formatDateTime(job.created_at, t.locale)}</time>
        </dd>
        <dt className="text-text-dim">{t.sourceLanguage}</dt>
        <dd>{languages?.source ? languages.source.toUpperCase() : EMPTY_VALUE}</dd>
        <dt className="text-text-dim">{t.targetLanguages}</dt>
        <dd>{languages ? formatLanguages(languages.targets) : EMPTY_VALUE}</dd>
      </dl>
      {/* Partial/failed Jobs may already hold a review token; the quick link is for finished work only. */}
      {job.status === "COMPLETED" && reviewHref && (
        <a
          className="mt-3 inline-block text-sm text-accent underline hover:opacity-80"
          href={reviewHref}
        >
          {t.openReview}
        </a>
      )}
    </article>
  );
}
