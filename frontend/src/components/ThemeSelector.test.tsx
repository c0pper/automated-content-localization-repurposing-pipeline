import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { ThemeSelector } from "./ThemeSelector";
import { themeStore } from "@/store";

const rootAccent = () =>
  document.documentElement.style.getPropertyValue("--accent").trim();

describe("ThemeSelector", () => {
  beforeEach(() => {
    themeStore.getState().setAccentColor("cyan");
  });
  afterEach(() => cleanup());

  it("offers four accent options with cyan selected by default", () => {
    render(<ThemeSelector />);
    const group = screen.getByRole("radiogroup", { name: "Accent color" });
    const radios = screen.getAllByRole("radio");
    expect(group).toBeTruthy();
    expect(radios.map((r) => r.getAttribute("aria-label"))).toEqual([
      "Cyan",
      "Electric green",
      "Magenta",
      "Amber",
    ]);
    expect(screen.getByRole("radio", { name: "Cyan" }).getAttribute("aria-checked")).toBe("true");
  });

  it("applies the selected accent across the document instantly", () => {
    render(<ThemeSelector />);
    fireEvent.click(screen.getByRole("radio", { name: "Amber" }));
    expect(screen.getByRole("radio", { name: "Amber" }).getAttribute("aria-checked")).toBe("true");
    expect(screen.getByRole("radio", { name: "Cyan" }).getAttribute("aria-checked")).toBe("false");
    expect(rootAccent()).toBe("#ffbf00");
  });

  it("supports arrow-key navigation between accents", () => {
    render(<ThemeSelector />);
    fireEvent.keyDown(screen.getByRole("radio", { name: "Cyan" }), { key: "ArrowRight" });
    expect(screen.getByRole("radio", { name: "Electric green" }).getAttribute("aria-checked")).toBe("true");
    expect(rootAccent()).toBe("#00ff00");
    fireEvent.keyDown(screen.getByRole("radio", { name: "Electric green" }), { key: "ArrowLeft" });
    fireEvent.keyDown(screen.getByRole("radio", { name: "Cyan" }), { key: "ArrowLeft" });
    expect(rootAccent()).toBe("#ffbf00");
  });
});
