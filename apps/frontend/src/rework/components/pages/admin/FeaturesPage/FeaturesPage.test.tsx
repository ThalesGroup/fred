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

// Each resource tab receives the current organization; registry behavior has its own suite.
// `t` is mocked to echo its key (plus any interpolated count), so we assert on
// which key each state uses and on the enabled-team count it renders.

import { createRoot, type Root } from "react-dom/client";
import { act } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const h = vi.hoisted(() => ({
  drawer: undefined as
    | undefined
    | { organizationId: string; runtimeId?: string; capability: { id: string; route_base_url?: string } | null },
  // Every key `t` was asked for during the last render. Needed for hints that
  // live in a `Tooltip`: its panel is portaled and only mounts once hovered, so
  // the rendered markup never contains the hint text — the key request is the
  // only observable signal that the hint was wired up.
  tKeys: [] as string[],
}));
const translate = vi.hoisted(
  () => (key: string, opts?: { defaultValue?: string; count?: number; content?: string }) => {
    h.tKeys.push(key);
    const interpolated = opts?.count ?? opts?.content;
    return opts?.defaultValue ?? (interpolated === undefined ? key : `${key}:${interpolated}`);
  },
);

// `t` echoes its key, but appends an interpolated `count` (or the composed
// `content` of the "All (…)" wrapper) when one is passed — those are the values
// under test for the enabled-teams column, and a bare key echo would hide
// whether the right number ever reached the label.
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: translate,
    i18n: { language: "en" },
  }),
}));

vi.mock("../../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useOrganizationAgentsQuery: () => ({ currentData: undefined, isLoading: false, isError: false }),
  useSetOrganizationAgentDefaultMutation: () => [() => ({ unwrap: async () => ({}) }), { isLoading: false }],
  useSetOrganizationCapabilityDefaultMutation: () => [vi.fn(), { isLoading: false }],
  useOrganizationCapabilitiesQuery: () => ({ data: undefined }),
  useLazyOrganizationCapabilityRevokeImpactQuery: () => [vi.fn(), { data: undefined, isFetching: false }],
}));

vi.mock("./OrganizationKnowledgeBases", () => ({
  default: ({ organizationId }: { organizationId: string }) => <p>organization-kbs:{organizationId}</p>,
}));

vi.mock("@shared/molecules/Toast/ToastProvider", () => ({
  useToast: () => ({ showSuccess: vi.fn(), showError: vi.fn(), showWarn: vi.fn(), showInfo: vi.fn() }),
}));

// The offers panel has its own suite; a marker is enough to see which panel the page chose.
vi.mock("./OrganizationApplications", () => ({
  default: ({ organizationId }: { organizationId: string }) => <p>organization-applications:{organizationId}</p>,
}));
vi.mock("./OrganizationCapabilities", () => ({
  OrganizationCapabilities: ({
    capabilityColumns,
  }: {
    capabilityColumns: import("@shared/molecules/DataTable/LocalizedDataTable").DataTableColumn<
      import("../../../../../slices/controlPlane/controlPlaneOpenApi").CapabilityInventoryOffer
    >[];
  }) => (
    <>
      <p>organization-offers</p>
      {capabilityColumns
        .filter((c) => c.label === "rework.admin.capabilities.col.settings")
        .map((c) => (
          <section key={c.label}>
            {c.label}
            {["ppt_builder", "ppt_filler"].map((id) => (
              <div key={id} data-offer={id}>
                {c.cellRenderer?.({
                  capability_id: id,
                  source_id: "pod-b",
                  origin: "pod",
                  runtime_id: "pod-b",
                  advertised: true,
                  route_base_url: "/pod-b/ppt_builder",
                  descriptor: { name: id },
                } as import("../../../../../slices/controlPlane/controlPlaneOpenApi").CapabilityInventoryOffer)}
              </div>
            ))}
          </section>
        ))}
    </>
  ),
}));

// Only ppt_builder declares a platform panel here; the drawer is exercised by its panel's own tests.
vi.mock("../../../../features/capabilities/platformPanelRegistry", () => ({
  platformPanelFor: (id: string) => (id === "ppt_builder" ? () => null : undefined),
}));
vi.mock("./CapabilityPlatformDrawer", () => ({
  CapabilityPlatformDrawer: (props: typeof h.drawer) => {
    h.drawer = props;
    return null;
  },
}));

vi.mock("../McpConnectionsPage/McpConnectionsPage", () => ({
  default: ({ spaceId }: { spaceId: string }) => <p data-mcp-space={spaceId}>MCP {spaceId}</p>,
}));

import FeaturesPage from "./FeaturesPage";

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  container = document.createElement("div");
  document.body.append(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

/** Render the organization page and open the Knowledge Bases tab. */
function renderKnowledgeBases(): string {
  h.tKeys = [];
  act(() => root.render(<FeaturesPage organizationId="O1" />));
  const tab = Array.from(container.querySelectorAll<HTMLElement>('[role="radio"]')).find((element) =>
    element.textContent?.endsWith("kindFilter.knowledge_base"),
  );
  if (!tab) throw new Error("no Knowledge Bases tab");
  act(() => tab.click());
  return container.innerHTML;
}

it("routes Knowledge Bases to the current organization's registry", () => {
  expect(renderKnowledgeBases()).toContain("organization-kbs:O1");
  act(() => root.render(<FeaturesPage organizationId="O2" />));
  expect(container.textContent).toContain("organization-kbs:O2");
});

describe("FeaturesPage kind filter", () => {
  it("always exposes Applications through the organization registry", () => {
    renderKnowledgeBases();
    const appsTab = Array.from(container.querySelectorAll<HTMLElement>('[role="radio"]')).find((element) =>
      element.textContent?.endsWith("kindFilter.app"),
    );
    expect(appsTab).toBeDefined();
    act(() => appsTab!.click());
    expect(container.textContent).toContain("organization-applications:O1");
    expect(container.textContent).not.toContain("cap.legacy_app");
  });
});

it("opens the common-template drawer from the Swift settings gear on ppt_builder alone", async () => {
  await act(async () => root.render(<FeaturesPage organizationId="org-a" />));
  const tab = [...container.querySelectorAll("button")].find((button) =>
    button.textContent?.includes("kindFilter.tool"),
  );
  expect(tab).toBeDefined();
  await act(async () => tab!.click());
  const gear = container.querySelector<HTMLButtonElement>('[data-offer="ppt_builder"] button');
  expect(gear?.getAttribute("aria-label")).toBe("rework.admin.capabilities.platformSettings");
  expect(container.querySelector('[data-offer="ppt_filler"] button')).toBeNull();
  await act(async () => gear!.click());
  expect(h.drawer).toMatchObject({
    organizationId: "org-a",
    runtimeId: "pod-b",
    capability: { id: "ppt_builder", route_base_url: "/pod-b/ppt_builder" },
  });
});

it("places MCP beside models and passes the selected organization space", () => {
  act(() => root.render(<FeaturesPage organizationId="org-a" />));
  const tabs = [...container.querySelectorAll("button")];
  const models = tabs.findIndex((button) => button.textContent?.endsWith("kindFilter.model"));
  expect(tabs[models + 1].textContent).toContain("kindFilter.mcp");
  act(() => tabs[models + 1].click());
  expect(container.querySelector("[data-mcp-space]")?.getAttribute("data-mcp-space")).toBe("org-a");
  act(() => root.render(<FeaturesPage organizationId="org-b" />));
  expect(container.querySelector("[data-mcp-space]")?.getAttribute("data-mcp-space")).toBe("org-b");
});
