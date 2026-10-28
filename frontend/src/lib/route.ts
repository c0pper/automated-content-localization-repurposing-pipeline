/** Hash-route parsing for the hand-rolled router in App.tsx. */

export type Route =
  | { page: "dashboard" }
  | { page: "jobs" }
  | { page: "profile" }
  | { page: "newJob" }
  | { page: "jobDetail"; jobId: string }
  | { page: "jobLocalization"; jobId: string };

function decode(part: string): string {
  try {
    return decodeURIComponent(part);
  } catch {
    return part;
  }
}

/** Parse a hash path (without the leading `#`) into a Route. */
export function parseRoute(path: string): Route {
  const parts = path.split(/[?#]/)[0].split("/").filter(Boolean);
  const [root, id, sub] = parts;

  if (root === "jobs") {
    if (!id) return { page: "jobs" };
    if (id === "new" && !sub) return { page: "newJob" };
    const jobId = decode(id);
    if (sub === "localization") return { page: "jobLocalization", jobId };
    return { page: "jobDetail", jobId };
  }
  if (root === "profile") return { page: "profile" };
  return { page: "dashboard" };
}
