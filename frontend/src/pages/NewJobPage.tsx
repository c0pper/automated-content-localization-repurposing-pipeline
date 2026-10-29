import { useEffect, useRef, useState, type FormEvent } from "react";
import { useStore } from "zustand";
import { errorText } from "@/lib/errors";
import { formatDuration } from "@/lib/format";
import type { Dict } from "@/lib/i18n";
import { formatUsd } from "@/lib/money";
import { CURATED_MODELS, MODEL_TASKS, type ModelTask } from "@/lib/models";
import { uploadSource as defaultUploadSource, type UploadSource } from "@/lib/sourceUpload";
import { interpolate, useTranslation } from "@/lib/useTranslation";
import { readVideoDuration as defaultReadDuration, type ReadDuration } from "@/lib/videoDuration";
import { jobStore, profileStore } from "@/store";
import type { SubmitJobPayload } from "@/store/jobStore";

export interface NewJobPageProps {
  onCreated: (jobId: string) => void;
  /** Injected so tests can stub the Source Upload. */
  uploadSource?: UploadSource;
  /** Injected so tests can stub reading the file's duration. */
  readDuration?: ReadDuration;
}

/**
 * Form state for a Job submission. New options (e.g. lip-sync, #29) are added
 * here, given a default in `emptyDraft`, mapped in `toPayload`, and rendered as
 * another <fieldset> below. An uploaded file lives in `SourceUploadState`.
 */
interface JobDraft {
  sourceType: "upload" | "url";
  url: string;
  targetLanguages: string[];
  lipSync: boolean;
  models: Partial<Record<ModelTask, string>>;
}

/**
 * The picked file's Source Upload; `key` is set once it completed.
 * `durationSeconds` is read locally: undefined while reading, null if unreadable.
 */
interface SourceUploadState {
  file: File;
  percent: number;
  status: "uploading" | "done" | "failed";
  key?: string;
  durationSeconds?: number | null;
}

const emptyDraft = (defaults: Record<string, string>): JobDraft => ({
  sourceType: "upload",
  url: "",
  targetLanguages: [],
  lipSync: false,
  models: { ...defaults },
});

/** Only models that differ from the Workspace defaults are sent as overrides. */
function toPayload(
  draft: JobDraft,
  source: SubmitJobPayload["source"],
  defaults: Record<string, string>,
): SubmitJobPayload {
  const model_overrides: Record<string, string> = {};
  for (const task of MODEL_TASKS) {
    const chosen = draft.models[task];
    if (chosen && chosen !== defaults[task]) model_overrides[task] = chosen;
  }
  return {
    source,
    target_languages: draft.targetLanguages,
    lip_sync: draft.lipSync,
    model_overrides,
  };
}

const MODEL_LABEL_KEYS: Record<ModelTask, string> = {
  planning: "planningModel",
  copy: "copyModel",
  translation: "translationModel",
};

/** Curated list for a task, keeping the Workspace default selectable even if config drifted. */
function modelOptions(task: ModelTask, current: string | undefined): string[] {
  const list = [...CURATED_MODELS[task]];
  if (current && !list.includes(current)) list.unshift(current);
  return list;
}

/** Screen-reader progress, in 10% steps so the live region isn't read out on every percent. */
function uploadAnnouncement(t: Dict, upload: SourceUploadState | null): string {
  if (!upload || upload.status === "failed") return "";
  const name = upload.file.name;
  if (upload.status === "done") return interpolate(t.fileUploaded, { name });
  return interpolate(t.uploadingFile, { name, percent: Math.floor(upload.percent / 10) * 10 });
}

const ACCEPTED_VIDEO ="video/mp4,video/quicktime,video/x-m4v,.mp4,.mov,.m4v";

