/** Profile / Account settings page (issue #22). */
import { useEffect, useState } from "react";
import { useTranslation } from "@/lib/useTranslation";
import { profileStore } from "@/store/profileStore";

export function ProfilePage() {
  const t = useTranslation();
  const ws = profileStore((s) => s.workspace);
  const loading = profileStore((s) => s.loading);
  const errorMsg = profileStore((s) => s.error);
  const loadWorkspace = profileStore.getState().loadWorkspace;
  const setVoiceProfile = profileStore.getState().setVoiceProfile;
  const [voiceForm, setVoiceForm] = useState({ provider: "elevenlabs", voice_id: "" });
  const [showRotatePlaceholder, setShowRotatePlaceholder] = useState(false);

  useEffect(() => {
    void (async () => {
      try { await loadWorkspace(); } catch { /* handled by store */ }
    })();
  }, [loadWorkspace]);

  if (loading && !ws) return <div className="p-6">{t.loading}</div>;
  if (errorMsg && !ws) return <div className="p-6 text-red-400">{errorMsg}</div>;

  return (
    <div className="space-y-8">
      <header>
        <h2 className="text-2xl font-bold text-accent">Profile</h2>
        <p className="text-text-dim">Workspace settings summary and account management</p>
      </header>

      {/* Workspace settings summary — core of issue #22 */}
      <section className="bg-surface rounded-xl border border-border p-6 space-y-4">
        <h3 className="font-semibold">Workspace Settings</h3>
        <div className="grid grid-cols-2 gap-4 text-sm">
          <div><span className="text-text-dim">Workspace ID</span> <code className="text-text">{ws?.workspace_id ?? "—"}</code></div>
          <div><span className="text-text-dim">Source allowlist</span> {ws?.target_language_allowlist?.join(", ") ?? "—"}</div>
          <div><span className="text-text-dim">Job budget</span> <strong className="text-accent">{ws?.job_budget_usd ?? "—"}</strong></div>
          <div><span className="text-text-dim">Monthly budget</span> <strong>{ws?.monthly_budget_usd ?? "—"}</strong></div>
          <div><span className="text-text-dim">Spent this month</span> <span className="text-text">{ws?.current_month_spend_usd ?? "0.00"}</span></div>
          <div><span className="text-text-dim">Workspace remaining</span> <strong className="text-green-400">{ws?.remaining_usd ?? "—"}</strong></div>
          <div><span className="text-text-dim">Max concurrent jobs</span> <strong>{ws?.max_concurrent_jobs ?? "—"}</strong></div>
          <div><span className="text-text-dim">Default models</span> <code className="text-text">{JSON.stringify(ws?.default_models ?? "—")}</code></div>
        </div>
      </section>

      {/* Voice profile management — issue #22 / #26 */}
      <section className="bg-surface rounded-xl border border-border p-6 space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="font-semibold">Voice Profile</h3>
          {ws?.voice_profile ? (
            <span className="text-xs text-green-400">Configured</span>
          ) : (
            <span className="text-xs text-red-400">Missing — localization will fail</span>
          )}
        </div>
        {ws?.voice_profile ? (
          <div className="bg-surface-2 p-4 rounded-lg space-y-2 text-sm">
            <div><span className="text-text-dim">Provider:</span> <strong>{ws.voice_profile.provider}</strong></div>
            <div><span className="text-text-dim">Voice ID:</span> <code className="text-text">{ws.voice_profile.voice_id}</code></div>
          </div>
        ) : (
          <p className="text-text-dim text-sm">No voice profile configured. Set a provider and voice ID below.</p>
        )}
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            if (!voiceForm.voice_id.trim()) return;
            try {
              await setVoiceProfile(voiceForm.provider, voiceForm.voice_id.trim());
              await loadWorkspace();
              setVoiceForm({ ...voiceForm, voice_id: "" });
            } catch {
              // Error shown via store
            }
          }}
          className="flex gap-2"
        >
          <input
            className="flex-1 rounded border border-border bg-background px-3 py-2 text-sm text-text focus:outline-none focus:ring-2 focus:ring-accent"
            placeholder="voice_id (required)"
            value={voiceForm.voice_id}
            onChange={(e) => setVoiceForm({ ...voiceForm, voice_id: e.target.value })}
            required
          />
          <button
            type="submit"
            className="bg-accent text-accent-contrast px-4 py-2 rounded text-sm font-medium hover:opacity-90 transition"
          >
            Save Profile
          </button>
        </form>
      </section>

      {/* API key rotation placeholder — issue #22 */}
      <section className="bg-surface rounded-xl border border-border p-6 space-y-4">
        <h3 className="font-semibold">API Key</h3>
        <p className="text-text-dim text-sm">Key rotation and revocation are placeholders in v1 — manage externally and use this workspace token.</p>
        <div className="flex gap-2">
          <button
            onClick={() => {
              setShowRotatePlaceholder(true);
              setTimeout(() => setShowRotatePlaceholder(false), 3000);
            }}
            className="bg-surface-2 border border-border px-3 py-2 rounded text-sm hover:bg-surface-2/60"
          >
            Rotate API Key (placeholder)
          </button>
          <button
            onClick={() => setShowRotatePlaceholder(true)}
            className="bg-red-900/20 border border-red-900/40 text-red-300 px-3 py-2 rounded text-sm hover:bg-red-900/30"
          >
            Clear Key (placeholder)
          </button>
        </div>
        {showRotatePlaceholder && (
          <p className="text-sm text-accent">Placeholder rotation triggered — regenerate the workspace token externally.</p>
        )}
      </section>

      {/* Job budget overview — issue #22 requires budget view */}
      <section className="bg-surface rounded-xl border border-border p-6 space-y-4">
        <h3 className="font-semibold">Job Budget Overview</h3>
        <div className="grid grid-cols-3 gap-4 text-sm">
          <div className="bg-surface-2 p-4 rounded-lg text-center">
            <div className="text-text-dim">Job Budget</div>
            <div className="text-xl font-bold text-text">{ws?.job_budget_usd ?? "—"}</div>
          </div>
          <div className="bg-surface-2 p-4 rounded-lg text-center">
            <div className="text-text-dim">Spent This Month</div>
            <div className="text-xl font-bold text-accent">{ws?.current_month_spend_usd ?? "0.00"}</div>
          </div>
          <div className="bg-surface-2 p-4 rounded-lg text-center">
            <div className="text-text-dim">Remaining</div>
            <div className="text-xl font-bold text-green-400">{ws?.remaining_usd ?? "—"}</div>
          </div>
        </div>
      </section>
    </div>
  );
}