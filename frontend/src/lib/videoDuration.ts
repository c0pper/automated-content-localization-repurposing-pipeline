/**
 * Reads a picked file's duration in the browser, before and independently of
 * its Source Upload (US33). Only a hint: some codecs can't be decoded here, so
 * an unreadable file yields `null` and ingest stays the authority on length.
 */

export type ReadDuration = (file: File) => Promise<number | null>;

/** Give up on files whose metadata the browser never reports. */
const READ_TIMEOUT_MS = 10_000;

/** Duration in seconds from the file's metadata, or `null` when the browser can't read it. */
export const readVideoDuration: ReadDuration = (file) =>
  new Promise((resolve) => {
    let url: string;
    let video: HTMLVideoElement;
    try {
      url = URL.createObjectURL(file);
      video = document.createElement("video");
    } catch {
      resolve(null);
      return;
    }
    const finish = (seconds: number | null) => {
      clearTimeout(timer);
      video.onloadedmetadata = video.onerror = null;
      video.removeAttribute("src");
      URL.revokeObjectURL(url);
      resolve(seconds);
    };
    const timer = setTimeout(() => finish(null), READ_TIMEOUT_MS);
    video.preload = "metadata";
    video.onloadedmetadata = () =>
      finish(Number.isFinite(video.duration) && video.duration > 0 ? video.duration : null);
    video.onerror = () => finish(null);
    video.src = url;
  });
