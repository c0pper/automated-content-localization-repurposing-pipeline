/** Job details page (issue #27). */
import { useEffect, useState } from "react";
import { jobStore, profileStore } from "@/store";
import { useTranslation } from "@/lib/useTranslation";
import type { Job } from "@/lib/types";

export function JobDetailPage({ location }: { location: { hash: string } }) {
  const jobId = location.hash.replace(/^#/, "");
  const t = useTranslation();
  const job = jobStore((s) => s.selectedJob);
  const ws = profileStore((s) => s.workspace);
  const loadJobs = jobStore.getState().listJobs;
  const [gate, setGate] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    void (async () => {
      try { await jobStore.getState().getJob(jobId ?? ""); } catch { /* err */ }
      try { await jobStore.getState().getGate(jobId ?? ""); } catch { /* err */ }
      setLoading(false);
    })();
  }, [jobId, loadJobs]);

  if (loading && !job) return <div className="p-6">Loading…</div>;

  // Auto-load workspace if we have a job and no workspace loaded yet
  useEffect(() => {
    if (job && ws?.workspace_id == null) {
      void profileStore.getState().loadWorkspace();
    }
  }, [job, ws?.workspace_id]);

  if (!job) return <div className="p-6 text-red-400">Job not found.</div>;

  // Build segment cards from the job's segments array
  const segmentCards = job.segments.map((seg) => (
    <div
      key={seg.segment_id}
      className="bg-surface-2 rounded-lg p-3 text-sm mb-2"
    >
      <div className="text-text-dim">Segment {seg.segment_id}</div>
      <div className="text-text font-medium">{seg.hook_title}</div>
      <div className="text-text-dim text-xs mt-0.5">
        {seg.start_time} – {seg.end_time}
      </div>
      <div className="text-text-dim text-xs mt-0.5">Score: {seg.selection_score} / 100</div>
      <div className="text-text-dim text-xs mt-0.5">Rationale: {seg.rationale || "—"}</div>
    </div>
  ));

  // Build cost matrix cells visible in gate view
  const costMatrixCells = job.selection
    ? job.selection.languages.map((lang) =>
        job.segments.map((seg) => ({
          segment_id: seg.segment_id,
          language: lang,
          translation_usd: "0.00",
          voice_usd: "0.00",
          lip_sync_usd: "0.00",
        }))
      )
    : [];

  // Build a simplified cost summary
  const costSummary = () => {
    if (!job.cost) return null;
    const { job_budget_usd, spent_usd, workspace_remaining_usd, entries } = job.cost;
    return (
      <div>
        <div>
          <span className="text-text-dim">Job budget</span>
          <strong>{job_budget_usd}</strong>
        </div>
        <div>
          <span className="text-text-dim">Spent</span>
          <strong>{spent_usd}</strong>
        </div>
        <div>
          <span className="text-text-dim">Remaining</span>
          <strong>{workspace_remaining_usd}</strong>
        </div>
        {entries.length > 0 && (
          <div className="mt-2 text-xs text-text-dim">
            {entries.length} entries recorded
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="space-y-6">
      <header>
        <h2 className="text-2xl font-bold text-accent">{job.job_id}</h2>
        <p className="text-text-dim">Created {job.created_at ?? "—"}</p>
      </header>

      {/* Job status and overall info */}
      <section className="bg-surface rounded-xl border border-border p-4">
        <div className="grid grid-cols-3 gap-3 text-sm">
          <div>
            <span className="text-text-dim">Status</span>
            <span className={`font-medium ${job.status === "COMPLETED" ? "text-green-400" : job.status === "FAILED" ? "text-red-400" : job.status === "AWAITING_SELECTION" ? "text-orange-400" : "text-text"}`}>
              {job.status}
            </span>
          </div>
          <div>
            <span className="text-text-dim">Stage</span>
            <span className="font-medium">{job.stage ?? "—"}</span>
          </div>
          <div>
            <span className="text-text-dim">Source language</span>
            {job.source_language?.code ? (
              <span className="text-accent font-medium">{job.source_language.code}</span>
            ) : (
              <span className="text-text-dim">—</span>
            )}
          </div>
        </div>
      </section>

      {/* Cost summary */}
      {costSummary()}

      {/* Segments grid */}
      <section className="bg-surface rounded-xl border border-border p-6 space-y-4">
        <h3 className="font-semibold text-sm">{t.segments}: {job.segments.length}</h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {segmentCards}
        </div>
      </section>

      {/* Selection Gate or Completed state */}
      {job.status === "AWAITING_SELECTION" ? (
        <section className="bg-surface rounded-xl border border-border p-6">
          <h3 className="font-semibold text-sm">Selection Gate</h3>
          <p className="text-text-dim text-sm mb-4">
            Select clips and target languages to localize. Costs use the workspace rate card.
          </p>
          <div className="overflow-x-auto">
            <table className="w-full text-sm text-text">
              <thead>
                <tr className="text-text-dim border-b border-border bg-surface-2 sticky top-0">
                  <th>{t.segment}</th>
                  {job.target_languages.map((lang) => (
                    <th key={lang} className="text-left font-medium">{lang}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {job.segments.map((seg) => (
                  <tr key={seg.segment_id} className="border-b border-border bg-surface-2">
                    <td className="font-medium text-text">
                      {seg.segment_id}: {seg.hook_title}
                    </td>
                    {job.target_languages.map((lang) => (
                      <td key={lang} className="text-text-dim">
                        {seg.segment_id} × {lang}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {job.selection_matrix && (
            <div className="mt-4 bg-surface-2 rounded-lg p-3 text-xs text-text-dim">
              <strong>Projected total:</strong> {job.projected_total_usd}
            </div>
          )}
        </section>
      ) : (
        <section className="bg-surface rounded-xl border border-border p-6">
          <h3 className="font-semibold text-sm">Review</h3>
          <p className="text-text-dim text-sm">
            Job complete — ready for review. Review link:{" "}
            <a
              href={job.review_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-accent hover:underline"
            >
              {job.review_url}
            </a>
          </p>
        </section>
      )}
    </div>
  );
}