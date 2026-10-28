/**
 * Source Upload (ADR 0022): sends a file straight to object storage as a
 * presigned multipart upload. The API only starts the upload, signs parts on
 * demand and completes it; the bytes never pass through it. The returned key is
 * then submitted as an `object` source.
 */
import { api, ApiError } from "./api";

export interface UploadProgress {
  loadedBytes: number;
  totalBytes: number;
}

export interface UploadSourceOptions {
  onProgress?: (progress: UploadProgress) => void;
  signal?: AbortSignal;
}

export type UploadSource = (file: File, options?: UploadSourceOptions) => Promise<{ key: string }>;

export interface StartedUpload {
  upload_id: string;
  key: string;
  part_size_bytes: number;
  part_count: number;
}

export interface UploadedPart {
  part_number: number;
  etag: string;
}

/** The calls `uploadSource` makes; the HTTP adapter is below, tests use a fake. */
export interface UploadApi {
  start(
    request: { filename: string; content_type: string; size_bytes: number },
    signal: AbortSignal,
  ): Promise<StartedUpload>;
  signParts(uploadId: string, numbers: number[], signal: AbortSignal): Promise<{ part_number: number; url: string }[]>;
  /** PUTs one part and resolves with its ETag. */
  putPart(
    url: string,
    blob: Blob,
    options: { onProgress: (loadedBytes: number) => void; signal: AbortSignal },
  ): Promise<string>;
  complete(uploadId: string, parts: UploadedPart[], signal: AbortSignal): Promise<{ key: string }>;
  abort(uploadId: string): Promise<void>;
}

export interface UploaderOptions {
  /** Parts in flight at once. */
  concurrency?: number;
  /** Tries per part before the upload fails. */
  maxAttempts?: number;
  /** Delay before the first retry of a part; doubles on each further retry. */
  retryDelayMs?: number;
}

export function createSourceUploader(uploadApi: UploadApi, uploaderOptions: UploaderOptions = {}): UploadSource {
  const { concurrency = 4, maxAttempts = 4, retryDelayMs = 1000 } = uploaderOptions;

  return async (file, { onProgress, signal } = {}) => {
    if (signal) throwIfAborted(signal);
    const controller = new AbortController();
    const stop = () => controller.abort();
    signal?.addEventListener("abort", stop);
    const inner = controller.signal;

    const started = await uploadApi.start(
      { filename: file.name, content_type: contentTypeOf(file), size_bytes: file.size },
      inner,
    );
    const loaded = new Array<number>(started.part_count).fill(0);
    const report = () =>
      onProgress?.({ loadedBytes: loaded.reduce((a, b) => a + b, 0), totalBytes: file.size });

    // Each attempt signs afresh, so a URL that expired while queued is replaced.
    const uploadPart = async (number: number): Promise<UploadedPart> => {
      const begin = (number - 1) * started.part_size_bytes;
      const blob = file.slice(begin, Math.min(begin + started.part_size_bytes, file.size));
      for (let attempt = 1; ; attempt++) {
        try {
          const [{ url }] = await uploadApi.signParts(started.upload_id, [number], inner);
          const etag = await uploadApi.putPart(url, blob, {
            signal: inner,
            onProgress: (bytes) => {
              loaded[number - 1] = bytes;
              report();
            },
          });
          return { part_number: number, etag };
        } catch (err) {
          loaded[number - 1] = 0;
          if (inner.aborted || attempt >= maxAttempts || !isRetryable(err)) throw err;
          await sleep(retryDelayMs * 2 ** (attempt - 1), inner);
        }
      }
    };

    try {
      const parts: UploadedPart[] = [];
      let next = 1;
      const worker = async () => {
        while (next <= started.part_count && !inner.aborted) {
          const number = next++;
          parts.push(await uploadPart(number));
        }
      };
      await Promise.all(Array.from({ length: Math.min(concurrency, started.part_count) }, worker));
      throwIfAborted(inner);

      parts.sort((a, b) => a.part_number - b.part_number);
      const completed = await uploadApi.complete(started.upload_id, parts, inner);
      return { key: completed.key };
    } catch (err) {
      // Stop the other parts, then discard the upload; the bucket lifecycle rule
      // cleans up if this call is lost too.
      controller.abort();
      uploadApi.abort(started.upload_id).catch(() => {});
      throw signal?.aborted ? abortError() : err;
    } finally {
      signal?.removeEventListener("abort", stop);
    }
  };
}

/** Storage and network failures are retried; a refusal from the API is final. */
function isRetryable(err: unknown): boolean {
  if (err instanceof ApiError) return err.status === 0 || err.status >= 500;
  return true;
}

function abortError(): DOMException {
  return new DOMException("The upload was cancelled", "AbortError");
}

function throwIfAborted(signal: AbortSignal): void {
  if (signal.aborted) throw abortError();
}

function sleep(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal.aborted) return reject(abortError());
    const timer = setTimeout(() => {
      signal.removeEventListener("abort", onAbort);
      resolve();
    }, ms);
    const onAbort = () => {
      clearTimeout(timer);
      reject(abortError());
    };
    signal.addEventListener("abort", onAbort, { once: true });
  });
}

/**
 * The real upload API: control calls go through the cookie-authenticated
 * client, parts go straight to the presigned URL. Parts use XHR because fetch
 * reports no upload progress. Storage needs CORS to expose `ETag` (ADR 0022).
 */
export const httpUploadApi: UploadApi = {
  start: (request, signal) => api.post<StartedUpload>("/uploads", request, { signal }),
  async signParts(uploadId, numbers, signal) {
    const res = await api.get<{ parts: { part_number: number; url: string }[] }>(
      `/uploads/${encodeURIComponent(uploadId)}/parts`,
      { query: { numbers: numbers.join(",") }, signal },
    );
    return res.parts;
  },
  putPart: (url, blob, { onProgress, signal }) =>
    new Promise<string>((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      const failed = (message: string) => reject(new ApiError(0, "upload_failed", message));
      const onAbort = () => xhr.abort();
      xhr.open("PUT", url);
      xhr.upload.onprogress = (e) => onProgress(e.loaded);
      xhr.onload = () => {
        signal.removeEventListener("abort", onAbort);
        const etag = xhr.getResponseHeader("ETag");
        if (xhr.status >= 200 && xhr.status < 300 && etag) resolve(etag);
        else failed(`Part upload failed with HTTP ${xhr.status}`);
      };
      xhr.onerror = () => {
        signal.removeEventListener("abort", onAbort);
        failed("Part upload failed");
      };
      xhr.onabort = () => reject(abortError());
      signal.addEventListener("abort", onAbort, { once: true });
      xhr.send(blob);
    }),
  complete: (uploadId, parts, signal) =>
    api.post<{ key: string }>(`/uploads/${encodeURIComponent(uploadId)}/complete`, { parts }, { signal }),
  abort: (uploadId) => api.delete<void>(`/uploads/${encodeURIComponent(uploadId)}`),
};

/** Starts a Source Upload of `file` and resolves with its key once completed. */
export const uploadSource: UploadSource = createSourceUploader(httpUploadApi);

/** Browsers sometimes report no type for .mov/.m4v; the API needs one. */
const CONTENT_TYPES: Record<string, string> = {
  mp4: "video/mp4",
  m4v: "video/x-m4v",
  mov: "video/quicktime",
};

function contentTypeOf(file: File): string {
  if (file.type) return file.type;
  const ext = file.name.split(".").pop()?.toLowerCase() ?? "";
  return CONTENT_TYPES[ext] ?? "application/octet-stream";
}
