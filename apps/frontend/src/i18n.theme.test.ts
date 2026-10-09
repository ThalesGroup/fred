import { afterEach, expect, it, vi } from "vitest";
import i18n, { loadThemeTranslations } from "./i18n.ts";

const original = i18n.getResource("en", "translation", "rework.uiSettings.title");
afterEach(() => {
  vi.unstubAllGlobals();
  i18n.addResource("en", "translation", "rework.uiSettings.title", original);
});

it("merges ZIP labels while keeping every unspecified shipped message", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => ({
      ok: true,
      status: 200,
      json: async () => (url.endsWith("/en.json") ? { rework: { uiSettings: { title: "Acme interface" } } } : {}),
    })),
  );

  await loadThemeTranslations();

  expect(i18n.getFixedT("en")("rework.uiSettings.title")).toBe("Acme interface");
  expect(i18n.getFixedT("en")("rework.userSettings.app.themePebble")).toBe("Pebble");
});
