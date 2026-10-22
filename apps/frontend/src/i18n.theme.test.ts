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

it("ignores keys that are not shipped labels and never blocks on a broken file", async () => {
  vi.spyOn(console, "warn").mockImplementation(() => {});
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) =>
      url.endsWith("/en.json")
        ? { ok: true, status: 200, json: async () => ({ valueOf: { call: "x" }, rework: "flattened" }) }
        : { ok: false, status: 503, json: async () => ({}) },
    ),
  );

  await expect(loadThemeTranslations()).resolves.toBeUndefined();

  expect(typeof Object.prototype.valueOf.call).toBe("function");
  expect(i18n.getFixedT("en")("rework.userSettings.app.themePebble")).toBe("Pebble");
});
