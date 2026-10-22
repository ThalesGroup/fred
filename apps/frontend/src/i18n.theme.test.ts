import { afterEach, expect, it, vi } from "vitest";
import i18n, { loadThemeTranslations } from "./i18n.ts";

const original = i18n.getResource("en", "translation", "rework.uiSettings.title");
const tracePaths = {
  askUser: "platform.askUser",
  readSkillFile: "platform.readSkillFile",
  readQuery: "mcp.tabular.readQuery",
  documents: "mcp.tabular.documents",
  markdown: "mcp.tabular.markdown",
  schemas: "mcp.tabular.schemas",
  descriptions: "mcp.tabular.descriptions",
  search: "mcp.tabular.search",
  webSearch: "capabilities.webResearch.webSearch",
  fetchUrl: "capabilities.webResearch.fetchUrl",
};
const originalTraceLabels = Object.fromEntries(
  ["en", "fr"].flatMap((language) =>
    Object.values(tracePaths).map((path) => {
      const key = `rework.chatTrace.toolLabels.${path}`;
      return [`${language}:${key}`, i18n.getResource(language, "translation", key)];
    }),
  ),
);
afterEach(() => {
  vi.unstubAllGlobals();
  i18n.addResource("en", "translation", "rework.uiSettings.title", original);
  for (const [languageAndKey, value] of Object.entries(originalTraceLabels)) {
    const [language, key] = languageAndKey.split(":", 2);
    i18n.addResource(language, "translation", key, value);
  }
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

it("applies old trace label override keys to their current categories", async () => {
  const legacyLabels = Object.fromEntries(Object.keys(tracePaths).map((name) => [name, `Custom ${name}`]));
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => ({
      ok: true,
      status: 200,
      json: async () =>
        url.endsWith("/en.json")
          ? {
              rework: {
                chatTrace: {
                  toolLabels: { ...legacyLabels, mcp: { tabular: { documents: "Current documents" } } },
                },
              },
            }
          : { rework: { chatTrace: { toolLabels: { readQuery: "Consultation personnalisée" } } } },
    })),
  );

  await loadThemeTranslations();

  for (const [name, path] of Object.entries(tracePaths)) {
    expect(i18n.getFixedT("en")(`rework.chatTrace.toolLabels.${path}`)).toBe(
      name === "documents" ? "Current documents" : `Custom ${name}`,
    );
  }
  expect(i18n.getFixedT("fr")("rework.chatTrace.toolLabels.mcp.tabular.readQuery")).toBe("Consultation personnalisée");
});
