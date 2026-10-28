/**
 * Selection Gate page (issue #28) at `/jobs/{id}/localization`.
 *
 * The Creator picks a rectangle — a set of Clips × a set of Target Languages —
 * or the empty selection, sees the exact total live (integer micro-USD), and
 * confirms it. A 409 `selection_price_changed` reloads the matrix, shows the new
 * total and requires a fresh confirmation.
 */
import { useEffect, useId, useMemo, useState } from "react";
import { useStore } from "zustand";
import { jobStore } from "@/store";
import { isApiError, isSelectionPriceChanged } from "@/lib/api";
import { formatUsd, sumUsd } from "@/lib/money";
import { interpolate, useTranslation } from "@/lib/useTranslation";
import type { Dict } from "@/lib/i18n";
import type { CostCell, GatePayload, Job } from "@/lib/types";

type GateSegment = GatePayload["segments"][number];

const ERROR_KEYS: Record<string, string> = {
  invalid_state: "gateErrorInvalidState",
  selection_expired: "gateErrorExpired",
  selection_already_confirmed: "gateErrorAlreadyConfirmed",
  invalid_selection: "gateErrorInvalidSelection",
  invalid_amount: "gateErrorInvalidAmount",
  not_found: "jobNotFound",
};

function errorText(t: Dict, err: unknown): string {
  const key = isApiError(err) ? ERROR_KEYS[err.code] : undefined;
  return t[key ?? "gateErrorGeneric"];
}

/** A rectangle selection: every selected Clip × every selected Language. */
export interface GateSelection {
  clips: ReadonlySet<number>;
  languages: ReadonlySet<string>;
}

/** Valid when both sides are non-empty (a rectangle) or both are empty (skip localization). */
export function isValidSelection(sel: GateSelection): boolean {
  return (sel.clips.size === 0) === (sel.languages.size === 0);
}

/** Exact total of the selected cells as a wire USD string. */
export function selectionTotal(matrix: CostCell[], sel: GateSelection): string {
  return sumUsd(
    matrix
      .filter((c) => sel.clips.has(c.segment_id) && sel.languages.has(c.language))
      .map((c) => c.total_usd),
  );
}

function toggle<T>(set: ReadonlySet<T>, value: T): Set<T> {
  const next = new Set(set);
  if (next.has(value)) next.delete(value);
  else next.add(value);
  return next;
}

