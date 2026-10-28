/** Job details page (issue #27). */
import { useEffect, useState } from "react";
import { useStore } from "zustand";
import { jobStore } from "@/store";
import { interpolate, useTranslation } from "@/lib/useTranslation";
import { jobAssetUrl } from "@/lib/api";
import type { Clip } from "@/lib/types";
import type { Dict } from "@/lib/i18n";

export function JobDetailPage({ jobId }: { jobId: string }) {
  const t = useTranslation();
  const selectedJob = useStore(jobStore, (s) => s.selectedJob);
  // Id whose load attempt has finished; guards against showing a stale job.
  const [loadedId, setLoadedId] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    void (async () => {
      if (!jobId) return;
      try {
        await jobStore.getState().getJob(jobId);
      } catch { /* rendered as not found below */ }
      if (active) setLoadedId(jobId);
    })();
    return () => { active = false; };
  }, [jobId]);

  const job = selectedJob?.job_id === jobId ? selectedJob : null;
  if (!job && loadedId !== jobId) return <div className="p-6">{t.loading}</div>;
  if (!job) return <div className="p-6 text-red-400">{t.jobNotFound}</div>;

  const segmentCards = job.segments.map((seg) => (
    <ClipCard key={seg.segment_id} jobId={job.job_id} clip={seg} t={t} />
  ));
  const statusClass =
    job.status === "COMPLETED" ? "text-green-400"
    : job.status === "FAILED" ? "text-red-400"
    : job.status === "AWAITING_SELECTION" ? "text-orange-400"
    : "text-text";

  return (
    <div className="space-y-6">
      <header>
        <h2 className="text-2xl font-bold text-accent">{job.job_id}</h2>
        <p className="text-text-dim">{t.created} {job.created_at ?? "—"}</p>
      </header>

      {/* Job status and overall info */}
      <section className="bg-surface rounded-xl border border-border p-4">
        <dl className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm">
          <div>
            <dt className="text-text-dim">{t.status}</dt>
            <dd className={`font-medium ${statusClass}`}>{job.status}</dd>
          </div>
          <div>
            <dt className="text-text-dim">{t.stage}</dt>
            <dd className="font-medium">{job.stage ?? "—"}</dd>
          </div>
          <div>
            <dt className="text-text-dim">{t.sourceLanguage}</dt>
            <dd className="text-accent font-medium">{job.source_language?.code ?? "—"}</dd>
          </div>
          <div>
            <dt className="text-text-dim">{t.targetLanguages}</dt>
            <dd className="font-medium">{job.target_languages.join(", ") || "—"}</dd>
          </div>
        </dl>
        {job.error && (
          <div role="alert" className="mt-3 text-sm text-red-400">
            <strong>{t.jobError}:</strong> <code>{job.error.code}</code> — {job.error.message}
          </div>
        )}
      </section>

      {/* Cost summary */}
      {job.cost && (
        <section aria-labelledby="job-costs" className="bg-surface rounded-xl border border-border p-4">
          <h3 id="job-costs" className="font-semibold text-sm mb-2">{t.costs}</h3>
          <dl className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm">
            <div>
              <dt className="text-text-dim">{t.jobBudget}</dt>
              <dd className="font-medium">{job.cost.job_budget_usd}</dd>
            </div>
            <div>
              <dt className="text-text-dim">{t.spent}</dt>
              <dd className="font-medium">{job.cost.spent_usd}</dd>
            </div>
            <div>
              <dt className="text-text-dim">{t.workspaceRemaining}</dt>
              <dd className="font-medium">{job.cost.workspace_remaining_usd}</dd>
            </div>
            {job.cost.projected_localization_usd != null && (
              <div>
                <dt className="text-text-dim">{t.projectedLocalization}</dt>
                <dd className="font-medium">{job.cost.projected_localization_usd}</dd>
              </div>
            )}
          </dl>
        </section>
      )}

      {/* Confirmed selection (payment) state */}
      <section aria-labelledby="job-selection" className="bg-surface rounded-xl border border-border p-4 text-sm">
        <h3 id="job-selection" className="font-semibold text-sm mb-2">{t.selection}</h3>
        {job.selection ? (
          <dl className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div>
              <dt className="text-text-dim">{t.selectedClips}</dt>
              <dd>{job.selection.segment_ids.join(", ") || "—"}</dd>
            </div>
            <div>
              <dt className="text-text-dim">{t.selectedLanguages}</dt>
              <dd>{job.selection.languages.join(", ") || "—"}</dd>
            </div>
            <div>
              <dt className="text-text-dim">{t.confirmedTotal}</dt>
              <dd>{job.selection.expected_total_usd}</dd>
            </div>
            <div>
              <dt className="text-text-dim">{t.confirmedAt}</dt>
              <dd>{job.selection.confirmed_at ?? "—"}</dd>
            </div>
          </dl>
        ) : (
          <p className="text-text-dim">{t.noneSelected}</p>
        )}
      </section>

      {/* Segments grid */}
      <section className="bg-surface rounded-xl border border-border p-6 space-y-4">
        <h3 className="font-semibold text-sm">{t.segments}: {job.segments.length}</h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {segmentCards}
        </div>
      </section>

      {/* Long-form copy stays in the Source Language in v1 */}
      {job.content && (job.content.linkedin_post || job.content.newsletter) && (
        <section className="bg-surface rounded-xl border border-border p-6 space-y-3 text-sm">
          <h3 className="font-semibold text-sm">{t.longFormCopy}</h3>
          {job.content.linkedin_post && (
            <div>
              <h4 className="text-text-dim text-xs">{t.linkedinPost}</h4>
              <p className="whitespace-pre-wrap">{job.content.linkedin_post}</p>
            </div>
          )}
          {job.content.newsletter && (
            <div>
              <h4 className="text-text-dim text-xs">{t.newsletter}</h4>
              <p className="whitespace-pre-wrap">{job.content.newsletter}</p>
            </div>
          )}
        </section>
      )}

      {/* Selection Gate or Completed state */}
      {job.status === "AWAITING_SELECTION" ? (
        <section aria-labelledby="job-gate" className="bg-surface rounded-xl border border-border p-6 space-y-2">
          <h3 id="job-gate" className="font-semibold text-sm">{t.gateTitle}</h3>
          <p className="text-text-dim text-sm">{t.gateAwaiting}</p>
          <a
            href={`#/jobs/${encodeURIComponent(job.job_id)}/localization`}
            className="inline-block rounded-lg bg-accent text-accent-contrast px-4 py-2 font-semibold"
          >
            {t.openGate}
          </a>
        </section>
      ) : job.review_url ? (
        <section className="bg-surface rounded-xl border border-border p-6">
          <h3 className="font-semibold text-sm">{t.reviewLink}</h3>
          <p className="text-text-dim text-sm">
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
      ) : null}
    </div>
  );
}

