// @vitest-environment happy-dom
// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import type {
  SpaceModels as SpaceModelsData,
  ReplaceSpaceModelPolicyApiArg,
} from "../../../../slices/controlPlane/controlPlaneOpenApi";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const h = vi.hoisted(() => ({
  data: undefined as SpaceModelsData | undefined,
  calls: [] as ReplaceSpaceModelPolicyApiArg[],
  refetch: vi.fn(),
}));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock("@core/hooks/useSpaceAccess", () => ({ useSpaceAccess: () => ({ allowed: true, settled: true }) }));
vi.mock("../../../../slices/controlPlane/controlPlaneOpenApi", () => ({
  useSpaceModelsQuery: () => ({ currentData: h.data, refetch: h.refetch }),
  useListAgentInstancesQuery: () => ({ currentData: { items: [] } }),
  useReplaceSpaceModelPolicyMutation: () => [
    (args: ReplaceSpaceModelPolicyApiArg) => ({
      unwrap: async () => {
        h.calls.push(args);
      },
    }),
    { isLoading: false },
  ],
}));
import { SpaceModels } from "./SpaceModels";
const a = { source_id: "source", upstream_model_id: "A" };
const b = { source_id: "source", upstream_model_id: "B" };
let root: Root;
let container: HTMLDivElement;
beforeEach(() => {
  h.calls = [];
  h.refetch.mockClear();
  h.data = {
    policy: { revision: 0, default: null, disabled: [], reasoning_default_on: [] },
    parent_permitted: [b],
    inherited_default: a,
    models: {
      default: a,
      recommendation: null,
      requires_reselection: false,
      reasoning_default_on: [a],
      options: {},
      policy: { organization_id: "org", revision: 2, permitted: [b], reasoning_enabled: [b], embedding_locked: false },
      offers: [a, b].map((key) => ({
        key,
        permitted: key === b,
        candidate: key === b,
        selectable: key === b,
        diagnostics: [],
        metadata: { chat: true, reasoning: true },
        observation: null,
      })),
    },
  };
  container = document.createElement("div");
  document.body.append(container);
  root = createRoot(container);
});
afterEach(() => {
  act(() => root.unmount());
  container.remove();
});
const chooseAllowedDefault = async () => {
  await act(async () => root.render(<SpaceModels spaceId="project" />));
  const button = Array.from(container.querySelectorAll("button")).find(
    (item) => item.textContent === "rework.teamSettings.routing.setDefault",
  )!;
  expect(button.disabled).toBe(false);
  await act(async () => button.click());
};
it("does not materialize a revoked inherited reasoning preference when choosing the first project default", async () => {
  await chooseAllowedDefault();
  expect(h.calls).toEqual([
    {
      spaceId: "project",
      replaceSpaceModelPolicy: {
        expected_revision: 0,
        default: b,
        disabled: [],
        reasoning_default_on: [],
      },
    },
  ]);
  expect(h.refetch).toHaveBeenCalledOnce();
});
it("preserves an already-local revoked reasoning preference when changing an independent default", async () => {
  h.data!.policy = { revision: 1, default: a, disabled: [], reasoning_default_on: [a] };
  await chooseAllowedDefault();
  expect(h.calls[0].replaceSpaceModelPolicy.reasoning_default_on).toEqual([a]);
  expect(h.calls[0].replaceSpaceModelPolicy.default).toEqual(b);
});
