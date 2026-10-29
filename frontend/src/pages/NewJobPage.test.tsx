import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { ApiError } from "@/lib/api";
import type { UploadSourceOptions } from "@/lib/sourceUpload";
import { NewJobPage } from "@/pages/NewJobPage";
import { jobStore, profileStore } from "@/store";
import type { WorkspaceSettings } from "@/lib/types";

const workspace: WorkspaceSettings = {
  workspace_id: "ws_test",
  target_language_allowlist: ["en", "es", "de"],
  default_models: {
    planning: "openrouter/anthropic/claude-3.5-sonnet",
    copy: "openrouter/anthropic/claude-3.5-sonnet",
    translation: "openrouter/openai/gpt-4o-mini",
  },
  job_budget_usd: "50.00",
  monthly_budget_usd: "500.00",
  max_concurrent_jobs: 3,
  max_video_minutes: 90,
  current_month_spend_usd: "10.00",
  remaining_usd: "490.00",
  voice_profile: null,
};

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/** A controllable `uploadSource`: the test drives progress and decides how it ends. */
function stubUpload() {
  let options: UploadSourceOptions = {};
  let settle: { resolve: (v: { key: string }) => void; reject: (e: unknown) => void } | null = null;
  const fn = vi.fn((_file: File, opts: UploadSourceOptions = {}) => {
    options = opts;
    return new Promise<{ key: string }>((resolve, reject) => {
      settle = { resolve, reject };
      opts.signal?.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")));
    });
  });
  return {
    fn,
    signal: () => options.signal!,
    progress: (loadedBytes: number, totalBytes: number) =>
      act(() => options.onProgress?.({ loadedBytes, totalBytes })),
    finish: (key: string) => act(async () => settle!.resolve({ key })),
    fail: (err: unknown) => act(async () => settle!.reject(err)),
  };
}

const video = new File(["0123456789"], "talk.mp4", { type: "video/mp4" });

/** A controllable `readDuration`: the test decides what each read resolves to. */
function stubDuration() {
  const pending: Array<(seconds: number | null) => void> = [];
  const fn = vi.fn(() => new Promise<number | null>((resolve) => pending.push(resolve)));
  return {
    fn,
    /** Resolves the `index`-th read (default: the latest). */
    read: (seconds: number | null, index = pending.length - 1) =>
      act(async () => pending[index](seconds)),
  };
}

function pickFile(file: File = video) {
  fireEvent.change(screen.getByLabelText("Video file"), { target: { files: [file] } });
}

function beforeUnloadBlocked(): boolean {
  const event = new Event("beforeunload", { cancelable: true });
  window.dispatchEvent(event);
  return event.defaultPrevented;
}

