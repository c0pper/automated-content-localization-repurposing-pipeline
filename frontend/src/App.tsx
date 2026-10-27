import { useEffect, useState } from "react";
import { AuthGate } from "./components/AuthGate";
import { Nav } from "./components/Nav";
import { DashboardPage } from "./pages/DashboardPage";
import { JobsPage } from "./pages/JobsPage";
import { JobDetailPage } from "./pages/JobDetailPage";
import { ProfilePage } from "./pages/ProfilePage";
import { createAuthStore } from "./store/authStore";
import { createJobStore } from "./store/jobStore";
import { createProfileStore } from "./store/profileStore";

const authStore = createAuthStore();
const jobStore = createJobStore();
const profileStore = createProfileStore();

export default function App() {
  const [ready, setReady] = useState(false);
  const [authed, setAuthed] = useState(false);
  const [path, setPath] = useState("/dashboard");

  useEffect(() => {
    void (async () => {
      try {
        await authStore.getState().refresh();
        setAuthed(authStore.getState().isAuthenticated());
      } catch {
        setAuthed(false);
      }
      setReady(true);
    })();
  }, []);

  useEffect(() => {
    const onHash = () => setPath(window.location.hash.replace(/^#/, "") || "/dashboard");
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  if (!ready) return <div className="min-h-screen bg-background text-text p-8">Loading…</div>;

  if (!authed) {
    return <AuthGate onAuthed={() => setAuthed(true)} />;
  }

  const page = path.startsWith("/jobs/")
    ? <JobDetailPage jobId={path.split("/jobs/")[1] ?? ""} />
    : path.startsWith("/jobs")
      ? <JobsPage />
      : path.startsWith("/profile")
        ? <ProfilePage />
        : path.startsWith("/dashboard")
          ? <DashboardPage />
          : <DashboardPage />;

  return (
    <div className="min-h-screen bg-background text-text">
      <Nav path={path} />
      <main className="mx-auto max-w-5xl px-4 pb-24 pt-6">{page}</main>
    </div>
  );
}