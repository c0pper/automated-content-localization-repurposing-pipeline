import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { Nav } from "./Nav";
import { JobCard } from "./JobCard";
import { localizationStore } from "@/store";
import type { JobSummary } from "@/lib/types";

const job: JobSummary = {
  job_id: "job_1",
  status: "COMPLETED",
  stage: null,
  created_at: "2026-10-27T14:05:00Z",
  expires_at: null,
  review_url: null,
};

function renderShell() {
  return render(
    <>
      <Nav path="/jobs" onNavigate={() => {}} />
      <JobCard job={job} />
    </>,
  );
}

describe("Nav UI language switch", () => {
  beforeEach(() => localizationStore.getState().setUILanguage("en"));
  afterEach(() => {
    cleanup();
    localizationStore.getState().setUILanguage("en");
  });

  it("marks the active UI language", () => {
    renderShell();
    expect(screen.getByRole("button", { name: "English" }).getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByRole("button", { name: "Deutsch" }).getAttribute("aria-pressed")).toBe("false");
  });

  it("re-renders the UI in the selected language", () => {
    renderShell();
    fireEvent.click(screen.getByRole("button", { name: "Deutsch" }));

    expect(screen.getByRole("button", { name: "Aufträge" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Abmelden" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Deutsch" }).getAttribute("aria-pressed")).toBe("true");
  });

  it("formats dates for the selected language", () => {
    renderShell();
    expect(screen.getByText(/Oct 27, 2026/)).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Español" }));
    expect(screen.getByText("27 oct 2026, 14:05")).toBeTruthy();
  });

  it("records the selection in the Localization domain", () => {
    renderShell();
    fireEvent.click(screen.getByRole("button", { name: "Español" }));
    expect(localizationStore.getState().uiLanguage).toBe("es");
  });
});
