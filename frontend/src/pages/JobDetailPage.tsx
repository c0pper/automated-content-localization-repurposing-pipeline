/** Job details page (issue #27); Base/Localized Clip playback (issue #30). */
import { useEffect, useState } from "react";
import { useStore } from "zustand";
import { jobStore } from "@/store";
import { interpolate, useTranslation } from "@/lib/useTranslation";
import { baseAssetId, jobAssetUrl, localizedAssetId } from "@/lib/api";
import { errorCodeText, errorText } from "@/lib/errors";
import { EMPTY_VALUE, formatDateTime, joinOrEmpty, orEmpty } from "@/lib/format";
import { formatUsd } from "@/lib/money";
import { openReviewLink } from "@/lib/review";
import { VideoPlayer } from "@/components/VideoPlayer";
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
    <ClipCard
      key={seg.segment_id}
      jobId={job.job_id}
      clip={seg}
      sourceLanguage={job.source_language?.code ?? job.copy_origin?.source_language ?? "en"}
      lipSync={job.lip_sync}
      t={t}
    />
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
        <p className="text-text-dim">{t.created} {formatDateTime(job.created_at, t.locale)}</p>
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
            <dd className="font-medium">{orEmpty(job.stage)}</dd>
          </div>
          <div>
            <dt className="text-text-dim">{t.sourceLanguage}</dt>
            <dd className="text-accent font-medium">{orEmpty(job.source_language?.code)}</dd>
          </div>
          <div>
            <dt className="text-text-dim">{t.targetLanguages}</dt>
            <dd className="font-medium">{joinOrEmpty(job.target_languages)}</dd>
          </div>
        </dl>
        {job.error && (
          <div role="alert" className="mt-3 text-sm text-red-400">
            <strong>{t.jobError}:</strong> <code>{job.error.code}</code>
            <p>{errorCodeText(t, job.error.code, "job")}</p>
            <p>{job.error.retryable ? t.jobErrorRetryable : t.jobErrorNotRetryable}</p>
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
              <dd className="font-medium">{formatUsd(job.cost.job_budget_usd)}</dd>
            </div>
            <div>
              <dt className="text-text-dim">{t.spent}</dt>
              <dd className="font-medium">{formatUsd(job.cost.spent_usd)}</dd>
            </div>
            <div>
              <dt className="text-text-dim">{t.workspaceRemaining}</dt>
              <dd className="font-medium">{formatUsd(job.cost.workspace_remaining_usd)}</dd>
            </div>
            {job.cost.projected_localization_usd != null && (
              <div>
                <dt className="text-text-dim">{t.projectedLocalization}</dt>
                <dd className="font-medium">{formatUsd(job.cost.projected_localization_usd)}</dd>
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
              <dd>{joinOrEmpty(job.selection.segment_ids)}</dd>
            </div>
            <div>
              <dt className="text-text-dim">{t.selectedLanguages}</dt>
              <dd>{joinOrEmpty(job.selection.languages)}</dd>
            </div>
            <div>
              <dt className="text-text-dim">{t.confirmedTotal}</dt>
              <dd>{formatUsd(job.selection.expected_total_usd)}</dd>
            </div>
            <div>
              <dt className="text-text-dim">{t.confirmedAt}</dt>
              <dd>{formatDateTime(job.selection.confirmed_at, t.locale)}</dd>
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
      ) : null}

      <ReviewLinkSection jobId={job.job_id} reviewUrl={job.review_url} t={t} />
    </div>
  );
}

/**
 * Review access controls (issue #32). Shown for any Job status: partial and
 * failed Jobs can still be reviewed. Rotate issues a new token (the old one
 * stops working); Revoke removes it, so old links 404.
 */