/**
 * Asset links use the stable `/api/jobs/{id}/assets/{asset_id}` routes, which
 * 302 to a fresh presigned URL; the wire `video_asset_url` / `localized_assets`
 * values are raw object-store URLs and only tell us that the asset exists.
 */
function ClipAssets({ jobId, clip, t }: { jobId: string; clip: Clip; t: Dict }) {
  const langs = Object.keys(clip.localized_assets ?? {});
  const linkClass = "text-accent hover:underline";
  return (
    <ul className="text-xs space-y-0.5" aria-label={t.assets}>
      {clip.video_asset_url && (
        <li>
          <a
            href={jobAssetUrl(jobId, `base_${clip.segment_id}`)}
            target="_blank"
            rel="noopener noreferrer"
            className={linkClass}
          >
            {t.baseClip}
          </a>
        </li>
      )}
      {langs.length === 0 ? (
        <li className="text-text-dim">{t.noLocalizedClips}</li>
      ) : (
        langs.map((lang) => (
          <li key={lang}>
            <a
              href={jobAssetUrl(jobId, `clip_${clip.segment_id}_${lang}`)}
              target="_blank"
              rel="noopener noreferrer"
              className={linkClass}
            >
              {interpolate(t.localizedClip, { lang })}
            </a>
          </li>
        ))
      )}
    </ul>
  );
}

function ClipCard({ jobId, clip, t }: { jobId: string; clip: Clip; t: Dict }) {
  const headingId = `clip-${clip.segment_id}-heading`;
  const b = clip.score_breakdown;
  return (
    <article aria-labelledby={headingId} className="bg-surface-2 rounded-lg p-3 text-sm space-y-1">
      <h4 id={headingId} className="text-text-dim">
        {t.segmentId} {clip.segment_id}
      </h4>
      <div className="text-text-dim text-xs">
        {clip.start_time} – {clip.end_time}
      </div>
      <div className="text-text font-medium">{clip.hook_title}</div>
      <p className="text-text-dim text-xs">{clip.caption}</p>
      <div className="text-xs">
        {t.scoreBreakdown}: {clip.selection_score}
      </div>
      {b && (
        <ul className="text-text-dim text-xs">
          <li>{t.hookStrength}: {b.hook_strength}</li>
          <li>{t.standaloneClarity}: {b.standalone_clarity}</li>
          <li>{t.emotionalPayoff}: {b.emotional_payoff}</li>
          <li>{t.businessFit}: {b.business_fit}</li>
        </ul>
      )}
      <div className="text-text-dim text-xs">
        <span>{t.rationale}: </span>
        <span>{clip.rationale || "—"}</span>
      </div>
      <ClipAssets jobId={jobId} clip={clip} t={t} />
      {Object.entries(clip.localized_copy ?? {}).map(([lang, copy]) => (
        <div
          key={lang}
          role="group"
          aria-label={`${t.localizedCopy} (${lang})`}
          lang={lang}
          className="border-t border-border pt-1 text-xs"
        >
          <div className="text-text-dim uppercase">{lang}</div>
          <div className="text-text font-medium">{copy.hook_title}</div>
          <p className="text-text-dim">{copy.caption}</p>
        </div>
      ))}
    </article>
  );
}
