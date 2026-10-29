import { beforeEach, describe, expect, it } from "vitest";
import { createLocalizationStore } from "./localizationStore";

describe("localization store", () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.removeAttribute("lang");
  });

  it("defaults the UI language to English", () => {
    const store = createLocalizationStore();
    expect(store.getState().uiLanguage).toBe("en");
    expect(document.documentElement.lang).toBe("en");
  });

  it("switches the UI language and tags the document with it", () => {
    const store = createLocalizationStore();
    store.getState().setUILanguage("de");
    expect(store.getState().uiLanguage).toBe("de");
    expect(document.documentElement.lang).toBe("de");
  });

  it("ignores languages without a string table", () => {
    const store = createLocalizationStore();
    store.getState().setUILanguage("es");
    store.getState().setUILanguage("fr");
    expect(store.getState().uiLanguage).toBe("es");
  });

  it("restores the chosen UI language after a reload", () => {
    createLocalizationStore().getState().setUILanguage("es");
    document.documentElement.removeAttribute("lang");

    const next = createLocalizationStore();
    expect(next.getState().uiLanguage).toBe("es");
    expect(document.documentElement.lang).toBe("es");
  });

  it("falls back to English when the persisted language is unknown", () => {
    localStorage.setItem(
      "creator-localization-storage",
      JSON.stringify({ state: { uiLanguage: "fr" }, version: 1 }),
    );
    expect(createLocalizationStore().getState().uiLanguage).toBe("en");
  });
});
