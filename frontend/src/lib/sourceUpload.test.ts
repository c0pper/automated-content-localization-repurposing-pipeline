import { describe, it, expect } from "vitest";
import { ApiError } from "@/lib/api";
import { createSourceUploader, type UploadApi, type UploadProgress } from "@/lib/sourceUpload";

const MiB = 1024 * 1024;

/** A file of `size` bytes without allocating it: only `size`, `name`, `type` and `slice` are read. */
function fakeFile(size: number, name = "talk.mp4", type = "video/mp4"): File {
  const file = {
    name,
    type,
    size,
    slice: (start: number, end: number) => ({ size: Math.min(end, size) - start }) as Blob,
  };
  return file as unknown as File;
}

type PutBehaviour = (attempt: number) => "ok" | "fail";

/**
 * In-memory upload API: records calls, lets each part fail a chosen number of
 * times, and can hold every PUT open until released so concurrency and abort
 * can be observed.
 */
function fakeUploadApi(partSize: number, opts: { put?: Record<number, PutBehaviour>; hold?: boolean } = {}) {
  const calls = {
    start: [] as { filename: string; content_type: string; size_bytes: number }[],
    signed: [] as number[],
    puts: [] as number[],
    complete: [] as { part_number: number; etag: string }[][],
    abort: [] as string[],
  };
  const attempts = new Map<number, number>();
  let inFlight = 0;
  let maxInFlight = 0;
  const held: (() => void)[] = [];

  const api: UploadApi = {
    async start(req) {
      calls.start.push(req);
      return {
        upload_id: "upl_1",
        key: "uploads/upl_1/source.mp4",
        part_size_bytes: partSize,
        part_count: Math.ceil(req.size_bytes / partSize),
      };
    },
    async signParts(uploadId, numbers) {
      calls.signed.push(...numbers);
      return numbers.map((n) => ({ part_number: n, url: `https://silo.test/${uploadId}/${n}` }));
    },
    async putPart(url, blob, { onProgress, signal }) {
      const n = Number(url.split("/").pop());
      const attempt = (attempts.get(n) ?? 0) + 1;
      attempts.set(n, attempt);
      calls.puts.push(n);
      inFlight += 1;
      maxInFlight = Math.max(maxInFlight, inFlight);
      try {
        onProgress(blob.size / 2);
        if (opts.hold) {
          await new Promise<void>((resolve, reject) => {
            held.push(resolve);
            signal.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")));
          });
        } else {
          await Promise.resolve();
        }
        if ((opts.put?.[n]?.(attempt) ?? "ok") === "fail") throw new TypeError("network down");
        onProgress(blob.size);
        return `"etag-${n}"`;
      } finally {
        inFlight -= 1;
      }
    },
    async complete(uploadId, parts) {
      calls.complete.push(parts);
      return { key: `uploads/${uploadId}/source.mp4` };
    },
    async abort(uploadId) {
      calls.abort.push(uploadId);
    },
  };
  return {
    api,
    calls,
    maxInFlight: () => maxInFlight,
    held: () => held.length,
    release: () => held.splice(0).forEach((r) => r()),
  };
}

const flush = () => new Promise((r) => setTimeout(r, 0));

