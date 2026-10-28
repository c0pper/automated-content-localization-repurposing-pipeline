/**
 * Video player module (issue #30): `playClip(assetUrl, captionsUrl)` as a
 * component. A native, accessible <video> is enough: Base and Localized Clips
 * have their captions burned in, so `captionsUrl` is only bound as a captions
 * track when a separate caption source exists.
 */
import { useState } from "react";
import { interpolate, useTranslation } from "@/lib/useTranslation";

export interface VideoPlayerProps {
  /** Stable asset URL (e.g. the 302 redirect route), usable as `<video src>`. */
  assetUrl: string;
  /** Accessible name of the player, e.g. "Localized clip (es)". */
  label: string;
  /** Language of the captions shown on the video. */
  captionLanguage: string;
  /** Optional separate caption file; omitted when captions are burned in. */
  captionsUrl?: string;
}

export function VideoPlayer({ assetUrl, label, captionLanguage, captionsUrl }: VideoPlayerProps) {
  const t = useTranslation();
  const [failedUrl, setFailedUrl] = useState<string | null>(null);
  const failed = failedUrl === assetUrl;

  return (
    <figure className="space-y-1">
      <video
        src={assetUrl}
        aria-label={label}
        controls
        playsInline
        preload="metadata"
        onError={() => setFailedUrl(assetUrl)}
        className="w-full aspect-[9/16] max-h-96 rounded bg-black"
      >
        {captionsUrl && (
          <track kind="captions" src={captionsUrl} srcLang={captionLanguage} label={label} default />
        )}
      </video>
      <figcaption className="text-text-dim text-xs flex flex-wrap gap-x-2">
        {!captionsUrl && (
          <span>{interpolate(t.videoCaptionsBurnedIn, { lang: captionLanguage })}</span>
        )}
        <a href={assetUrl} target="_blank" rel="noopener noreferrer" className="text-accent hover:underline">
          {interpolate(t.videoOpen, { label })}
        </a>
      </figcaption>
      {failed && (
        <p role="alert" className="text-red-400 text-xs">
          {t.videoLoadFailed}
        </p>
      )}
    </figure>
  );
}
