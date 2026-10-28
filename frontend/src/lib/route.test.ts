import { describe, it, expect } from "vitest";
import { parseRoute } from "@/lib/route";

describe("parseRoute", () => {
  it("resolves /jobs/{id} to the job detail page", () => {
    expect(parseRoute("/jobs/job_123")).toEqual({ page: "jobDetail", jobId: "job_123" });
  });

  it("does not treat the localization sub-route as part of the job id", () => {
    expect(parseRoute("/jobs/job_123/localization")).toEqual({
      page: "jobLocalization",
      jobId: "job_123",
    });
  });

  it("ignores a trailing slash and query string on the job detail route", () => {
    expect(parseRoute("/jobs/job_123/")).toEqual({ page: "jobDetail", jobId: "job_123" });
    expect(parseRoute("/jobs/job_123?tab=clips")).toEqual({ page: "jobDetail", jobId: "job_123" });
  });

  it("resolves the top-level pages and falls back to the dashboard", () => {
    expect(parseRoute("/jobs")).toEqual({ page: "jobs" });
    expect(parseRoute("/jobs/")).toEqual({ page: "jobs" });
    expect(parseRoute("/profile")).toEqual({ page: "profile" });
    expect(parseRoute("/dashboard")).toEqual({ page: "dashboard" });
    expect(parseRoute("")).toEqual({ page: "dashboard" });
    expect(parseRoute("/nope")).toEqual({ page: "dashboard" });
  });

  it("resolves /jobs/new to the new job page, not a job detail", () => {
    expect(parseRoute("/jobs/new")).toEqual({ page: "newJob" });
    expect(parseRoute("/jobs/new/")).toEqual({ page: "newJob" });
  });

  it("decodes URL-encoded job ids", () => {
    expect(parseRoute("/jobs/job%20a")).toEqual({ page: "jobDetail", jobId: "job a" });
  });
});