describe("NewJobPage", () => {
  const mockFetch = vi.fn();

  beforeEach(() => {
    globalThis.fetch = mockFetch;
    mockFetch.mockReset();
    profileStore.setState({ workspace: null, loading: false, error: null, notice: null });
    jobStore.getState().reset();
  });

  afterEach(() => {
    cleanup();
  });

  it("loads workspace defaults and preselects them in a curated dropdown per task", async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse(workspace));
    render(<NewJobPage onCreated={() => {}} />);

    const planning = (await screen.findByLabelText("Planning model")) as HTMLSelectElement;
    const copy = screen.getByLabelText("Copy model") as HTMLSelectElement;
    const translation = screen.getByLabelText("Translation model") as HTMLSelectElement;

    expect(mockFetch.mock.calls[0][0]).toEqual(expect.stringContaining("/api/workspace"));
    expect(planning.value).toBe("openrouter/anthropic/claude-3.5-sonnet");
    expect(copy.value).toBe("openrouter/anthropic/claude-3.5-sonnet");
    expect(translation.value).toBe("openrouter/openai/gpt-4o-mini");
    expect(Array.from(translation.options).map((o) => o.value)).toEqual([
      "openrouter/anthropic/claude-3.5-sonnet",
      "openrouter/openai/gpt-4o-mini",
      "openrouter/google/gemini-1.5-flash",
    ]);
    expect(Array.from(planning.options).map((o) => o.value)).toContain(
      "openrouter/google/gemini-1.5-pro",
    );
  });

  it("submits POST /api/jobs with an Idempotency-Key and only the changed model overrides", async () => {
    const onCreated = vi.fn();
    mockFetch.mockResolvedValueOnce(jsonResponse(workspace));
    mockFetch.mockResolvedValueOnce(
      jsonResponse({ job_id: "job_1", status: "RECEIVED", created_at: "2026-10-28T00:00:00Z" }, 202),
    );
    render(<NewJobPage onCreated={onCreated} />);

    const translation = await screen.findByLabelText("Translation model");
    fireEvent.click(screen.getByLabelText("URL"));
    fireEvent.change(screen.getByLabelText("Video URL"), {
      target: { value: "https://example.com/talk.mp4" },
    });
    fireEvent.click(screen.getByLabelText("es"));
    fireEvent.click(screen.getByLabelText("de"));
    fireEvent.change(translation, { target: { value: "openrouter/google/gemini-1.5-flash" } });
    fireEvent.click(screen.getByRole("button", { name: "Create job" }));

    await waitFor(() => expect(onCreated).toHaveBeenCalledWith("job_1"));
    const [url, init] = mockFetch.mock.calls[1];
    expect(url).toEqual(expect.stringContaining("/api/jobs"));
    expect(init.method).toBe("POST");
    expect(new Headers(init.headers).get("Idempotency-Key")).toBeTruthy();
    expect(JSON.parse(init.body)).toEqual({
      source: { type: "url", url: "https://example.com/talk.mp4" },
      target_languages: ["es", "de"],
      lip_sync: false,
      model_overrides: { translation: "openrouter/google/gemini-1.5-flash" },
    });
  });

  it("lip-sync is off by default and is sent as lip_sync: true when the creator enables it", async () => {
    const onCreated = vi.fn();
    mockFetch.mockResolvedValueOnce(jsonResponse(workspace));
    mockFetch.mockResolvedValueOnce(
      jsonResponse({ job_id: "job_2", status: "RECEIVED", created_at: "2026-10-28T00:00:00Z" }, 202),
    );
    render(<NewJobPage onCreated={onCreated} />);

    const toggle = (await screen.findByLabelText("Enable lip-sync")) as HTMLInputElement;
    expect(toggle.checked).toBe(false);
    fireEvent.click(screen.getByLabelText("URL"));
    fireEvent.change(screen.getByLabelText("Video URL"), {
      target: { value: "https://example.com/talk.mp4" },
    });
    fireEvent.click(screen.getByLabelText("es"));
    fireEvent.click(toggle);
    fireEvent.click(screen.getByRole("button", { name: "Create job" }));

    await waitFor(() => expect(onCreated).toHaveBeenCalledWith("job_2"));
    expect(JSON.parse(mockFetch.mock.calls[1][1].body).lip_sync).toBe(true);
  });

  it("explains that lip-sync is unavailable when the backend rejects it with 422 lip_sync_unavailable", async () => {
    const onCreated = vi.fn();
    mockFetch.mockResolvedValueOnce(jsonResponse(workspace));
    mockFetch.mockResolvedValueOnce(
      jsonResponse(
        { detail: { code: "lip_sync_unavailable", message: "Lip-sync is not enabled", details: {} } },
        422,
      ),
    );
    render(<NewJobPage onCreated={onCreated} />);

    fireEvent.click(await screen.findByLabelText("Enable lip-sync"));
    fireEvent.click(screen.getByLabelText("URL"));
    fireEvent.change(screen.getByLabelText("Video URL"), {
      target: { value: "https://example.com/talk.mp4" },
    });
    fireEvent.click(screen.getByLabelText("es"));
    fireEvent.click(screen.getByRole("button", { name: "Create job" }));

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toBe(
      "Lip-sync is not available right now. Turn off lip-sync to submit this job, or try again later.",
    );
    expect(onCreated).not.toHaveBeenCalled();
  });

  it("shows a user-facing message when the backend rejects a model with 422 invalid_model", async () => {
    const onCreated = vi.fn();
    mockFetch.mockResolvedValueOnce(jsonResponse(workspace));
    mockFetch.mockResolvedValueOnce(
      jsonResponse(
        { detail: { code: "invalid_model", message: "Model x is not allowed for planning", details: {} } },
        422,
      ),
    );
    render(<NewJobPage onCreated={onCreated} />);

    await screen.findByLabelText("Planning model");
    fireEvent.click(screen.getByLabelText("URL"));
    fireEvent.change(screen.getByLabelText("Video URL"), {
      target: { value: "https://example.com/talk.mp4" },
    });
    fireEvent.click(screen.getByLabelText("es"));
    fireEvent.click(screen.getByRole("button", { name: "Create job" }));

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toBe(
      "One of the selected models is not in the curated list. Pick another model and try again.",
    );
    expect(onCreated).not.toHaveBeenCalled();
  });

  it("shows the Job Budget as money", async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse({ ...workspace, job_budget_usd: "50.000000" }));
    render(<NewJobPage onCreated={() => {}} />);
    expect(await screen.findByText(/^\$50\.00 — set in Workspace Settings/)).toBeTruthy();
  });

  it.each([
    ["insufficient_job_budget", "Spend plus the projected cost would exceed this Job's budget."],
    ["workspace_budget_exceeded", "The monthly Workspace Budget would be exceeded; raise the cap or wait for the next month."],
    ["brand_new_code", "Something went wrong (error code: brand_new_code)."],
  ])("maps a %s rejection by code and never shows the backend message", async (code, expected) => {
    mockFetch.mockResolvedValueOnce(jsonResponse(workspace));
    mockFetch.mockResolvedValueOnce(jsonResponse({ detail: { code, message: "raw backend text", details: {} } }, 422));
    render(<NewJobPage onCreated={() => {}} />);

    fireEvent.click(await screen.findByLabelText("URL"));
    fireEvent.change(screen.getByLabelText("Video URL"), {
      target: { value: "https://example.com/talk.mp4" },
    });
    fireEvent.click(screen.getByLabelText("es"));
    fireEvent.click(screen.getByRole("button", { name: "Create job" }));

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toBe(expected);
  });

  describe("uploading a file", () => {
    it("offers Upload (default) and URL as sources, never a raw object key", async () => {
      mockFetch.mockResolvedValueOnce(jsonResponse(workspace));
      render(<NewJobPage onCreated={() => {}} uploadSource={stubUpload().fn} />);

      const radios = (await screen.findAllByRole("radio")) as HTMLInputElement[];
      expect(radios.map((r) => r.closest("label")?.textContent?.trim())).toEqual(["Upload", "URL"]);
      expect(radios[0].checked).toBe(true);
      expect(screen.queryByText(/object key/i)).toBeNull();
    });

    it("starts uploading as soon as a file is picked and shows its progress", async () => {
      const upload = stubUpload();
      mockFetch.mockResolvedValueOnce(jsonResponse(workspace));
      render(<NewJobPage onCreated={() => {}} uploadSource={upload.fn} />);

      await screen.findByLabelText("Video file");
      pickFile();
      expect(upload.fn).toHaveBeenCalledWith(video, expect.objectContaining({ signal: expect.any(AbortSignal) }));

      upload.progress(42, 100);
      const bar = screen.getByRole("progressbar", { name: "Upload progress" });
      expect(bar.getAttribute("value")).toBe("42");
      expect(screen.getByText("42%")).toBeTruthy();
    });

    it("announces progress to screen readers in 10% steps from a region that is already mounted", async () => {
      const upload = stubUpload();
      mockFetch.mockResolvedValueOnce(jsonResponse(workspace));
      render(<NewJobPage onCreated={() => {}} uploadSource={upload.fn} />);

      await screen.findByLabelText("Video file");
      const status = screen.getByRole("status");
      expect(status.textContent).toBe("");

      pickFile();
      upload.progress(42, 100);
      expect(status.textContent).toBe("Uploading talk.mp4: 40%");
      upload.progress(49, 100);
      expect(status.textContent).toBe("Uploading talk.mp4: 40%");
      await upload.finish("uploads/upl_1/source.mp4");
      expect(screen.getByRole("status")).toBe(status);
      expect(status.textContent).toBe("talk.mp4 uploaded");
    });

    it("Create job waits for the upload, then submits its key as an object source", async () => {
      const upload = stubUpload();
      const onCreated = vi.fn();
      mockFetch.mockResolvedValueOnce(jsonResponse(workspace));
      mockFetch.mockResolvedValueOnce(
        jsonResponse({ job_id: "job_9", status: "RECEIVED", created_at: "2026-10-28T00:00:00Z" }, 202),
      );
      render(<NewJobPage onCreated={onCreated} uploadSource={upload.fn} />);

      await screen.findByLabelText("Video file");
      pickFile();
      fireEvent.click(screen.getByLabelText("es"));
      upload.progress(25, 100);
      fireEvent.click(screen.getByRole("button", { name: "Create job" }));

      const button = await screen.findByRole("button", { name: "Uploading 25%…" });
      expect((button as HTMLButtonElement).disabled).toBe(true);
      expect(mockFetch).toHaveBeenCalledTimes(1);

      await upload.finish("uploads/upl_1/source.mp4");

      await waitFor(() => expect(onCreated).toHaveBeenCalledWith("job_9"));
      expect(JSON.parse(mockFetch.mock.calls[1][1].body).source).toEqual({
        type: "object",
        key: "uploads/upl_1/source.mp4",
      });
    });

    it("shows Submitting… while the Job is being created after the upload finished", async () => {
      const upload = stubUpload();
      mockFetch.mockResolvedValueOnce(jsonResponse(workspace));
      mockFetch.mockReturnValueOnce(new Promise(() => {}));
      render(<NewJobPage onCreated={() => {}} uploadSource={upload.fn} />);

      await screen.findByLabelText("Video file");
      pickFile();
      fireEvent.click(screen.getByLabelText("es"));
      await upload.finish("uploads/upl_1/source.mp4");
      fireEvent.click(screen.getByRole("button", { name: "Create job" }));

      expect(await screen.findByRole("button", { name: "Submitting…" })).toBeTruthy();
    });

    it("asks for a file when Create job is pressed without one", async () => {
      mockFetch.mockResolvedValueOnce(jsonResponse(workspace));
      render(<NewJobPage onCreated={() => {}} uploadSource={stubUpload().fn} />);

      await screen.findByLabelText("Video file");
      fireEvent.click(screen.getByLabelText("es"));
      fireEvent.submit(screen.getByRole("button", { name: "Create job" }).closest("form")!);

      expect((await screen.findByRole("alert")).textContent).toBe("Choose a video file to upload.");
      expect(mockFetch).toHaveBeenCalledTimes(1);
    });

    it("cancelling aborts the upload and clears the file", async () => {
      const upload = stubUpload();
      mockFetch.mockResolvedValueOnce(jsonResponse(workspace));
      render(<NewJobPage onCreated={() => {}} uploadSource={upload.fn} />);

      await screen.findByLabelText("Video file");
      pickFile();
      fireEvent.click(screen.getByRole("button", { name: "Cancel upload" }));

      expect(upload.signal().aborted).toBe(true);
      await waitFor(() => expect(screen.queryByRole("progressbar")).toBeNull());
      expect(screen.queryByRole("alert")).toBeNull();
    });

    it("picking another file aborts the previous upload", async () => {
      const upload = stubUpload();
      mockFetch.mockResolvedValueOnce(jsonResponse(workspace));
      render(<NewJobPage onCreated={() => {}} uploadSource={upload.fn} />);

      await screen.findByLabelText("Video file");
      pickFile();
      const first = upload.signal();
      pickFile(new File(["x"], "other.mov", { type: "video/quicktime" }));

      expect(first.aborted).toBe(true);
      expect(upload.fn).toHaveBeenCalledTimes(2);
    });

    it("leaving the page aborts the upload", async () => {
      const upload = stubUpload();
      mockFetch.mockResolvedValueOnce(jsonResponse(workspace));
      const { unmount } = render(<NewJobPage onCreated={() => {}} uploadSource={upload.fn} />);

      await screen.findByLabelText("Video file");
      pickFile();
      unmount();

      expect(upload.signal().aborted).toBe(true);
    });

    it("warns before the browser leaves mid-upload, and not once it is done", async () => {
      const upload = stubUpload();
      mockFetch.mockResolvedValueOnce(jsonResponse(workspace));
      render(<NewJobPage onCreated={() => {}} uploadSource={upload.fn} />);

      await screen.findByLabelText("Video file");
      expect(beforeUnloadBlocked()).toBe(false);
      pickFile();
      expect(beforeUnloadBlocked()).toBe(true);
      await upload.finish("uploads/upl_1/source.mp4");
      expect(beforeUnloadBlocked()).toBe(false);
    });

    it("a finished upload can be removed", async () => {
      const upload = stubUpload();
      mockFetch.mockResolvedValueOnce(jsonResponse(workspace));
      render(<NewJobPage onCreated={() => {}} uploadSource={upload.fn} />);

      await screen.findByLabelText("Video file");
      pickFile();
      await upload.finish("uploads/upl_1/source.mp4");
      expect(screen.getByRole("status").textContent).toBe("talk.mp4 uploaded");

      fireEvent.click(screen.getByRole("button", { name: "Remove file" }));
      expect(screen.getByRole("status").textContent).toBe("");
      expect(screen.queryByRole("progressbar")).toBeNull();
    });

    it.each([
      ["source_too_large", "The source file is too large."],
      ["unsupported_media_format", "This media format is not supported. Use MP4 or MOV."],
      ["upload_size_mismatch", "The uploaded file did not arrive intact. Remove it and upload it again."],
      ["upload_failed", "The upload failed. Check your connection, then remove the file and upload it again."],
    ])("maps a %s upload failure to a user-facing message", async (code, expected) => {
      const upload = stubUpload();
      mockFetch.mockResolvedValueOnce(jsonResponse(workspace));
      render(<NewJobPage onCreated={() => {}} uploadSource={upload.fn} />);

      await screen.findByLabelText("Video file");
      pickFile();
      await upload.fail(new ApiError(422, code, "raw backend text"));

      expect((await screen.findByRole("alert")).textContent).toBe(expected);
      expect(beforeUnloadBlocked()).toBe(false);
    });

    it("does not submit when the upload it waited for fails", async () => {
      const upload = stubUpload();
      const onCreated = vi.fn();
      mockFetch.mockResolvedValueOnce(jsonResponse(workspace));
      render(<NewJobPage onCreated={onCreated} uploadSource={upload.fn} />);

      await screen.findByLabelText("Video file");
      pickFile();
      fireEvent.click(screen.getByLabelText("es"));
      fireEvent.click(screen.getByRole("button", { name: "Create job" }));
      await screen.findByRole("button", { name: "Uploading 0%…" });
      await upload.fail(new ApiError(422, "upload_size_mismatch", "raw"));

      expect((await screen.findByRole("alert")).textContent).toBe(
        "The uploaded file did not arrive intact. Remove it and upload it again.",
      );
      expect(screen.getByRole("button", { name: "Create job" })).toBeTruthy();
      expect(mockFetch).toHaveBeenCalledTimes(1);
      expect(onCreated).not.toHaveBeenCalled();
    });
  });

  describe("reading the file's duration", () => {
    // The workspace fixture allows 90 minutes.
    async function renderWithStubs() {
      const upload = stubUpload();
      const duration = stubDuration();
      const onCreated = vi.fn();
      mockFetch.mockResolvedValueOnce(jsonResponse(workspace));
      render(<NewJobPage onCreated={onCreated} uploadSource={upload.fn} readDuration={duration.fn} />);
      await screen.findByLabelText("Video file");
      return { upload, duration, onCreated };
    }

    it("shows a readable file's duration in the UI language, without a warning", async () => {
      const { duration } = await renderWithStubs();
      pickFile();
      expect(duration.fn).toHaveBeenCalledWith(video);

      await duration.read(3903.4);

      expect(screen.getByText("Duration: 1 hr 5 min 3 sec")).toBeTruthy();
      expect(screen.queryByRole("alert")).toBeNull();
    });

    it("announces a non-blocking warning for a file over the allowed length", async () => {
      const { upload, duration, onCreated } = await renderWithStubs();
      mockFetch.mockResolvedValueOnce(
        jsonResponse({ job_id: "job_1", status: "RECEIVED", created_at: "2026-10-28T00:00:00Z" }, 202),
      );
      pickFile();
      await duration.read(91 * 60);

      expect(screen.getByRole("alert").textContent).toBe(
        "This video is 1 hr 31 min long, over the 1 hr 30 min limit, so it will likely be rejected. You can still submit it.",
      );

      fireEvent.click(screen.getByLabelText("es"));
      await upload.finish("uploads/upl_1/source.mp4");
      fireEvent.click(screen.getByRole("button", { name: "Create job" }));
      await waitFor(() => expect(onCreated).toHaveBeenCalledWith("job_1"));
    });

    it("does not warn for a file exactly at the limit", async () => {
      const { duration } = await renderWithStubs();
      pickFile();
      await duration.read(90 * 60);

      expect(screen.getByText("Duration: 1 hr 30 min")).toBeTruthy();
      expect(screen.queryByRole("alert")).toBeNull();
    });

    it("shows no duration and no error for an unreadable file, which can still be submitted", async () => {
      const { upload, duration, onCreated } = await renderWithStubs();
      mockFetch.mockResolvedValueOnce(
        jsonResponse({ job_id: "job_1", status: "RECEIVED", created_at: "2026-10-28T00:00:00Z" }, 202),
      );
      pickFile();
      await duration.read(null);

      expect(screen.queryByText(/^Duration:/)).toBeNull();
      expect(screen.queryByRole("alert")).toBeNull();

      fireEvent.click(screen.getByLabelText("es"));
      await upload.finish("uploads/upl_1/source.mp4");
      fireEvent.click(screen.getByRole("button", { name: "Create job" }));
      await waitFor(() => expect(onCreated).toHaveBeenCalledWith("job_1"));
    });

    it("ignores a late duration from a file that was since replaced", async () => {
      const { duration } = await renderWithStubs();
      pickFile();
      pickFile(new File(["01"], "short.mp4", { type: "video/mp4" }));

      await duration.read(120 * 60, 0);
      expect(screen.queryByText(/^Duration:/)).toBeNull();
      expect(screen.queryByRole("alert")).toBeNull();

      await duration.read(65);
      expect(screen.getByText("Duration: 1 min 5 sec")).toBeTruthy();
    });

    it("clears the duration and warning when the file is removed", async () => {
      const { duration } = await renderWithStubs();
      pickFile();
      await duration.read(91 * 60);

      fireEvent.click(screen.getByRole("button", { name: "Cancel upload" }));

      expect(screen.queryByText(/^Duration:/)).toBeNull();
      expect(screen.queryByRole("alert")).toBeNull();
    });
  });
});