function ReviewLinkSection({ jobId, reviewUrl, t }: { jobId: string; reviewUrl: string | null; t: Dict }) {
  const busy = useStore(jobStore, (s) => s.busy);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const href = openReviewLink(reviewUrl);

  const run = async (action: () => Promise<unknown>, doneKey: string) => {
    setNotice(null);
    setError(null);
    try {
      await action();
      setNotice(t[doneKey]);
    } catch (e) {
      setError(errorText(t, e));
    }
  };

  const rotate = () => run(() => jobStore.getState().rotateReviewLink(jobId), "reviewLinkRotated");
  const revoke = () => {
    if (!window.confirm(t.revokeConfirm)) return;
    void run(() => jobStore.getState().revokeReviewLink(jobId), "reviewLinkRevoked");
  };

  return (
    <section aria-labelledby="job-review-link" className="bg-surface rounded-xl border border-border p-6 space-y-3 text-sm">
      <h3 id="job-review-link" className="font-semibold text-sm">{t.reviewLink}</h3>
      {href ? (
        <p>
          <a href={href} className="text-accent hover:underline">
            {t.openReview}
          </a>
        </p>
      ) : (
        <p className="text-text-dim">{t.reviewNoLink}</p>
      )}
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => void rotate()}
          disabled={busy}
          className="rounded-lg bg-accent text-accent-contrast px-3 py-1.5 font-semibold disabled:opacity-50"
        >
          {t.rotate}
        </button>
        {href && (
          <button
            type="button"
            onClick={revoke}
            disabled={busy}
            className="rounded-lg border border-red-400 text-red-400 px-3 py-1.5 font-semibold disabled:opacity-50"
          >
            {t.revoke}
          </button>
        )}
      </div>
      {notice && <p role="status" className="text-text-dim">{notice}</p>}
      {error && <p role="alert" className="text-red-400">{error}</p>}
    </section>
  );
}

interface ClipCardProps {
  jobId: string;
  clip: Clip;
  sourceLanguage: string;
  lipSync: boolean;
  t: Dict;
}

/**
 * Players use the stable `/api/jobs/{id}/assets/{asset_id}` routes, which 302
 * to a fresh presigned URL; the wire `video_asset_url` / `localized_assets`
 * values are raw object-store URLs and only tell us that the asset exists.
 * The backend records a language in `localized_assets` only once that
 * Localized Clip is COMPLETED, so only those languages get a player
 * (`clip_{n}_{lang}` 404s otherwise).
 */
function ClipAssets({ jobId, clip, sourceLanguage, lipSync, t }: ClipCardProps) {
  const langs = Object.entries(clip.localized_assets ?? {})
    .filter(([, url]) => Boolean(url))
    .map(([lang]) => lang);
  return (
    <div className="space-y-3 text-xs" aria-label={t.assets} role="group">
      {clip.video_asset_url && (
        <VideoPlayer
          assetUrl={jobAssetUrl(jobId, baseAssetId(clip))}
          label={t.baseClip}
          captionLanguage={sourceLanguage}
        />
      )}
      {langs.length === 0 ? (
        <p className="text-text-dim">{t.noLocalizedClips}</p>
      ) : (
        langs.map((lang) => {
          const copy = clip.localized_copy?.[lang];
          return (
            <div key={lang} className="border-t border-border pt-2 space-y-1">
              <VideoPlayer
                assetUrl={jobAssetUrl(jobId, localizedAssetId(clip, lang))}
                label={interpolate(t.localizedClip, { lang })}
                captionLanguage={lang}
              />
              <p className="text-text-dim">
                {t.dubbedWithVoiceProfile}
                {lipSync && ` · ${t.lipSyncApplied}`}
              </p>
              {copy && (
                <div role="group" aria-label={`${t.localizedCopy} (${lang})`} lang={lang}>
                  <div className="text-text font-medium">{copy.hook_title}</div>
                  <p className="text-text-dim">{copy.caption}</p>
                </div>
              )}
            </div>
          );
        })
      )}
    </div>
  );
}

function ClipCard(props: ClipCardProps) {
  const { clip, t } = props;
  const headingId = `clip-${clip.segment_id}-heading`;
  const b = clip.score_breakdown;
  return (
    <article aria-labelledby={headingId} className="bg-surface-2 rounded-lg p-3 text-sm space-y-1">
      <h4 id={headingId} className="text-text-dim">
        {t.clip} {clip.segment_id}
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
        <span>{clip.rationale || EMPTY_VALUE}</span>
      </div>
      <ClipAssets {...props} />
    </article>
  );
}
