// @vitest-environment happy-dom
// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { createInstance } from "i18next";
import { I18nextProvider } from "react-i18next";
import { afterEach, beforeEach, expect, it } from "vitest";
import en from "../../../../locales/en/translation.json";
import fr from "../../../../locales/fr/translation.json";
import type { AgentPackage, MarketplacePackage } from "../../../../slices/controlPlane/controlPlaneOpenApi";
import MarketplacePackageView from "./MarketplacePackageView";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
let root: Root;
let host: HTMLDivElement;
const agent: AgentPackage = {
  display_name: "Research assistant",
  logical_name: "research-assistant",
  description: "Summarizes reports",
  role: "Research specialist",
  usage_statement: "Help analysts compare reports.",
  runtime_id: "internal-runtime",
  template_agent_id: "internal-template",
  model_options: { temperature: 0.2 },
  tuning_field_values: { "prompts.system": "Compare the sources.\n<script>example</script>", "custom.limit": 42 },
  capabilities: {
    ppt_filler: {
      schema_version: "1",
      config: { template: "opaque-setting" },
      files: { "templates/report.pptx": "UEs=" },
    },
    "mcp-knowledge-flow-mcp-tabular": { schema_version: "1", config: {}, files: {} },
    "custom-capability": { schema_version: "1", config: {}, files: {} },
  },
};
beforeEach(() => {
  host = document.createElement("div");
  document.body.appendChild(host);
  root = createRoot(host);
});
afterEach(() => {
  act(() => root.unmount());
  host.remove();
});
async function render(value: MarketplacePackage, language = "en") {
  const i18n = createInstance();
  await i18n.init({
    lng: language,
    fallbackLng: "en",
    resources: { en: { translation: en }, fr: { translation: fr } },
  });
  await act(async () =>
    root.render(
      <I18nextProvider i18n={i18n}>
        <MarketplacePackageView value={value} />
      </I18nextProvider>,
    ),
  );
}

it.each(["en", "fr"])(
  "presents exported agent content in %s with shared capability labels and downloadable files",
  async (language) => {
    await render({ kind: "agent", content: agent }, language);
    expect(host.textContent).toContain(agent.role);
    expect(host.textContent).toContain(agent.usage_statement);
    expect(host.querySelector("pre")?.textContent).toBe(agent.tuning_field_values["prompts.system"]);
    expect(host.querySelector("script")).toBeNull();
    const locale = language === "fr" ? fr : en;
    expect(host.textContent).toContain(locale.capability.ppt_filler.name);
    expect(host.textContent).toContain(locale.mcp.servers.tabular.name);
    expect(host.textContent).toContain("custom-capability");
    for (const technical of [
      "internal-runtime",
      "internal-template",
      "temperature",
      "custom.limit",
      "opaque-setting",
      "schema_version",
    ]) {
      expect(host.textContent).not.toContain(technical);
    }
    const files = host.querySelector<HTMLButtonElement>('button[aria-expanded="false"]')!;
    expect(files.textContent).toContain(locale.capability.ppt_filler.name);
    await act(async () => files.click());
    const download = host.querySelector<HTMLAnchorElement>("a[download]")!;
    expect(download.textContent).toBe("templates/report.pptx");
    expect(download.download).toBe("report.pptx");
    expect(download.href).toBe("data:application/octet-stream;base64,UEs=");
  },
);

it.each([undefined, "  ", { text: "not a prompt" }])(
  "shows explicit empty instructions for missing, blank or non-text exported values",
  async (instructions) => {
    await render({
      kind: "agent",
      content: { ...agent, capabilities: {}, tuning_field_values: { "prompts.system": instructions } },
    });
    expect(host.textContent).toContain(en.rework.localMarketplace.noInstructions);
    expect(host.textContent).toContain(en.rework.localMarketplace.noCapabilities);
    expect(host.querySelector("pre")).toBeNull();
    expect(host.querySelector("a")).toBeNull();
  },
);

it("preserves prompt and skill snapshot readers as literal text", async () => {
  await render({
    kind: "prompt",
    content: { display_name: "Prompt", logical_name: "summarize", tags: ["Research"], text: "<b>Frozen prompt</b>" },
  });
  expect(host.textContent).toContain("summarize · Research");
  expect(host.querySelector("pre")?.textContent).toBe("<b>Frozen prompt</b>");
  expect(host.querySelector("b")).toBeNull();
  await render({
    kind: "skill",
    content: {
      name: "Reports",
      files: { "SKILL.md": "# Report instructions", "references/rules.md": "<script>example</script>" },
    },
  });
  expect([...host.querySelectorAll("summary")].map((item) => item.textContent)).toEqual([
    "SKILL.md",
    "references/rules.md",
  ]);
  expect([...host.querySelectorAll("pre")].map((item) => item.textContent)).toEqual([
    "# Report instructions",
    "<script>example</script>",
  ]);
  expect(host.querySelector("script")).toBeNull();
});
