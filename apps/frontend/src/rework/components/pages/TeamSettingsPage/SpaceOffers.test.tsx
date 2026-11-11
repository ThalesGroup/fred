// @vitest-environment happy-dom
// Copyright Thales 2026 — SPDX-License-Identifier: Apache-2.0
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { beforeEach, afterEach, expect, it, vi } from "vitest";
import type {
  SpaceCapabilityPolicy,
  ReplaceSpaceCapabilityPolicyApiArg,
} from "../../../../slices/controlPlane/controlPlaneOpenApi";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const h = vi.hoisted(() => ({
  allowed: true,
  fail: false,
  policies: [] as SpaceCapabilityPolicy[],
  calls: [] as ReplaceSpaceCapabilityPolicyApiArg[],
  query: vi.fn(),
  refresh: vi.fn(),
}));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string, options?: { defaultValue?: string }) => options?.defaultValue ?? key }),
}));
vi.mock("@core/hooks/useSpaceAccess", () => ({ useSpaceAccess: () => ({ allowed: h.allowed, settled: true }) }));
vi.mock("../../../../slices/controlPlane/controlPlaneOpenApi", () => ({
  useSpaceCapabilityPoliciesQuery: (args: unknown, options: unknown) => {
    h.query(args, options);
    return { currentData: h.policies, refetch: h.refresh };
  },
  useReplaceSpaceCapabilityPolicyMutation: () => [
    (args: ReplaceSpaceCapabilityPolicyApiArg) => ({
      unwrap: async () => {
        h.calls.push(args);
        if (h.fail) throw { status: 409 };
      },
    }),
    { isLoading: false },
  ],
}));
import { SpaceOffers } from "./SpaceOffers";
let root: Root;
let container: HTMLDivElement;
beforeEach(() => {
  h.allowed = true;
  h.fail = false;
  h.calls = [];
  h.refresh.mockClear();
  h.query.mockClear();
  h.policies = [
    {
      source_id: "pod",
      origin: "pod",
      runtime_id: "pod",
      revision: 4,
      restricted: false,
      permitted_ids: [],
      source_enabled: true,
      reachable: true,
      offers: [
        {
          capability_id: "restricted-tool",
          advertised: true,
          parent_permitted: false,
          permitted: false,
          descriptor: {
            id: "restricted-tool",
            name: "graph",
            description: "Draw",
            icon: "tune",
            kind: "tool",
            version: "1",
          },
        },
        {
          capability_id: "tool",
          advertised: true,
          parent_permitted: true,
          permitted: true,
          descriptor: { id: "tool", name: "Tool", description: "Tool", icon: "tune", kind: "tool", version: "1" },
        },
      ],
    },
  ];
  container = document.createElement("div");
  document.body.append(container);
  root = createRoot(container);
});
afterEach(() => {
  act(() => root.unmount());
  container.remove();
});
const render = () => act(() => root.render(<SpaceOffers spaceId="project" />));
it("uses the direct Manage gate without requiring content Read", () => {
  h.allowed = false;
  render();
  expect(h.query).toHaveBeenLastCalledWith({ spaceId: "project" }, expect.objectContaining({ skip: true }));
  expect(container.textContent).toContain("rework.spaceMembers.forbidden");
  expect(container.querySelector("input")).toBeNull();
});
it("starts a local restriction from the effective parent ceiling and current revision", async () => {
  render();
  await act(async () => {
    container.querySelector<HTMLInputElement>("input")!.click();
  });
  expect(h.calls).toEqual([
    {
      spaceId: "project",
      sourceId: "pod",
      replaceSpaceCapabilityPolicy: { expected_revision: 4, restricted: true, permitted_ids: ["tool"] },
    },
  ]);
  expect(h.refresh).toHaveBeenCalledOnce();
});
it("saves explicit empty separately from inheritance and reports a stale edit", async () => {
  h.policies[0].restricted = true;
  h.policies[0].permitted_ids = ["restricted-tool"];
  h.fail = true;
  render();
  const button = Array.from(container.querySelectorAll("button")).find((b) => b.textContent?.includes("denyAll"))!;
  await act(async () => button.click());
  expect(h.calls[0].replaceSpaceCapabilityPolicy).toEqual({
    expected_revision: 4,
    restricted: true,
    permitted_ids: [],
  });
  expect(container.querySelector('[role="alert"]')?.textContent).toContain("conflict");
  expect(h.refresh).toHaveBeenCalledOnce();
});
it("distinguishes unavailable source from a saved refusal", () => {
  h.policies[0].reachable = false;
  h.policies[0].restricted = true;
  render();
  expect(container.textContent).toContain("source.unavailable");
  expect(container.textContent).toContain("rework.toolGovernance.denied");
  expect(container.textContent).toContain("graph");
});
