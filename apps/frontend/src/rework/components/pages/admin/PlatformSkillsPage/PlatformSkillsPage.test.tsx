// @vitest-environment happy-dom
// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { act } from "react";
import { createRoot } from "react-dom/client";
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, expect, it, vi } from "vitest";
import type { PlatformSkillInventory } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import PlatformSkillsPage from "./PlatformSkillsPage";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const state = vi.hoisted(() => ({
  data: undefined as PlatformSkillInventory | undefined,
  isLoading: false,
  isError: false,
  isFetching: false,
  mutate: vi.fn(),
  refetch: vi.fn(),
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: { defaultValue?: string; runtimes?: string }) =>
      opts?.defaultValue ?? `${key}${opts?.runtimes ? `:${opts.runtimes}` : ""}`,
  }),
}));
vi.mock("../../../../../slices/controlPlane/controlPlaneOpenApi", () => ({
  useGetSkillsQuery: () => ({ ...state }),
  useSetSkillMutation: () => [state.mutate, { isLoading: false }],
}));

beforeEach(() => {
  state.data = {
    skills: [],
    disabled_skill_names: [],
    unavailable_runtime_ids: [],
    unsupported_runtime_ids: [],
    disabled_runtime_ids: [],
    custom_runtime_ids: [],
    conflicting_skill_names: [],
  };
  state.isLoading = false;
  state.isError = false;
  state.isFetching = false;
  state.mutate.mockReset().mockImplementation(() => ({ unwrap: async () => ({}) }));
  state.refetch.mockReset().mockImplementation(async () => ({ data: state.data }));
});

it("shows one global row for a packaged skill and its advertising runtimes", () => {
  state.data!.skills = [
    {
      skill: {
        name: "meeting-minutes",
        description: "Prepare minutes",
        argument_hint: null,
        builtin: true,
        user_invocable: true,
        disable_model_invocation: false,
      },
      enabled: true,
      runtime_ids: ["pod-a", "pod-b"],
    },
  ];
  const html = renderToStaticMarkup(<PlatformSkillsPage />);
  expect(html).toContain("/meeting-minutes");
  expect(html).toContain("Prepare minutes");
  expect(html).toContain("pod-a, pod-b");
  expect(html).toContain("rework.admin.skills.userInvocable");
  expect(html).toContain("rework.admin.skills.modelInvocable");
});

it("distinguishes unavailable, old, null and custom runtime configurations", () => {
  state.data!.unavailable_runtime_ids = ["offline"];
  state.data!.unsupported_runtime_ids = ["legacy"];
  state.data!.disabled_runtime_ids = ["null-config"];
  state.data!.custom_runtime_ids = ["mounted-directory"];
  state.data!.conflicting_skill_names = ["meeting-minutes"];
  const html = renderToStaticMarkup(<PlatformSkillsPage />);
  expect(html).toContain("rework.admin.skills.unavailableSources:offline");
  expect(html).toContain("rework.admin.skills.unsupportedSources:legacy");
  expect(html).toContain("rework.admin.skills.disabledSources:null-config");
  expect(html).toContain("rework.admin.skills.customSources:mounted-directory");
  expect(html).toContain("rework.admin.skills.conflictingMetadata");
  expect(html).toContain("rework.admin.skills.empty");
});

it("blocks disabling while a source is unverified but permits recovery offline", async () => {
  state.data!.skills = [
    {
      skill: {
        name: "graph",
        description: "Diagram",
        argument_hint: null,
        builtin: true,
        user_invocable: true,
        disable_model_invocation: false,
      },
      enabled: true,
      runtime_ids: ["pod-a"],
    },
  ];
  state.data!.unavailable_runtime_ids = ["offline"];
  state.data!.disabled_skill_names = ["meeting-minutes"];
  const container = document.createElement("div");
  document.body.append(container);
  const root = createRoot(container);
  try {
    await act(async () => root.render(<PlatformSkillsPage />));
    expect(container.querySelector<HTMLInputElement>('input[type="checkbox"]')?.disabled).toBe(true);
    const restore = Array.from(container.querySelectorAll("button")).find((button) =>
      button.textContent?.includes("rework.admin.skills.restore"),
    );
    expect(restore).toBeDefined();
    await act(async () => restore!.click());
    expect(state.mutate).toHaveBeenCalledWith({ name: "meeting-minutes", setSkillEnabled: { enabled: true } });
  } finally {
    act(() => root.unmount());
    container.remove();
  }
});
