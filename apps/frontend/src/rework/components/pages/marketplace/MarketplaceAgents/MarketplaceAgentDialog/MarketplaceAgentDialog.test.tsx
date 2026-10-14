// @vitest-environment happy-dom
// Copyright Thales 2026
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

// The read-only "ID card" of a marketplace agent: Import is the only action
// for users; platform admins may also remove it with a message.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";
import type {
  MarketplaceAgentDetail,
  MarketplaceAgentSummary,
} from "../../../../../../slices/controlPlane/controlPlaneOpenApi";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const h = vi.hoisted(() => ({
  canAdmin: false,
  detail: undefined as unknown,
  unpublishCalls: [] as unknown[],
  unpublishError: undefined as unknown,
  refetch: vi.fn(),
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) => (opts ? `${key} ${JSON.stringify(opts)}` : key),
    i18n: { language: "en" },
  }),
}));
vi.mock("@shared/molecules/Toast/ToastProvider", () => ({
  useToast: () => ({ showSuccess: vi.fn(), showError: vi.fn() }),
}));
vi.mock("@hooks/useUserCapabilities.ts", () => ({
  useUserCapabilities: () => ({ canAdmin: h.canAdmin }),
}));
vi.mock("../../../../../../hooks/useFrontendProperties.ts", () => ({
  useFrontendProperties: () => ({ agentIconName: "smart_toy" }),
}));
vi.mock("../../../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useMarketplaceAgentQuery: () => ({ data: h.detail, isError: false, refetch: h.refetch }),
  useUnpublishAgentMutation: () => [
    (arg: unknown) => {
      h.unpublishCalls.push(arg);
      return {
        unwrap: async () => {
          if (h.unpublishError) throw h.unpublishError;
        },
      };
    },
    { isLoading: false },
  ],
}));

import MarketplaceAgentDialog from "./MarketplaceAgentDialog";
import styles from "./MarketplaceAgentDialog.module.css";
import dialogStyles from "@shared/molecules/Dialog/Dialog.module.css";
import promptStyles from "@shared/molecules/PromptEditor/PromptEditor.module.css";

const summary = { entry_id: "entry-1", team_id: "team-pub", display_name: "Analyst" } as MarketplaceAgentSummary;

const detail: MarketplaceAgentDetail = {
  entry_id: "entry-1",
  agent_instance_id: "agent-1",
  team_id: "team-pub",
  team_name: "Source Team",
  template_id: "pod:basic",
  display_name: "Analyst",
  description: "Reads reports",
  role: "Report reader",
  version: 3,
  first_published_at: "2026-09-01T10:00:00Z",
  published_at: "2026-10-01T10:00:00Z",
  like_count: 5,
  likes_since_update: 1,
  import_count: 7,
  tuning_field_values: { "prompts.system": "Be precise." },
  capabilities: [{ id: "ppt_filler", name: "capability.ppt.name", description: "capability.ppt.description" }],
  files: [{ capability_id: "ppt_filler", filename: "template.pptx", size: 2048 }],
};

const buttons = () => Array.from(document.querySelectorAll("button")).map((b) => b.textContent?.trim() ?? "");

