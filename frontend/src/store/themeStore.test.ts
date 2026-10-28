import { beforeEach, describe, expect, it } from "vitest";
import { contrastRatio } from "@/lib/contrast";
import { BACKGROUND, THEMES, createThemeStore } from "./themeStore";

const rootVar = (name: string) =>
  document.documentElement.style.getPropertyValue(name).trim();

describe("theme store", () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.removeAttribute("style");
  });

  it("offers exactly the four neon accents from the spec", () => {
    expect(
      Object.fromEntries(THEMES.map((t) => [t.name, t.accent.toLowerCase()])),
    ).toEqual({
      cyan: "#00ffff",
      green: "#00ff00",
      magenta: "#ff00ff",
      amber: "#ffbf00",
    });
  });

  it("applies cyan to the document by default", () => {
    const store = createThemeStore();
    expect(store.getState().theme.name).toBe("cyan");
    expect(rootVar("--accent")).toBe("#00ffff");
    expect(rootVar("--accent-rgb")).toBe("0 255 255");
  });

  it("applies the chosen accent to the document immediately", () => {
    const store = createThemeStore();
    store.getState().setAccentColor("magenta");
    expect(rootVar("--accent")).toBe("#ff00ff");
    expect(rootVar("--accent-rgb")).toBe("255 0 255");
    expect(rootVar("--accent-contrast")).toBe("#000000");
  });

  it("ignores unknown accent names", () => {
    const store = createThemeStore();
    store.getState().setAccentColor("amber");
    store.getState().setAccentColor("chartreuse");
    expect(store.getState().theme.name).toBe("amber");
    expect(rootVar("--accent")).toBe("#ffbf00");
  });

  it("restores the persisted accent in a new session", () => {
    createThemeStore().getState().setAccentColor("green");
    document.documentElement.removeAttribute("style");

    const next = createThemeStore();
    expect(next.getState().theme.name).toBe("green");
    expect(rootVar("--accent")).toBe("#00ff00");
  });

  it.each(THEMES.map((t) => [t.name, t] as const))(
    "%s meets WCAG AA as text on the black background and behind its contrast text",
    (_name, theme) => {
      expect(contrastRatio(theme.accent, BACKGROUND)).toBeGreaterThanOrEqual(4.5);
      expect(contrastRatio(theme.contrast, theme.accent)).toBeGreaterThanOrEqual(4.5);
    },
  );
});
