/** Profile / Account settings page (issue #22). */
import { useEffect, useRef, useState } from "react";
import { useStore } from "zustand";
import { useTranslation } from "@/lib/useTranslation";
import { profileStore } from "@/store";
import { ThemeSelector } from "@/components/ThemeSelector";

const PROVIDERS = ["elevenlabs", "other"];

function money(value: string | null | undefined): string {
  return `$${value ?? "0.00"}`;
}

export function ProfilePage() {
  const t = useTranslation();
  const ws = useStore(profileStore, (s) => s.workspace);
  const loading = useStore(profileStore, (s) => s.loading);
  const errorMsg = useStore(profileStore, (s) => s.error);
  const notice = useStore(profileStore, (s) => s.notice);
  const loadWorkspace = profileStore.getState().loadWorkspace;
  const setVoiceProfile = profileStore.getState().setVoiceProfile;
  const deleteVoiceProfile = profileStore.getState().deleteVoiceProfile;
  const rotateApiKeyPlaceholder = profileStore.getState().rotateApiKeyPlaceholder;
  const clearApiKeyPlaceholder = profileStore.getState().clearApiKeyPlaceholder;

  const [voiceForm, setVoiceForm] = useState({
    provider: ws?.voice_profile?.provider ?? PROVIDERS[0],
    voice_id: "",
  });
  const [submitting, setSubmitting] = useState(false);
  const voiceSectionRef = useRef<HTMLElement | null>(null);
  const voiceInputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    void (async () => {
      try {
        await loadWorkspace();
      } catch {
        /* error is exposed through the store */
      }
    })();
  }, [loadWorkspace]);

  const focusVoiceProfile = () => {
    voiceSectionRef.current?.scrollIntoView?.({ behavior: "smooth", block: "center" });
    voiceInputRef.current?.focus();
  };

  const handleSaveVoice = async (e: React.FormEvent) => {
    e.preventDefault();
    const voiceId = voiceForm.voice_id.trim();
    if (!voiceId) return;
    setSubmitting(true);
    try {
      await setVoiceProfile(voiceForm.provider, voiceId);
      setVoiceForm((form) => ({ ...form, voice_id: "" }));
    } catch {
      /* error is exposed through the store */
    } finally {
      setSubmitting(false);
    }
  };

  const handleDeleteVoice = async () => {
    setSubmitting(true);
    try {
      await deleteVoiceProfile();
    } catch {
      /* error is exposed through the store */
    } finally {
      setSubmitting(false);
    }
  };

  if (loading && !ws) return <div className="p-6">{t.loading}</div>;
  if (errorMsg && !ws) {
    return (
      <div className="p-6 text-red-400" role="alert">
        {errorMsg}
      </div>
    );
  }

  const voice = ws?.voice_profile ?? null;
  const providers = voice && !PROVIDERS.includes(voice.provider)
    ? [...PROVIDERS, voice.provider]
    : PROVIDERS;

  return (
    <div className="space-y-8">
      <header>
        <h2 className="text-2xl font-bold text-accent">{t.profile}</h2>
        <p className="text-text-dim">{t.profileSubtitle}</p>
      </header>

      {errorMsg && (
        <p className="text-sm text-red-400 bg-red-900/20 border border-red-900/40 rounded p-3" role="alert">
          {errorMsg}
        </p>
      )}
      {notice && (
        <p className="text-sm text-accent bg-accent/10 border border-accent/30 rounded p-3" role="status">
          {t[notice] ?? notice}
        </p>
      )}

      {/* Workspace settings summary — core of issue #22 */}
      <section
        className="bg-surface rounded-xl border border-border p-6 space-y-4"
        aria-labelledby="workspace-settings-heading"
      >
        <h3 id="workspace-settings-heading" className="font-semibold">
          {t.workspaceSettings}
        </h3>
        <dl className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-sm">
          <div>
            <dt className="text-text-dim">{t.workspaceId}</dt>
            <dd><code className="text-text">{ws?.workspace_id ?? "—"}</code></dd>
          </div>
          <div>
            <dt className="text-text-dim">{t.sourceLanguageAllowlist}</dt>
            <dd>
              {ws?.target_language_allowlist?.length
                ? ws.target_language_allowlist.join(", ")
                : t.allowlistEmpty}
            </dd>
          </div>
          <div>
            <dt className="text-text-dim">{t.jobBudget}</dt>
            <dd><strong className="text-accent">{money(ws?.job_budget_usd)}</strong></dd>
          </div>
          <div>
            <dt className="text-text-dim">{t.monthlyBudget}</dt>
            <dd><strong>{money(ws?.monthly_budget_usd)}</strong></dd>
          </div>
          <div>
            <dt className="text-text-dim">{t.monthlySpend}</dt>
            <dd className="text-text">{money(ws?.current_month_spend_usd)}</dd>
          </div>
          <div>
            <dt className="text-text-dim">{t.workspaceRemaining}</dt>
            <dd><strong className="text-green-400">{money(ws?.remaining_usd)}</strong></dd>
          </div>
          <div>
            <dt className="text-text-dim">{t.maxConcurrentJobs}</dt>
            <dd><strong>{ws?.max_concurrent_jobs ?? "—"}</strong></dd>
          </div>
          <div>
            <dt className="text-text-dim">{t.defaultModels}</dt>
            <dd>
              {ws?.default_models && Object.keys(ws.default_models).length > 0 ? (
                <ul className="space-y-0.5">
                  {Object.entries(ws.default_models).map(([stage, model]) => (
                    <li key={stage}>
                      <span className="text-text-dim">{stage}:</span>{" "}
                      <code className="text-text">{model}</code>
                    </li>
                  ))}
                </ul>
              ) : (
                <span className="text-text-dim">{t.notConfigured}</span>
              )}
            </dd>
          </div>
        </dl>
        <button
          type="button"
          onClick={focusVoiceProfile}
          className="text-accent text-sm hover:underline focus:outline-none focus:ring-2 focus:ring-accent rounded"
        >
          {t.manageVoiceProfile}
        </button>
      </section>

      {/* Voice profile management — issue #22 / #26 */}
      <section
        ref={voiceSectionRef}
        id="voice-profile"
        aria-labelledby="voice-profile-heading"
        className="bg-surface rounded-xl border border-border p-6 space-y-4"
      >
        <div className="flex items-center justify-between">
          <h3 id="voice-profile-heading" className="font-semibold">{t.voiceProfile}</h3>
          {voice ? (
            <span className="text-xs text-green-400">{t.voiceConfigured}</span>
          ) : (
            <span className="text-xs text-red-400">{t.voiceMissing}</span>
          )}
        </div>

        {voice ? (
          <dl className="bg-surface-2 p-4 rounded-lg space-y-2 text-sm">
            <div>
              <dt className="text-text-dim">{t.voiceProvider}</dt>
              <dd><strong>{voice.provider}</strong></dd>
            </div>
            <div>
              <dt className="text-text-dim">{t.voiceId}</dt>
              <dd><code className="text-text">{voice.voice_id}</code></dd>
            </div>
          </dl>
        ) : (
          <p className="text-text-dim text-sm">{t.noVoiceProfile}</p>
        )}

        <form onSubmit={handleSaveVoice} className="space-y-3">
          <div className="flex flex-col sm:flex-row gap-2">
            <label className="sr-only" htmlFor="voice-provider">{t.voiceProvider}</label>
            <select
              id="voice-provider"
              className="rounded border border-border bg-background px-3 py-2 text-sm text-text focus:outline-none focus:ring-2 focus:ring-accent"
              value={voiceForm.provider}
              onChange={(e) => setVoiceForm({ ...voiceForm, provider: e.target.value })}
            >
              {providers.map((provider) => (
                <option key={provider} value={provider}>{provider}</option>
              ))}
            </select>
            <label className="sr-only" htmlFor="voice-id">{t.voiceId}</label>
            <input
              id="voice-id"
              ref={voiceInputRef}
              className="flex-1 rounded border border-border bg-background px-3 py-2 text-sm text-text focus:outline-none focus:ring-2 focus:ring-accent"
              placeholder={t.voiceId}
              value={voiceForm.voice_id}
              onChange={(e) => setVoiceForm({ ...voiceForm, voice_id: e.target.value })}
              required
            />
            <button
              type="submit"
              disabled={submitting}
              className="bg-accent text-accent-contrast px-4 py-2 rounded text-sm font-medium hover:opacity-90 disabled:opacity-50 transition"
            >
              {submitting ? t.saving : t.saveVoiceProfile}
            </button>
          </div>
        </form>

        {voice && (
          <button
            type="button"
            onClick={handleDeleteVoice}
            disabled={submitting}
            className="text-sm text-red-300 border border-red-900/40 bg-red-900/20 px-3 py-2 rounded hover:bg-red-900/30 disabled:opacity-50"
          >
            {t.deleteVoiceProfile}
          </button>
        )}
      </section>

      {/* API key rotation placeholder — issue #22 */}
      <section className="bg-surface rounded-xl border border-border p-6 space-y-4" aria-labelledby="api-key-heading">
        <h3 id="api-key-heading" className="font-semibold">{t.apiKey}</h3>
        <p className="text-text-dim text-sm">{t.apiKeyDescription}</p>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={rotateApiKeyPlaceholder}
            className="bg-surface-2 border border-border px-3 py-2 rounded text-sm hover:bg-surface-2/60"
          >
            {t.apiKeyRotatePlaceholder}
          </button>
          <button
            type="button"
            onClick={clearApiKeyPlaceholder}
            className="bg-red-900/20 border border-red-900/40 text-red-300 px-3 py-2 rounded text-sm hover:bg-red-900/30"
          >
            {t.apiKeyClearPlaceholder}
          </button>
        </div>
      </section>

      {/* Job budget overview — issue #22 requires budget view */}
      <section className="bg-surface rounded-xl border border-border p-6 space-y-4" aria-labelledby="budget-overview-heading">
        <h3 id="budget-overview-heading" className="font-semibold">{t.jobBudgetOverview}</h3>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 text-sm">
          <div className="bg-surface-2 p-4 rounded-lg text-center">
            <div className="text-text-dim">{t.jobBudget}</div>
            <div className="text-xl font-bold text-text">{money(ws?.job_budget_usd)}</div>
          </div>
          <div className="bg-surface-2 p-4 rounded-lg text-center">
            <div className="text-text-dim">{t.monthlySpend}</div>
            <div className="text-xl font-bold text-accent">{money(ws?.current_month_spend_usd)}</div>
          </div>
          <div className="bg-surface-2 p-4 rounded-lg text-center">
            <div className="text-text-dim">{t.workspaceRemaining}</div>
            <div className="text-xl font-bold text-green-400">{money(ws?.remaining_usd)}</div>
          </div>
        </div>
      </section>

      <ThemeSelector />
    </div>
  );
}
