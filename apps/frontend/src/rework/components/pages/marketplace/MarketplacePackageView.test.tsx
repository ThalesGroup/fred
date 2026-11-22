// @vitest-environment happy-dom
// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { createInstance } from "i18next";
import { I18nextProvider } from "react-i18next";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import en from "../../../../locales/en/translation.json";
import fr from "../../../../locales/fr/translation.json";
import type { AgentPackage, MarketplacePackage } from "../../../../slices/controlPlane/controlPlaneOpenApi";
import MarketplacePackageView from "./MarketplacePackageView";

const downloads = vi.hoisted(() => ({ run: vi.fn(), error: vi.fn() }));
vi.mock("@rework/features/imports/managerDocuments", () => ({ downloadManagerDocument: downloads.run }));
vi.mock("./marketplace", () => ({ useMarketplaceSession: () => () => true }));
vi.mock("@shared/molecules/Toast/ToastProvider", () => ({
  useToast: () => ({ showSuccess: vi.fn(), showError: downloads.error }),
}));

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
      files: {
        "templates/report.pptx": {
          document_id: "private-id",
          name: "report.pptx",
          mime: "application/vnd.openxmlformats-officedocument.presentationml.presentation",
          size: 2048,
          sha256: "private-hash",
        },
      },
    },
    "mcp-knowledge-flow-mcp-tabular": { schema_version: "1", config: {}, files: {} },
    "custom-capability": { schema_version: "1", config: {}, files: {} },
  },
};
beforeEach(() => {
  downloads.run.mockReset();
  downloads.error.mockReset();
  host = document.createElement("div");
  document.body.appendChild(host);
  root = createRoot(host);
});
afterEach(() => {
  act(() => root.unmount());
  host.remove();
});
async function render(value: MarketplacePackage, language = "en", canDownload = true) {
  const i18n = createInstance();
  await i18n.init({
    lng: language,
    fallbackLng: "en",
    resources: { en: { translation: en }, fr: { translation: fr } },
  });
  await act(async () =>
    root.render(
      <I18nextProvider i18n={i18n}>
        <MarketplacePackageView value={value} canDownload={canDownload} />
      </I18nextProvider>,
    ),
  );
}

it.each(["en", "fr"])(
  "presents exported agent content in %s with shared capability labels and file descriptions",
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
    expect(host.textContent).toContain("report.pptx");
    expect(host.textContent).toContain("application/vnd.openxmlformats-officedocument.presentationml.presentation");
    expect(host.textContent).not.toContain("private-id");
    expect(host.textContent).not.toContain("private-hash");
    expect(host.querySelector("a[download]")).toBeNull();
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

it("reuses the prompt and skill library readers without executing HTML", async () => {
  await render({
    kind: "prompt",
    content: { display_name: "Prompt", logical_name: "summarize", tags: ["Research"], text: "<b>Frozen prompt</b>" },
  });
  expect(host.textContent).toContain("/summarize");
  expect(host.textContent).toContain("Research");
  expect(host.textContent).toContain("<b>Frozen prompt</b>");
  expect(host.querySelector("b")).toBeNull();
  await render({
    kind: "skill",
    content: {
      name: "Reports",
      files: { "SKILL.md": "# Report instructions", "references/rules.md": "Reference text\n<script>example</script>" },
    },
  });
  expect(host.querySelector("h1")?.textContent).toBe("Report instructions");
  const reference = [...host.querySelectorAll("button")].find((item) => item.textContent === "references/rules.md")!;
  await act(async () => reference.click());
  expect(host.textContent).toContain("Reference text");
  expect(host.querySelector("script")).toBeNull();
});

it("downloads an inspected configuration file through the existing authenticated document helper", async () => {
  await render({ kind: "agent", content: agent });
  await act(async () => host.querySelector<HTMLButtonElement>('button[aria-expanded="false"]')!.click());
  await act(async () => host.querySelector<HTMLButtonElement>('button[aria-label="Download report.pptx"]')!.click());
  expect(downloads.run).toHaveBeenCalledWith({ id: "private-id", name: "report.pptx", size: 2048 });
  expect(host.querySelector('a[href^="data:"]')).toBeNull();
});

it("disables configuration downloads while package authority is being refreshed", async () => {
  await render({ kind: "agent", content: agent }, "en", false);
  await act(async () => host.querySelector<HTMLButtonElement>('button[aria-expanded="false"]')!.click());
  const button = host.querySelector<HTMLButtonElement>('button[aria-label="Download report.pptx"]')!;
  expect(button.disabled).toBe(true);
  await act(async () => button.click());
  expect(downloads.run).not.toHaveBeenCalled();
});

it("reports a failed configuration download through the shared toast", async () => {
  downloads.run.mockRejectedValue(new Error("download_failed_404"));
  await render({ kind: "agent", content: agent });
  await act(async () => host.querySelector<HTMLButtonElement>('button[aria-expanded="false"]')!.click());
  await act(async () => host.querySelector<HTMLButtonElement>('button[aria-label="Download report.pptx"]')!.click());
  expect(downloads.error).toHaveBeenCalledWith({ summary: "Could not download report.pptx" });
});

it("keeps the shared download button busy until the authenticated transfer finishes", async () => {
  let complete!: () => void;
  downloads.run.mockImplementation(
    () =>
      new Promise<void>((resolve) => {
        complete = resolve;
      }),
  );
  await render({ kind: "agent", content: agent });
  await act(async () => host.querySelector<HTMLButtonElement>('button[aria-expanded="false"]')!.click());
  const button = host.querySelector<HTMLButtonElement>('button[aria-label="Download report.pptx"]')!;
  await act(async () => button.click());
  expect(button.disabled).toBe(true);
  expect(button.getAttribute("aria-busy")).toBe("true");
  await act(async () => complete());
  expect(button.disabled).toBe(false);
});