export function NewJobPage({
  onCreated,
  uploadSource = defaultUploadSource,
  readDuration = defaultReadDuration,
}: NewJobPageProps) {
  const t = useTranslation();
  const ws = useStore(profileStore, (s) => s.workspace);
  const busy = useStore(jobStore, (s) => s.busy);
  const [draft, setDraft] = useState<JobDraft | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [upload, setUpload] = useState<SourceUploadState | null>(null);
  // Bumped to clear the file input after a removal.
  const [fileInputKey, setFileInputKey] = useState(0);
  const [phase, setPhase] = useState<"uploading" | "submitting" | null>(null);
  const uploadRef = useRef<{ controller: AbortController; done: Promise<{ key: string }> } | null>(null);

  useEffect(() => {
    profileStore.getState().loadWorkspace().catch(() => {});
  }, []);

  useEffect(() => {
    if (ws) setDraft(emptyDraft(ws.default_models));
  }, [ws]);

  // Leaving the page abandons the upload; an interrupted upload is never resumed (ADR 0022).
  useEffect(() => () => uploadRef.current?.controller.abort(), []);

  const uploading = upload?.status === "uploading";
  useEffect(() => {
    if (!uploading) return;
    const warn = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [uploading]);

  if (!ws || !draft) return <p>{t.loading}</p>;

  const update = (patch: Partial<JobDraft>) => setDraft({ ...draft, ...patch });

  const toggleLanguage = (lang: string) =>
    update({
      targetLanguages: draft.targetLanguages.includes(lang)
        ? draft.targetLanguages.filter((l) => l !== lang)
        : [...draft.targetLanguages, lang],
    });

  const discardUpload = () => {
    uploadRef.current?.controller.abort();
    uploadRef.current = null;
    setUpload(null);
    setError(null);
  };

  const removeFile = () => {
    discardUpload();
    setFileInputKey((k) => k + 1);
  };

  const startUpload = (file: File) => {
    discardUpload();
    const controller = new AbortController();
    const isCurrent = () => uploadRef.current?.controller === controller;
    const patch = (p: Partial<SourceUploadState>) => {
      if (isCurrent()) setUpload((u) => (u ? { ...u, ...p } : u));
    };
    const done = uploadSource(file, {
      signal: controller.signal,
      onProgress: ({ loadedBytes, totalBytes }) => {
        const percent = totalBytes > 0 ? Math.floor((loadedBytes * 100) / totalBytes) : 0;
        if (isCurrent()) setUpload((u) => (u && u.percent !== percent ? { ...u, percent } : u));
      },
    });
    uploadRef.current = { controller, done };
    setUpload({ file, percent: 0, status: "uploading" });
    // Only a hint: the upload proceeds whatever the browser reads (US33).
    readDuration(file).then(
      (durationSeconds) => patch({ durationSeconds }),
      () => patch({ durationSeconds: null }),
    );
    done.then(
      ({ key }) => patch({ status: "done", percent: 100, key }),
      (err) => {
        if (!isCurrent()) return; // cancelled or replaced
        patch({ status: "failed" });
        setError(errorText(t, err));
      },
    );
  };

  const resolveSourceInput = async (): Promise<SubmitJobPayload["source"] | null> => {
    if (draft.sourceType === "url") return { type: "url", url: draft.url.trim() };
    const current = uploadRef.current;
    if (!upload || !current) {
      setError(t.chooseVideoFile);
      return null;
    }
    setPhase("uploading");
    try {
      const { key } = await current.done;
      return { type: "object", key };
    } catch {
      return null; // the upload's own handler reports why
    }
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (upload?.status !== "failed") setError(null);
    try {
      const source = await resolveSourceInput();
      if (!source) return;
      setPhase("submitting");
      const accepted = await jobStore.getState().submitJob(toPayload(draft, source, ws.default_models));
      onCreated(accepted.job_id);
    } catch (err) {
      setError(errorText(t, err));
    } finally {
      setPhase(null);
    }
  };

  const duration = upload?.durationSeconds;
  const tooLong = typeof duration === "number" && duration > ws.max_video_minutes * 60;

  const submitLabel =
    phase === "uploading"
      ? interpolate(t.uploadingPercent, { percent: upload?.percent ?? 0 })
      : phase === "submitting" || busy
        ? t.submitting
        : t.createJob;

  return (
    <form className="space-y-6" onSubmit={submit}>
      <h1 className="text-xl font-semibold">{t.newJob}</h1>

      <fieldset className="space-y-2">
        <legend>{t.jobSource}</legend>
        <label>
          <input
            type="radio"
            name="source-type"
            checked={draft.sourceType === "upload"}
            onChange={() => update({ sourceType: "upload" })}
          />{" "}
          {t.sourceTypeUpload}
        </label>{" "}
        <label>
          <input
            type="radio"
            name="source-type"
            checked={draft.sourceType === "url"}
            onChange={() => update({ sourceType: "url" })}
          />{" "}
          {t.sourceTypeUrl}
        </label>
        {draft.sourceType === "url" ? (
          <div>
            <label htmlFor="job-source">{t.videoUrl}</label>
            <input
              id="job-source"
              required
              value={draft.url}
              onChange={(e) => update({ url: e.target.value })}
            />
          </div>
        ) : (
          <div className="space-y-2">
            <label htmlFor="job-source-file">{t.videoFile}</label>
            <input
              key={fileInputKey}
              id="job-source-file"
              type="file"
              accept={ACCEPTED_VIDEO}
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) startUpload(file);
              }}
            />
            {upload && (
              <div className="space-y-1">
                {upload.status !== "failed" && (
                  <div>
                    <progress aria-label={t.uploadProgress} max={100} value={upload.percent} />{" "}
                    <span aria-hidden="true">{upload.percent}%</span>
                  </div>
                )}
                {typeof duration === "number" && (
                  <p>
                    {t.fileDuration}: {formatDuration(duration, t.locale)}
                  </p>
                )}
                {tooLong && (
                  <p role="alert">
                    {interpolate(t.videoTooLong, {
                      duration: formatDuration(duration, t.locale),
                      limit: formatDuration(ws.max_video_minutes * 60, t.locale),
                    })}
                  </p>
                )}
                <button type="button" onClick={removeFile}>
                  {upload.status === "uploading" ? t.cancelUpload : t.removeFile}
                </button>
              </div>
            )}
            {/* Mounted before the upload starts so screen readers pick up the first update. */}
            <p role="status" className="sr-only">
              {uploadAnnouncement(t, upload)}
            </p>
          </div>
        )}
      </fieldset>

      <fieldset className="space-y-2">
        <legend>{t.targetLanguages}</legend>
        {ws.target_language_allowlist.map((lang) => (
          <label key={lang} className="mr-3">
            <input
              type="checkbox"
              checked={draft.targetLanguages.includes(lang)}
              onChange={() => toggleLanguage(lang)}
            />{" "}
            {lang}
          </label>
        ))}
      </fieldset>

      <fieldset className="space-y-2">
        <legend>{t.lipSync}</legend>
        <label>
          <input
            type="checkbox"
            checked={draft.lipSync}
            aria-describedby="lip-sync-hint"
            onChange={(e) => update({ lipSync: e.target.checked })}
          />{" "}
          {t.enableLipSync}
        </label>
        <p id="lip-sync-hint" className="text-text-dim text-xs">
          {t.lipSyncHint}
        </p>
      </fieldset>

      <fieldset className="space-y-2">
        <legend>{t.jobBudget}</legend>
        <p>
          {formatUsd(ws.job_budget_usd)} — {t.jobBudgetFromWorkspace}
        </p>
      </fieldset>

      <fieldset className="space-y-2">
        <legend>{t.modelOverrides}</legend>
        {MODEL_TASKS.map((task) => {
          const id = `model-${task}`;
          return (
            <div key={task}>
              <label htmlFor={id}>{t[MODEL_LABEL_KEYS[task]]}</label>
              <select
                id={id}
                value={draft.models[task] ?? ""}
                onChange={(e) => update({ models: { ...draft.models, [task]: e.target.value } })}
              >
                {modelOptions(task, ws.default_models[task]).map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
              </select>
            </div>
          );
        })}
      </fieldset>

      {error && <p role="alert">{error}</p>}

      <button type="submit" disabled={busy || phase !== null}>
        {submitLabel}
      </button>
    </form>
  );
}
