/**
 * Curated OpenRouter model lists per task.
 *
 * No API endpoint exposes these, so they MIRROR the backend source of truth:
 * app/config.py `planning_models`, `copy_models`, `translation_models`
 * (see also `Settings.model_allowlists`). Keep the two in sync — the backend
 * rejects anything else with 422 `invalid_model`.
 */
export type ModelTask = "planning" | "copy" | "translation";

export const MODEL_TASKS: readonly ModelTask[] = ["planning", "copy", "translation"];

export const CURATED_MODELS: Readonly<Record<ModelTask, readonly string[]>> = {
  planning: [
    "openrouter/anthropic/claude-3.5-sonnet",
    "openrouter/openai/gpt-4o",
    "openrouter/google/gemini-1.5-pro",
  ],
  copy: [
    "openrouter/anthropic/claude-3.5-sonnet",
    "openrouter/openai/gpt-4o",
    "openrouter/google/gemini-1.5-pro",
  ],
  translation: [
    "openrouter/anthropic/claude-3.5-sonnet",
    "openrouter/openai/gpt-4o-mini",
    "openrouter/google/gemini-1.5-flash",
  ],
};
