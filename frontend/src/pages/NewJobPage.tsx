import { useEffect, useState, type FormEvent } from "react";
import { useStore } from "zustand";
import { isApiError } from "@/lib/api";
import { CURATED_MODELS, MODEL_TASKS, type ModelTask } from "@/lib/models";
import { useTranslation } from "@/lib/useTranslation";
import { jobStore, profileStore } from "@/store";
import type { SubmitJobPayload } from "@/store/jobStore";

export interface NewJobPageProps {
  onCreated: (jobId: string) => void;
}

/**
 * Form state for a Job submission. New options (e.g. lip-sync, #29) are added
 * here, given a default in `emptyDraft`, mapped in `toPayload`, and rendered as
 * another <fieldset> below.
 */
interface JobDraft {
  sourceType: "url" | "object";
  sourceValue: string;
  targetLanguages: string[];
  lipSync: boolean;
  models: Partial<Record<ModelTask, string>>;
}

const emptyDraft = (defaults: Record<string, string>): JobDraft => ({
  sourceType: "url",
  sourceValue: "",
  targetLanguages: [],
  lipSync: false,
  models: { ...defaults },
});

/** Only models that differ from the Workspace defaults are sent as overrides. */
function toPayload(draft: JobDraft, defaults: Record<string, string>): SubmitJobPayload {
  const model_overrides: Record<string, string> = {};
  for (const task of MODEL_TASKS) {
    const chosen = draft.models[task];
    if (chosen && chosen !== defaults[task]) model_overrides[task] = chosen;
  }
  const value = draft.sourceValue.trim();
  return {
    source: draft.sourceType === "url" ? { type: "url", url: value } : { type: "object", key: value },
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

export function NewJobPage({ onCreated }: NewJobPageProps) {
  const t = useTranslation();
  const ws = useStore(profileStore, (s) => s.workspace);
  const busy = useStore(jobStore, (s) => s.busy);
  const [draft, setDraft] = useState<JobDraft | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    profileStore.getState().loadWorkspace().catch(() => {});
  }, []);

  useEffect(() => {
    if (ws) setDraft(emptyDraft(ws.default_models));
  }, [ws]);

  if (!ws || !draft) return <p>{t.loading}</p>;

  const update = (patch: Partial<JobDraft>) => setDraft({ ...draft, ...patch });

  const toggleLanguage = (lang: string) =>
    update({
      targetLanguages: draft.targetLanguages.includes(lang)
        ? draft.targetLanguages.filter((l) => l !== lang)
        : [...draft.targetLanguages, lang],
    });

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      const accepted = await jobStore.getState().submitJob(toPayload(draft, ws.default_models));
      onCreated(accepted.job_id);
    } catch (err) {
      if (isApiError(err) && err.code === "invalid_model") setError(t.invalidModel);
      else if (isApiError(err) && err.code === "lip_sync_unavailable") setError(t.lipSyncUnavailable);
      else setError(err instanceof Error && err.message ? err.message : t.jobSubmitFailed);
    }
  };

  return (
    <form className="space-y-6" onSubmit={submit}>
      <h1 className="text-xl font-semibold">{t.newJob}</h1>

      <fieldset className="space-y-2">
        <legend>{t.jobSource}</legend>
        <label>
          <input
            type="radio"
            name="source-type"
            checked={draft.sourceType === "url"}
            onChange={() => update({ sourceType: "url" })}
          />{" "}
          {t.sourceTypeUrl}
        </label>{" "}
        <label>
          <input
            type="radio"
            name="source-type"
            checked={draft.sourceType === "object"}
            onChange={() => update({ sourceType: "object" })}
          />{" "}
          {t.sourceTypeObject}
        </label>
        <div>
          <label htmlFor="job-source">
            {draft.sourceType === "url" ? t.videoUrl : t.siloObjectKey}
          </label>
          <input
            id="job-source"
            required
            value={draft.sourceValue}
            onChange={(e) => update({ sourceValue: e.target.value })}
          />
        </div>
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
          ${ws.job_budget_usd} — {t.jobBudgetFromWorkspace}
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

      <button type="submit" disabled={busy}>
        {t.createJob}
      </button>
    </form>
  );
}
