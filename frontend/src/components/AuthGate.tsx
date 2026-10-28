import { useState, FormEvent } from "react";
import { authStore } from "@/store";

export interface AuthGateProps {
  onAuthed: () => void;
}

export function AuthGate({ onAuthed }: AuthGateProps) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      await authStore.getState().login();
      onAuthed();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Login failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center p-4 bg-background">
      <form onSubmit={handleSubmit} className="w-full max-w-md space-y-4 bg-surface p-8 rounded-xl border border-border">
        <h1 className="text-2xl font-bold text-accent">Creator Portal</h1>
        <p className="text-text-dim">Sign in to access your workspace</p>
        {error && (
          <div className="text-sm text-red-400 bg-red-900/20 border border-red-900/50 p-3 rounded">
            {error}
          </div>
        )}
        <button
          type="submit"
          disabled={loading}
          className="w-full py-3 bg-accent text-accent-contrast font-medium rounded-lg hover:opacity-90 disabled:opacity-50 transition"
        >
          {loading ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </div>
  );
}