export function SelectionGatePage({ jobId }: { jobId: string }) {
  const t = useTranslation();
  const storedGate = useStore(jobStore, (s) => s.gate);
  const busy = useStore(jobStore, (s) => s.busy);
  const gate = storedGate?.job_id === jobId ? storedGate : null;

  const [loadError, setLoadError] = useState<string | null>(null);
  const [clips, setClips] = useState<ReadonlySet<number>>(new Set());
  const [languages, setLanguages] = useState<ReadonlySet<string>>(new Set());
  const [priceChangedTotal, setPriceChangedTotal] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [confirmed, setConfirmed] = useState<Job | null>(null);

  useEffect(() => {
    let active = true;
    setLoadError(null);
    jobStore
      .getState()
      .getGate(jobId)
      .catch((err) => {
        if (active) setLoadError(errorText(t, err));
      });
    return () => {
      active = false;
    };
  }, [jobId, t]);

  const selection: GateSelection = { clips, languages };
  const valid = isValidSelection(selection);
  const total = useMemo(
    () => (gate ? selectionTotal(gate.cost_matrix, { clips, languages }) : "0.00"),
    [gate, clips, languages],
  );

  const backLink = (
    <a href={`#/jobs/${encodeURIComponent(jobId)}`} className="text-accent text-sm hover:underline">
      {t.backToJob}
    </a>
  );

  if (confirmed) {
    return (
      <div className="space-y-4">
        <h2 className="text-2xl font-bold text-accent">{t.gateTitle}</h2>
        <p role="status" className="bg-surface rounded-xl border border-border p-4">
          {interpolate(t.selectionConfirmed, {
            status: confirmed.status,
            stage: confirmed.stage ?? "—",
          })}
        </p>
        {backLink}
      </div>
    );
  }

  if (!gate) {
    return (
      <div className="space-y-4 p-6">
        {loadError ? <p role="alert" className="text-red-400">{loadError}</p> : <p role="status">{t.loading}</p>}
        {backLink}
      </div>
    );
  }

  const onConfirm = async () => {
    if (!valid || busy) return;
    setSubmitError(null);
    const segmentIds = gate.segments.map((s) => s.segment_id).filter((id) => clips.has(id));
    const langs = gate.target_languages.filter((l) => languages.has(l));
    try {
      const job = await jobStore.getState().confirmSelection(jobId, segmentIds, langs, total);
      setPriceChangedTotal(null);
      setConfirmed(job);
    } catch (err) {
      const changed = isSelectionPriceChanged(err);
      if (changed) {
        setPriceChangedTotal(changed.currentTotalUsd);
        await reloadAfterPriceChange(jobId, changed.costMatrix);
      } else {
        setSubmitError(errorText(t, err));
      }
    }
  };

  const changeClips = (next: ReadonlySet<number>) => {
    setClips(next);
    setPriceChangedTotal(null);
  };
  const changeLanguages = (next: ReadonlySet<string>) => {
    setLanguages(next);
    setPriceChangedTotal(null);
  };

  const cellCount = clips.size * languages.size;

  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <h2 className="text-2xl font-bold text-accent">{t.gateTitle}</h2>
        <p className="text-text-dim text-sm">{t.gateIntro}</p>
        {gate.expires_at && (
          <p className="text-text-dim text-xs">
            {t.gateExpires}: <time dateTime={gate.expires_at}>{gate.expires_at}</time>
          </p>
        )}
        {backLink}
      </header>

      <div className="grid gap-4 sm:grid-cols-2">
        <ChoiceGroup
          legend={t.clipsToLocalize}
          t={t}
          options={gate.segments.map((s) => ({ value: s.segment_id, label: clipLabel(t, s) }))}
          selected={clips}
          onChange={changeClips}
        />
        <ChoiceGroup
          legend={t.languagesToLocalize}
          t={t}
          options={gate.target_languages.map((l) => ({ value: l, label: l }))}
          selected={languages}
          onChange={changeLanguages}
        />
      </div>

      <CostMatrix gate={gate} selection={selection} t={t} />

      <section aria-labelledby="gate-total" className="bg-surface rounded-xl border border-border p-4 space-y-2">
        <h3 id="gate-total" className="font-semibold text-sm">{t.selectedTotal}</h3>
        <output aria-labelledby="gate-total" aria-live="polite" className="block text-lg font-semibold text-accent">
          {formatUsd(total)}
        </output>
        <p className="text-text-dim text-sm" aria-live="polite">
          {!valid
            ? t.selectionIncomplete
            : cellCount === 0
              ? t.emptySelectionHint
              : interpolate(t.selectionSummary, { clips: clips.size, langs: languages.size, cells: cellCount })}
        </p>
        {priceChangedTotal != null && (
          <p role="alert" className="text-orange-400 text-sm">
            {interpolate(t.priceChanged, { total: formatUsd(priceChangedTotal) })}
          </p>
        )}
        {submitError && (
          <p role="alert" className="text-red-400 text-sm">{submitError}</p>
        )}
        <button
          type="button"
          onClick={() => void onConfirm()}
          disabled={!valid || busy}
          aria-busy={busy}
          className="rounded-lg bg-accent text-accent-contrast px-4 py-2 font-semibold disabled:opacity-50"
        >
          {busy
            ? t.confirming
            : cellCount === 0
              ? t.confirmNoLocalization
              : interpolate(t.confirmSelection, { total: formatUsd(total) })}
        </button>
      </section>
    </div>
  );
}

/**
 * After a 409 the server's prices win: reload the full gate (with the
 * translation/voice/lip-sync breakdown). If that fails, patch the cell totals
 * from the error details so the live total still reflects the new prices.
 */
async function reloadAfterPriceChange(
  jobId: string,
  costMatrix: { segment_id: number; language: string; total_usd: string }[],
): Promise<void> {
  try {
    await jobStore.getState().getGate(jobId);
  } catch {
    const gate = jobStore.getState().gate;
    if (!gate) return;
    const totals = new Map(costMatrix.map((c) => [`${c.segment_id}:${c.language}`, c.total_usd]));
    jobStore.setState({
      gate: {
        ...gate,
        cost_matrix: gate.cost_matrix.map((c) => ({
          ...c,
          total_usd: totals.get(`${c.segment_id}:${c.language}`) ?? c.total_usd,
        })),
      },
    });
  }
}

