import { afterEach, expect, it, vi } from "vitest";
import { getConfig, getProperty, loadConfig } from "./config.tsx";

vi.mock("../security/KeycloakService", () => ({ createKeycloakInstance: vi.fn() }));

afterEach(() => vi.unstubAllGlobals());

it("loads branding from the deployment theme without accepting auth or feature overrides", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => ({
      ok: true,
      status: 200,
      json: async () => {
        if (url === "/config.json")
          return { properties: { siteTitle: "Stock", faviconName: "fred" }, feature_flags: { chat: true } };
        if (url === "/theme-properties.json")
          return { siteTitle: "Acme", logoName: "acme", user_auth: { enabled: true }, feature_flags: { chat: false } };
        if (url === "/theme-catalog.json") return { themes: [{ id: "acme", label: "Acme", base: "pebble" }] };
        return { user_auth: { enabled: false }, root_bootstrap_required: false };
      },
    })),
  );

  await loadConfig();

  expect(getProperty("siteTitle")).toBe("Acme");
  expect(getProperty("faviconName")).toBe("fred");
  expect(getProperty("logoName")).toBe("acme");
  expect(getConfig().user_auth.enabled).toBe(false);
  expect(getConfig().feature_flags.chat).toBe(true);
});