describe("MarketplaceAgentDialog", () => {
  let container: HTMLDivElement;
  let root: Root;
  const onImport = vi.fn();

  const render = () => {
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    act(() => {
      root.render(<MarketplaceAgentDialog agent={summary} onImport={onImport} onClose={() => {}} />);
    });
  };

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
    h.canAdmin = false;
    h.unpublishCalls.length = 0;
    h.unpublishError = undefined;
    h.refetch.mockReset();
    onImport.mockReset();
  });

  it("summarises identity, capabilities, instructions, files and likes per version", () => {
    h.detail = detail;
    render();
    const text = document.body.textContent ?? "";
    expect(text).toContain("Report reader");
    expect(text).toContain("rework.marketplace.agents.detail.publishedBy");
    expect(text).toContain("Source Team");
    expect(text).toContain("capability.ppt.name");
    expect(text).toContain("capability.ppt.description");
    expect(text).toContain("Be precise.");
    expect(text).toContain("template.pptx");
    expect(text).toMatch(/2(\.0)?\s?kB|2(\.0)?\s?KB|2\s?Ko/i);
    expect(text).toContain('rework.agentMarketplace.likes {"count":5}');
    // The likes since the last update show in a tooltip on the likes chip.
    const likesChip = Array.from(document.querySelectorAll("li")).find((li) =>
      li.textContent?.includes("rework.agentMarketplace.likes"),
    );
    const trigger = likesChip?.querySelector("[tabindex]");
    act(() => trigger?.dispatchEvent(new MouseEvent("mouseover", { bubbles: true })));
    expect(document.querySelector('[role="tooltip"]')?.textContent).toContain(
      'rework.marketplace.agents.detail.likesSinceUpdateTooltip {"count":1',
    );
    expect(text).toContain('rework.agentMarketplace.imports {"count":7}');
  });

  it("opens the summary with the publication line, then the name above the role", () => {
    h.detail = detail;
    render();
    const summary = document.querySelector(`.${styles.summary}`);
    expect(summary?.firstElementChild?.textContent).toContain("rework.marketplace.agents.detail.publishedBy");
    expect(summary?.querySelector(`.${styles.name}`)?.textContent).toBe("Analyst");
    expect(summary?.querySelector(`.${styles.name}`)?.nextElementSibling?.textContent).toBe("Report reader");
  });

  it("shows the information and the instructions in two separate columns", () => {
    h.detail = detail;
    render();
    const info = document.querySelector(`.${styles.infoColumn}`);
    const instructions = document.querySelector(`.${styles.instructionsColumn}`);
    expect(info?.parentElement).toBe(instructions?.parentElement);
    expect(info?.textContent).toContain("capability.ppt.name");
    expect(info?.textContent).toContain("template.pptx");
    expect(info?.textContent).not.toContain("Be precise.");
    expect(instructions?.textContent).toContain("Be precise.");
  });

  it("lets the instructions scroll on their own instead of the whole dialog body", () => {
    h.detail = detail;
    render();
    const content = document.querySelector(`.${dialogStyles.content}`);
    expect(content?.getAttribute("data-scroll-mode")).toBe("children");
    expect(document.querySelector('[role="dialog"]')?.className).toContain(dialogStyles.dividers);
    expect(content?.querySelector(`.${styles.instructions}`)).not.toBeNull();
  });

  it("colours the instructions like the prompt editor, keeping the text intact", () => {
    const prompt = "# Role\nBe **precise**.\n<rules>\n- cite sources\n</rules>";
    h.detail = { ...detail, tuning_field_values: { "prompts.system": prompt } };
    render();
    const block = document.querySelector(`.${styles.instructions}`);
    expect(block?.textContent).toBe(prompt);
    const styled = (className: string) =>
      Array.from(block?.querySelectorAll(`span.${className}`) ?? [], (span) => span.textContent).join("");
    expect(styled(promptStyles.heading)).toContain("Role");
    expect(styled(promptStyles.strong)).toContain("precise");
    expect(block?.querySelector(`span.${promptStyles.tag}`)).not.toBeNull();
    expect(block?.querySelector(`span.${promptStyles.listMarker}`)?.textContent).toBe("-");
  });

  it("offers Import only: no chat, edit or download, and no removal for users", () => {
    h.detail = detail;
    render();
    expect(buttons()).toEqual(["rework.marketplace.agents.detail.close", "rework.marketplace.agents.detail.import"]);
    expect(document.querySelector("a[download], a[href]")).toBeNull();
    const importButton = Array.from(document.querySelectorAll("button")).find(
      (b) => b.textContent?.trim() === "rework.marketplace.agents.detail.import",
    );
    act(() => importButton?.click());
    expect(onImport).toHaveBeenCalledWith(summary);
  });

  it("shows plain likes when the agent was never republished", () => {
    h.detail = { ...detail, published_at: detail.first_published_at };
    render();
    expect(document.body.textContent).toContain('rework.agentMarketplace.likes {"count":5}');
    expect(document.body.textContent).not.toContain("likesSinceUpdate");
  });

  const openRemoval = () => {
    const remove = Array.from(document.querySelectorAll("button")).find((b) =>
      b.textContent?.includes("rework.agentMarketplace.menu.remove"),
    );
    act(() => remove?.click());
  };
  const confirmRemoval = async () => {
    const confirm = Array.from(document.querySelectorAll("button")).find(
      (b) => b.textContent?.trim() === "rework.marketplace.agents.remove.confirm",
    );
    await act(async () => confirm?.click());
  };

  it("puts a platform admin's removal at the far left of the action bar", () => {
    h.canAdmin = true;
    h.detail = detail;
    render();
    const actions = document.querySelector(`.${dialogStyles.actions}`);
    const labels = Array.from(actions?.querySelectorAll("button") ?? []).map((b) => b.textContent?.trim());
    expect(labels).toEqual([
      expect.stringContaining("rework.agentMarketplace.menu.remove"),
      "rework.marketplace.agents.detail.close",
      "rework.marketplace.agents.detail.import",
    ]);
    expect(actions?.querySelector(`.${dialogStyles.actionsStart}`)?.textContent).toContain(
      "rework.agentMarketplace.menu.remove",
    );
  });

  it("lets a platform admin remove the agent with a message", async () => {
    h.canAdmin = true;
    h.detail = detail;
    render();
    openRemoval();
    const textarea = document.querySelector("textarea") as HTMLTextAreaElement;
    act(() => {
      const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value")?.set;
      setter?.call(textarea, "Outdated instructions");
      textarea.dispatchEvent(new Event("input", { bubbles: true }));
    });
    await confirmRemoval();
    expect(h.refetch).not.toHaveBeenCalled();
    expect(h.unpublishCalls).toEqual([
      {
        teamId: "team-pub",
        agentInstanceId: "agent-1",
        unpublishAgentRequest: { expected_version: 3, reason: "Outdated instructions" },
      },
    ]);
  });

  it("refetches the detail after a stale version so a retry carries the current one", async () => {
    h.canAdmin = true;
    h.detail = detail;
    h.unpublishError = { status: 409, data: { detail: { code: "marketplace_version_conflict", message: "stale" } } };
    render();
    openRemoval();
    await confirmRemoval();
    expect(h.refetch).toHaveBeenCalledTimes(1);
  });
});
