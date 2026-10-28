import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import App from "@/App";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("App review route", () => {
  const mockFetch = vi.fn();

  beforeEach(() => {
    globalThis.fetch = mockFetch;
    mockFetch.mockReset();
    mockFetch.mockImplementation(async (url: string) =>
      String(url).includes("/review/")
        ? jsonResponse({ detail: { code: "not_found", message: "Not found", details: {} } }, 404)
        : jsonResponse({ detail: { code: "unauthorized", message: "no", details: {} } }, 401),
    );
  });

  afterEach(() => {
    cleanup();
    window.location.hash = "";
  });

  it("opens #/review/{token} without a Creator session", async () => {
    window.location.hash = "#/review/tok_old";
    render(<App />);

    expect(await screen.findByText("This review link was revoked or does not exist.")).toBeTruthy();
    expect(mockFetch.mock.calls.some(([url]) => String(url).includes("/api/review/tok_old"))).toBe(true);
  });
});