describe("uploadSource", () => {
  it("uploads every part, completes with the ETags in order and returns the key", async () => {
    const fake = fakeUploadApi(32 * MiB);
    const upload = createSourceUploader(fake.api, { retryDelayMs: 0 });
    const progress: UploadProgress[] = [];

    const result = await upload(fakeFile(100 * MiB), { onProgress: (p) => progress.push(p) });

    expect(result).toEqual({ key: "uploads/upl_1/source.mp4" });
    expect(fake.calls.start).toEqual([{ filename: "talk.mp4", content_type: "video/mp4", size_bytes: 100 * MiB }]);
    expect([...fake.calls.signed].sort()).toEqual([1, 2, 3, 4]);
    expect(fake.calls.complete).toEqual([
      [
        { part_number: 1, etag: '"etag-1"' },
        { part_number: 2, etag: '"etag-2"' },
        { part_number: 3, etag: '"etag-3"' },
        { part_number: 4, etag: '"etag-4"' },
      ],
    ]);
    expect(progress.at(-1)).toEqual({ loadedBytes: 100 * MiB, totalBytes: 100 * MiB });
    expect(fake.calls.abort).toEqual([]);
  });

  it("retries only the failed part, without restarting the upload or over-counting progress", async () => {
    const fake = fakeUploadApi(32 * MiB, { put: { 2: (attempt) => (attempt < 3 ? "fail" : "ok") } });
    const upload = createSourceUploader(fake.api, { retryDelayMs: 0 });
    const progress: UploadProgress[] = [];

    const result = await upload(fakeFile(70 * MiB), { onProgress: (p) => progress.push(p) });

    expect(result.key).toBe("uploads/upl_1/source.mp4");
    expect(fake.calls.start).toHaveLength(1);
    expect(fake.calls.puts.filter((n) => n === 1)).toHaveLength(1);
    expect(fake.calls.puts.filter((n) => n === 2)).toHaveLength(3);
    expect(fake.calls.complete[0].map((p) => p.part_number)).toEqual([1, 2, 3]);
    expect(Math.max(...progress.map((p) => p.loadedBytes))).toBe(70 * MiB);
  });

  it("fails and aborts the Source Upload when a part keeps failing", async () => {
    const fake = fakeUploadApi(32 * MiB, { put: { 1: () => "fail" } });
    const upload = createSourceUploader(fake.api, { retryDelayMs: 0, maxAttempts: 3 });

    await expect(upload(fakeFile(10 * MiB))).rejects.toThrow("network down");
    expect(fake.calls.puts).toEqual([1, 1, 1]);
    expect(fake.calls.complete).toEqual([]);
    expect(fake.calls.abort).toEqual(["upl_1"]);
  });

  it("keeps four parts in flight", async () => {
    const fake = fakeUploadApi(32 * MiB, { hold: true });
    const upload = createSourceUploader(fake.api, { retryDelayMs: 0 });

    const pending = upload(fakeFile(10 * 32 * MiB));
    await flush();
    expect(fake.held()).toBe(4);
    while (fake.held() > 0) {
      fake.release();
      await flush();
    }

    await expect(pending).resolves.toEqual({ key: "uploads/upl_1/source.mp4" });
    expect(fake.maxInFlight()).toBe(4);
    expect(fake.calls.complete[0]).toHaveLength(10);
  });

  it("cancelling stops in-flight parts and aborts the Source Upload", async () => {
    const fake = fakeUploadApi(32 * MiB, { hold: true });
    const upload = createSourceUploader(fake.api, { retryDelayMs: 0 });
    const controller = new AbortController();

    const pending = upload(fakeFile(10 * 32 * MiB), { signal: controller.signal });
    await flush();
    controller.abort();

    await expect(pending).rejects.toMatchObject({ name: "AbortError" });
    expect(fake.calls.puts).toEqual([1, 2, 3, 4]);
    expect(fake.calls.complete).toEqual([]);
    expect(fake.calls.abort).toEqual(["upl_1"]);
  });

  it("aborts a Source Upload whose start returns after the Creator cancelled", async () => {
    const fake = fakeUploadApi(32 * MiB);
    const controller = new AbortController();
    const start = fake.api.start;
    fake.api.start = async (req, signal) => {
      controller.abort();
      return start(req, signal);
    };
    const upload = createSourceUploader(fake.api, { retryDelayMs: 0 });

    await expect(upload(fakeFile(10 * MiB), { signal: controller.signal })).rejects.toMatchObject({
      name: "AbortError",
    });
    expect(fake.calls.puts).toEqual([]);
    expect(fake.calls.abort).toEqual(["upl_1"]);
  });

  it("does not start when already cancelled", async () => {
    const fake = fakeUploadApi(32 * MiB);
    const upload = createSourceUploader(fake.api, { retryDelayMs: 0 });

    await expect(upload(fakeFile(10 * MiB), { signal: AbortSignal.abort() })).rejects.toMatchObject({
      name: "AbortError",
    });
    expect(fake.calls.start).toEqual([]);
  });

  it("does not retry a part the API refuses to sign", async () => {
    const fake = fakeUploadApi(32 * MiB);
    fake.api.signParts = async () => {
      throw new ApiError(409, "upload_not_in_progress", "aborted");
    };
    const upload = createSourceUploader(fake.api, { retryDelayMs: 0 });

    await expect(upload(fakeFile(10 * MiB))).rejects.toMatchObject({ code: "upload_not_in_progress" });
    expect(fake.calls.puts).toEqual([]);
  });
});
