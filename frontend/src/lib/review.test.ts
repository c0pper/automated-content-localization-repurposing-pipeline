import { describe, it, expect } from "vitest";
import { openReviewLink, reviewAssetUrl, reviewTokenFromUrl } from "@/lib/review";

describe("review access URLs", () => {
  it("extracts the token from the backend review_url", () => {
    expect(reviewTokenFromUrl("http://localhost:8000/api/review/tok_abc.sig")).toBe("tok_abc.sig");
    expect(reviewTokenFromUrl("https://api.example.com/api/review/tok_abc/")).toBe("tok_abc");
  });

  it("returns null when there is no usable review token", () => {
    expect(reviewTokenFromUrl(null)).toBeNull();
    expect(reviewTokenFromUrl("")).toBeNull();
    expect(reviewTokenFromUrl("http://localhost:8000/api/jobs/job_1")).toBeNull();
    expect(reviewTokenFromUrl("http://localhost:8000/api/review/")).toBeNull();
  });

  it("builds the in-app review page link for a review_url", () => {
    expect(openReviewLink("http://localhost:8000/api/review/tok_abc")).toBe("#/review/tok_abc");
    expect(openReviewLink(null)).toBeNull();
  });

  it("builds stable asset URLs through the review 302 route", () => {
    expect(reviewAssetUrl("tok_abc", "base_7")).toBe("/api/review/tok_abc/assets/base_7");
    expect(reviewAssetUrl("tok_abc", "clip_7_es")).toBe("/api/review/tok_abc/assets/clip_7_es");
  });
});
