import { describe, it, expect, afterEach } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { VideoPlayer } from "@/components/VideoPlayer";

function videoNamed(name: string): HTMLVideoElement {
  const el = screen.getByLabelText(name);
  expect(el.tagName).toBe("VIDEO");
  return el as HTMLVideoElement;
}

describe("VideoPlayer", () => {
  afterEach(() => cleanup());

  it("plays the given asset URL in a labelled native player with controls", () => {
    render(
      <VideoPlayer
        assetUrl="/api/jobs/job_1/assets/clip_3_es"
        label="Localized clip (es)"
        captionLanguage="es"
      />,
    );
    const video = videoNamed("Localized clip (es)");
    expect(video.getAttribute("src")).toBe("/api/jobs/job_1/assets/clip_3_es");
    expect(video.hasAttribute("controls")).toBe(true);
    expect(video.getAttribute("preload")).toBe("metadata");
  });

  it("states that captions are burned into the video in the caption language", () => {
    render(
      <VideoPlayer assetUrl="/a.mp4" label="Localized clip (de)" captionLanguage="de" />,
    );
    expect(screen.getByText("Captions burned in (de)")).toBeTruthy();
    expect(document.querySelector("track")).toBeNull();
  });

  it("binds a separate captions source as a captions track when one is given", () => {
    render(
      <VideoPlayer
        assetUrl="/a.mp4"
        captionsUrl="/a.es.vtt"
        label="Localized clip (es)"
        captionLanguage="es"
      />,
    );
    const track = videoNamed("Localized clip (es)").querySelector("track");
    expect(track?.getAttribute("src")).toBe("/a.es.vtt");
    expect(track?.getAttribute("kind")).toBe("captions");
    expect(track?.getAttribute("srclang")).toBe("es");
    expect(screen.queryByText("Captions burned in (es)")).toBeNull();
  });

  it("offers the asset as a link and reports a load failure", () => {
    render(<VideoPlayer assetUrl="/missing.mp4" label="Base clip" captionLanguage="en" />);
    const link = screen.getByRole("link", { name: "Open Base clip" });
    expect(link.getAttribute("href")).toBe("/missing.mp4");
    expect(screen.queryByRole("alert")).toBeNull();

    fireEvent.error(videoNamed("Base clip"));
    expect(screen.getByRole("alert").textContent).toContain("could not be loaded");
  });
});