function clipLabel(t: Dict, s: GateSegment): string {
  return `${t.clip} ${s.segment_id}: ${s.hook_title}`;
}

function ChoiceGroup<T extends string | number>({
  legend,
  options,
  selected,
  onChange,
  t,
}: {
  legend: string;
  options: { value: T; label: string }[];
  selected: ReadonlySet<T>;
  onChange: (next: ReadonlySet<T>) => void;
  t: Dict;
}) {
  const id = useId();
  return (
    <fieldset className="bg-surface rounded-xl border border-border p-4 space-y-2">
      <legend className="font-semibold text-sm px-1">{legend}</legend>
      <div className="flex gap-2 text-xs">
        <button
          type="button"
          className="rounded border border-border px-2 py-1"
          aria-label={`${t.selectAll}: ${legend}`}
          onClick={() => onChange(new Set(options.map((o) => o.value)))}
        >
          {t.selectAll}
        </button>
        <button
          type="button"
          className="rounded border border-border px-2 py-1"
          aria-label={`${t.selectNone}: ${legend}`}
          onClick={() => onChange(new Set())}
        >
          {t.selectNone}
        </button>
      </div>
      <ul className="space-y-1">
        {options.map((o) => {
          const inputId = `${id}-${o.value}`;
          return (
            <li key={String(o.value)} className="flex items-center gap-2 min-h-[2.75rem]">
              <input
                id={inputId}
                type="checkbox"
                className="h-5 w-5 accent-[var(--accent)]"
                checked={selected.has(o.value)}
                onChange={() => onChange(toggle(selected, o.value))}
              />
              <label htmlFor={inputId} className="text-sm">{o.label}</label>
            </li>
          );
        })}
      </ul>
    </fieldset>
  );
}

/** One row per Clip × Language cell; the lip-sync column appears only when the Job has lip-sync. */
function CostMatrix({ gate, selection, t }: { gate: GatePayload; selection: GateSelection; t: Dict }) {
  const hooks = new Map(gate.segments.map((s) => [s.segment_id, s]));
  const order = new Map(gate.segments.map((s, i) => [s.segment_id, i]));
  const langOrder = new Map(gate.target_languages.map((l, i) => [l, i]));
  const rows = [...gate.cost_matrix].sort(
    (a, b) =>
      (order.get(a.segment_id) ?? 0) - (order.get(b.segment_id) ?? 0) ||
      (langOrder.get(a.language) ?? 0) - (langOrder.get(b.language) ?? 0),
  );
  const th = "text-left font-medium px-2 py-1";
  const td = "px-2 py-1";

  return (
    <section className="bg-surface rounded-xl border border-border p-4 space-y-2">
      <div className="overflow-x-auto">
        <table className="w-full text-sm" aria-label={t.costMatrix}>
          <thead>
            <tr className="text-text-dim border-b border-border">
              <th scope="col" className={th}>{t.clip}</th>
              <th scope="col" className={th}>{t.language}</th>
              <th scope="col" className={th}>{t.translation}</th>
              <th scope="col" className={th}>{t.voice}</th>
              {gate.lip_sync && <th scope="col" className={th}>{t.lipSync}</th>}
              <th scope="col" className={th}>{t.total}</th>
              <th scope="col" className={th}>{t.selection}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((c) => {
              const seg = hooks.get(c.segment_id);
              const label = seg ? clipLabel(t, seg) : `${t.clip} ${c.segment_id}`;
              const isSelected = selection.clips.has(c.segment_id) && selection.languages.has(c.language);
              return (
                <tr
                  key={`${c.segment_id}:${c.language}`}
                  aria-label={`${label} × ${c.language}`}
                  className={`border-b border-border ${isSelected ? "bg-accent-soft" : ""}`}
                >
                  <th scope="row" className={th}>{label}</th>
                  <td className={td} lang={c.language}>{c.language}</td>
                  <td className={td}>{formatUsd(c.translation_usd)}</td>
                  <td className={td}>{formatUsd(c.voice_usd)}</td>
                  {gate.lip_sync && <td className={td}>{formatUsd(c.lip_sync_usd)}</td>}
                  <td className={`${td} font-medium`}>{formatUsd(c.total_usd)}</td>
                  <td className={td}>{isSelected ? t.selected : t.notSelected}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="text-text-dim text-xs">
        {interpolate(t.projectedAllCells, { total: formatUsd(gate.projected_total_usd) })}
      </p>
    </section>
  );
}
