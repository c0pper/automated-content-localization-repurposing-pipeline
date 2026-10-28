/**
 * Retry-safe mutation keys (ADR-0019).
 *
 * The backend stores the response to every POST/DELETE under its
 * Idempotency-Key and replays it on reuse. A user retrying the same intent
 * (same action, same inputs) after a network failure or 5xx must therefore
 * send the same key, so a request that did reach the server is not applied
 * twice. The key is dropped once the server gave a definitive answer
 * (success or a stored 4xx), or when the inputs change.
 */
import { ApiError, newIdempotencyKey } from "./api";

/** True when we cannot know whether the server applied the request. */
function outcomeUnknown(err: unknown): boolean {
  if (!(err instanceof ApiError)) return true; // network failure / abort
  return err.status >= 500 || err.code === "idempotency_in_progress";
}

export type WithIntentKey = <T>(
  intent: string,
  inputs: unknown,
  send: (idempotencyKey: string) => Promise<T>,
) => Promise<T>;

/** A registry of in-flight intents; `intent` names the action and target, e.g. `cancel:job_1`. */
export function createIntentKeys(): WithIntentKey {
  const pending = new Map<string, { fingerprint: string; key: string }>();
  return async (intent, inputs, send) => {
    const fingerprint = JSON.stringify(inputs ?? null);
    let entry = pending.get(intent);
    if (!entry || entry.fingerprint !== fingerprint) {
      entry = { fingerprint, key: newIdempotencyKey() };
      pending.set(intent, entry);
    }
    const current = entry;
    const settle = () => {
      if (pending.get(intent) === current) pending.delete(intent);
    };
    try {
      const result = await send(current.key);
      settle();
      return result;
    } catch (err) {
      if (!outcomeUnknown(err)) settle();
      throw err;
    }
  };
}
