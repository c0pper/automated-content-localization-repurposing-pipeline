/**
 * Read-only review view (issue #32): `#/review/{token}`.
 *
 * Loads GET /api/review/{token} (no auth) and plays whatever assets the
 * manifest lists, for any Job status (partial and failed Jobs included),
 * through the stable `/api/review/{token}/assets/{asset_id}` 302 routes.
 */
import { useEffect, useState } from "react";
import { VideoPlayer } from "@/components/VideoPlayer";
import { isApiError } from "@/lib/api";
import { loadReviewManifest, reviewAssetUrl } from "@/lib/review";
import { interpolate, useTranslation } from "@/lib/useTranslation";
import type { ReviewManifest, ReviewSegment } from "@/lib/types";
import type { Dict } from "@/lib/i18n";

type LoadState =
  | { kind: "loading" }
  | { kind: "loaded"; manifest: ReviewManifest }
  | { kind: "notFound" }
  | { kind: "error" };

export function ReviewPage({ token }: { token: string }) {
  const t = useTranslation();
  const [state, setState] = useState<LoadState>({ kind: "loading" });

  useEffect(() => {
    const controller = new AbortController();
    setState({ kind: "loading" });
    loadReviewManifest(token, controller.signal).then(
      (manifest) => setState({ kind: "loaded", manifest }),
      (err: unknown) => {
        if (controller.signal.aborted) return;
        setState(isApiError(err) && err.status === 404 ? { kind: "notFound" } : { kind: "error" });
      },
    );
    return () => controller.abort();
  }, [token]);

  if (state.kind === "loading") return <div className="p-6">{t.loading}</div>;
  if (state.kind === "notFound") {
    return (
      <div role="alert" className="p-6 text-red-400">
        {t.reviewNotFound}
      </div>
    );
  }
  if (state.kind === "error") {
    return (
      <div role="alert" className="p-6 text-red-400">
        {t.reviewLoadFailed}
      </div>
    );
  }

  const { manifest } = state;
  const sourceLanguage = manifest.source_language?.code ?? manifest.copy_origin?.source_language ?? "en";

  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <h2 className="text-2xl font-bold text-accent">
          {t.reviewTitle}: {manifest.job_id}
        </h2>
        <p className="text-text-dim text-sm">{t.reviewReadOnly}</p>
        <dl className="flex flex-wrap gap-x-6 gap-y-1 text-sm">
          <div>
            <dt className="inline text-text-dim">{t.status}: </dt>
            <dd className="inline font-medium">{manifest.status}</dd>
          </div>
          <div>
            <dt className="inline text-text-dim">{t.sourceLanguage}: </dt>
            <dd className="inline font-medium">{sourceLanguage}</dd>
          </div>
          <div>
            <dt className="inline text-text-dim">{t.targetLanguages}: </dt>
            <dd className="inline font-medium">{manifest.target_languages.join(", ") || "—"}</dd>
          </div>
        </dl>
      </header>

      <section className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
        {manifest.segments.map((seg) => (
          <ReviewClip key={seg.segment_id} token={token} clip={seg} sourceLanguage={sourceLanguage} t={t} />
        ))}
      </section>

      {manifest.content && (manifest.content.linkedin_post || manifest.content.newsletter) && (
        <section className="bg-surface rounded-xl border border-border p-6 space-y-3 text-sm">
          <h3 className="font-semibold text-sm">{t.longFormCopy}</h3>
          {manifest.content.linkedin_post && (
            <div>
              <h4 className="text-text-dim text-xs">{t.linkedinPost}</h4>
              <p className="whitespace-pre-wrap">{manifest.content.linkedin_post}</p>
            </div>
          )}
          {manifest.content.newsletter && (
            <div>
              <h4 className="text-text-dim text-xs">{t.newsletter}</h4>
              <p className="whitespace-pre-wrap">{manifest.content.newsletter}</p>
            </div>
          )}
        </section>
      )}
    </div>
  );
}

interface ReviewClipProps {
  token: string;
  clip: ReviewSegment;
  sourceLanguage: string;
  t: Dict;
}

/**
 * The manifest's asset URLs are absolute (`api_base_url`); players use the
 * same review routes through the app's API base so the dev proxy applies.
 */
function ReviewClip({ token, clip, sourceLanguage, t }: ReviewClipProps) {
  const headingId = `review-clip-${clip.segment_id}-heading`;
  const langs = Object.entries(clip.localized_assets ?? {})
    .filter(([, url]) => Boolean(url))
    .map(([lang]) => lang);
  return (
    <article aria-labelledby={headingId} className="bg-surface-2 rounded-lg p-3 text-sm space-y-2">
      <h3 id={headingId} className="text-text-dim">
        {t.segmentId} {clip.segment_id}
      </h3>
      <div className="text-text font-medium">{clip.hook_title}</div>
      <p className="text-text-dim text-xs">{clip.caption}</p>
      {clip.video_asset_url && (
        <VideoPlayer
          assetUrl={reviewAssetUrl(token, `base_${clip.segment_id}`)}
          label={t.baseClip}
          captionLanguage={sourceLanguage}
        />
      )}
      {langs.map((lang) => {
        const copy = clip.localized_copy?.[lang];
        return (
          <div key={lang} className="border-t border-border pt-2 space-y-1 text-xs">
            <VideoPlayer
              assetUrl={reviewAssetUrl(token, `clip_${clip.segment_id}_${lang}`)}
              label={interpolate(t.localizedClip, { lang })}
              captionLanguage={lang}
            />
            {copy && (
              <div role="group" aria-label={`${t.localizedCopy} (${lang})`} lang={lang}>
                <div className="text-text font-medium">{copy.hook_title}</div>
                <p className="text-text-dim">{copy.caption}</p>
              </div>
            )}
          </div>
        );
      })}
    </article>
  );
}
