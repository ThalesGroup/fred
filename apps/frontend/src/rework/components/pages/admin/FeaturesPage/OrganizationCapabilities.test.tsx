// @vitest-environment happy-dom
// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

// Organization capability inventory: one row per pod, then that pod's offers in the catalog table.
// `t` echoes its key followed by the interpolated values, so assertions name keys.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type {
  CapabilityInventoryOffer,
  PodCapabilityInventory,
  RefreshOrganizationCapabilitiesApiArg,
} from "../../../../../slices/controlPlane/controlPlaneOpenApi";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const h = vi.hoisted(() => ({
  query: { currentData: undefined, isFetching: false, isError: false } as {
    currentData?: PodCapabilityInventory[];
    isFetching: boolean;
    isError: boolean;
  },
  refreshes: [] as RefreshOrganizationCapabilitiesApiArg[],
  refreshFails: false,
  errors: [] as string[],
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) => {
      const values = Object.entries(opts ?? {})
        .filter(([name]) => name !== "defaultValue")
        .map(([, value]) => String(value));
      return [key, ...values].join(":");
    },
    i18n: { language: "en" },
  }),
}));

vi.mock("../../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useOrganizationCapabilitiesQuery: () => h.query,
  useRefreshOrganizationCapabilitiesMutation: () => [
    (arg: RefreshOrganizationCapabilitiesApiArg) => ({
      unwrap: async () => {
        h.refreshes.push(arg);
        if (h.refreshFails) throw { status: 503, data: { detail: "pod inventory unavailable" } };
      },
    }),
  ],
}));

vi.mock("@shared/molecules/Toast/ToastProvider", () => ({
  useToast: () => ({ showError: ({ summary }: { summary: string }) => h.errors.push(summary) }),
}));

import { OrganizationCapabilities } from "./OrganizationCapabilities";

const pod = (over: Partial<PodCapabilityInventory> & Pick<PodCapabilityInventory, "runtime_id">) =>
  ({
    enabled: true,
    observation: "observed",
    checked_at: "2026-10-28T08:00:00Z",
    observed_at: "2026-10-28T08:00:00Z",
    capabilities: [],
    template_capabilities: [],
    ...over,
  }) satisfies PodCapabilityInventory;

const offer = (capability_id: string, advertised = true): CapabilityInventoryOffer => ({
  runtime_id: "fred-agents",
  capability_id,
  version: "1",
  advertised,
  default_on: false,
  unusable_instances: [],
  descriptor: { id: capability_id, name: capability_id, description: "", icon: "description", version: "1" },
});

// The real columns belong to FeaturesPage; this stub shows which offers reach the table.
const columns = [{ label: "offer", cellRenderer: (item: CapabilityInventoryOffer) => `offer-${item.capability_id}` }];

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  h.query = { currentData: undefined, isFetching: false, isError: false };
  h.refreshes = [];
  h.refreshFails = false;
  h.errors = [];
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

const render = async () => {
  await act(async () => root.render(<OrganizationCapabilities organizationId="O1" capabilityColumns={columns} />));
};
const button = (label: string) =>
  Array.from(container.querySelectorAll("button")).find((element) =>
    element.textContent?.includes(label),
  ) as HTMLButtonElement;
const selectPod = () => act(async () => (container.querySelector("[data-activatable]") as HTMLElement).click());

describe("OrganizationCapabilities", () => {
  it("refreshes once each enabled pod that was never observed", async () => {
    h.query.currentData = [
      pod({ runtime_id: "fresh", observation: "not_observed" }),
      pod({ runtime_id: "known" }),
      pod({ runtime_id: "disabled", enabled: false, observation: "not_observed" }),
    ];
    await render();
    await render();
    expect(h.refreshes).toEqual([{ organizationId: "O1", runtimeId: "fresh" }]);
    expect(container.textContent).toContain("observation.not_observed");
  });

  it("replaces the pod table with the selected pod's offers, then goes back", async () => {
    h.query.currentData = [
      pod({ runtime_id: "fred-agents", capabilities: [offer("ppt_filler"), offer("legacy", false)] }),
      pod({ runtime_id: "other", capabilities: [offer("elsewhere")] }),
    ];
    await render();
    expect(container.textContent).toContain("observation.observed");
    expect(container.textContent).not.toContain("offer-");

    await selectPod();
    const text = container.textContent ?? "";
    expect(text).toContain("organizationCapabilities.backToPods");
    expect(text).toContain("fred-agents");
    expect(text).toContain("offer-ppt_filler");
    expect(text).toContain("offer-legacy");
    expect(text).not.toContain("offer-elsewhere");
    expect(text).not.toContain("observation.observed");
    expect(text).not.toContain("unavailableHint");

    await act(async () => button("backToPods").click());
    expect(container.textContent).not.toContain("offer-");
    expect(container.textContent).toContain("observation.observed");
  });

  it("keeps the last inventory of an unavailable pod visible", async () => {
    h.query.currentData = [
      pod({ runtime_id: "fred-agents", observation: "unavailable", capabilities: [offer("ppt_filler")] }),
    ];
    await render();
    await selectPod();
    expect(container.textContent).toContain("organizationCapabilities.unavailableHint");
    expect(container.textContent).toContain("offer-ppt_filler");
  });

  it("says when an unavailable pod has never answered", async () => {
    h.query.currentData = [pod({ runtime_id: "fred-agents", observation: "unavailable", observed_at: null })];
    await render();
    await selectPod();
    expect(container.textContent).toContain("organizationCapabilities.neverAnsweredHint");
    expect(container.textContent).not.toContain("unavailableHint");
    expect(container.textContent).toContain("rework.admin.capabilities.empty");
  });

  it("reports a failed refresh without selecting the pod", async () => {
    h.query.currentData = [pod({ runtime_id: "fred-agents", capabilities: [offer("ppt_filler")] })];
    h.refreshFails = true;
    await render();
    await act(async () => button("discovery.refresh").click());
    expect(h.refreshes).toEqual([{ organizationId: "O1", runtimeId: "fred-agents" }]);
    expect(h.errors).toEqual(["rework.admin.capabilities.organizationCapabilities.refreshError:fred-agents"]);
    expect(container.textContent).not.toContain("offer-");
  });

  it("disables refresh for a pod disabled in configuration", async () => {
    h.query.currentData = [pod({ runtime_id: "fred-agents", enabled: false })];
    await render();
    expect(button("discovery.refresh").disabled).toBe(true);
  });

  it("shows only the load error when the inventory is refused", async () => {
    h.query = { currentData: undefined, isFetching: false, isError: true };
    await render();
    expect(container.textContent).toContain("rework.admin.capabilities.loadError");
    expect(container.querySelector("[data-activatable]")).toBeNull();
    expect(h.refreshes).toEqual([]);
  });
});
