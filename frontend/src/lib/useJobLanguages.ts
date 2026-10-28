/**
 * Resolve source/target languages (and Clip Hooks) for a list of Job summaries.
 *
 * GET /api/jobs summaries do not carry languages (backend JobSummary has only
 * job_id/status/stage/created_at/expires_at/review_url) and backend changes are
 * out of scope, so each summary's languages come from GET /api/jobs/{id}.
 * One request per job (N+1), fetched once per job id and cached for the
 * lifetime of the component. A failed lookup yields `null` for that job.
 */
import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import type { Job } from "@/lib/types";

export interface JobLanguages {
  source: string | null;
  targets: string[];
  /** Hook of every Clip in the Job, for keyword search (#24). */
  hooks: string[];
}

/** Map of job_id -> languages (undefined = still loading, null = lookup failed). */
export type JobLanguagesMap = Record<string, JobLanguages | null>;

export function useJobLanguages(jobIds: string[]): JobLanguagesMap {
  const [languages, setLanguages] = useState<JobLanguagesMap>({});
  const requested = useRef(new Set<string>()).current;
  const mounted = useRef(true);
  const key = jobIds.join(",");

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  useEffect(() => {
    const missing = jobIds.filter((id) => !requested.has(id));
    for (const id of missing) {
      requested.add(id);
      api
        .get<Job>(`/jobs/${encodeURIComponent(id)}`)
        .then(
          (job): JobLanguages | null => ({
            source: job.source_language?.code ?? null,
            targets: job.target_languages ?? [],
            hooks: (job.segments ?? []).map((clip) => clip.hook_title).filter(Boolean),
          }),
          () => null,
        )
        .then((value) => {
          if (mounted.current) setLanguages((prev) => ({ ...prev, [id]: value }));
        });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  return languages;
}
