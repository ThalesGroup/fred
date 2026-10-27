// @vitest-environment happy-dom
// Copyright Thales 2026. Licensed under the Apache License, Version 2.0.

import { renderToStaticMarkup } from "react-dom/server";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { beforeEach, expect, it, vi } from "vitest";
import type { PlatformSkillInventory } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import { PlatformSkillsPanel } from "./PlatformSkillsPanel";

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
      opts?.defaultValue ?? `${key}${opts?.runtimes ? ":" + opts.runtimes : ""}`,
  }),
}));
vi.mock("../../../../../slices/controlPlane/controlPlaneOpenApi", () => ({
  useGetPlatformSkillsQuery: () => ({ ...state }),
  useSetPlatformSkillEnabledMutation: () => [state.mutate, { isLoading: false }],
}));
beforeEach(() => {
  state.data = { skills: [], unavailable_runtime_ids: [], unsupported_runtime_ids: [], disabled_skill_names: [] };
  state.isLoading = false;
  state.isError = false;
  state.isFetching = false;
  state.mutate
    .mockReset()
    .mockImplementation(() => ({ unwrap: async () => ({ name: "meeting-minutes", enabled: false }) }));
  state.refetch.mockReset().mockImplementation(async () => ({ data: state.data }));
});
const render = () => renderToStaticMarkup(<PlatformSkillsPanel />);

it("shows one global row with invocation modes and every advertising source", () => {
  state.data.skills = [
    {
      skill: {
        name: "meeting-minutes",
        description: "Prepare minutes",
        builtin: true,
        user_invocable: true,
        disable_model_invocation: false,
      },
      enabled: true,
      runtime_ids: ["pod-a", "pod-b"],
    },
  ];
  const html = render();
  expect(html).toContain("/meeting-minutes");
  expect(html).toContain("Prepare minutes");
  expect(html).toContain("rework.admin.skills.userInvocable");
  expect(html).toContain("rework.admin.skills.modelInvocable");
  expect(html).toContain("pod-a, pod-b");
  expect(html.match(/\/meeting-minutes/g)).toHaveLength(1);
});

it("reports unavailable and older sources instead of implying an empty healthy catalog", () => {
  state.data.unavailable_runtime_ids = ["offline"];
  state.data.unsupported_runtime_ids = ["legacy"];
  const html = render();
  expect(html).toContain("rework.admin.skills.unavailableSources:offline");
  expect(html).toContain("rework.admin.skills.unsupportedSources:legacy");
  expect(html).toContain("rework.admin.skills.empty");
});

it("separates loading, failed and empty catalogs", () => {
  expect(render()).toContain("rework.admin.skills.empty");
  state.isLoading = true;
  expect(render()).toContain("rework.admin.skills.loading");
  expect(render()).not.toContain("rework.admin.skills.empty");
  state.isLoading = false;
  state.isError = true;
  expect(render()).toContain("rework.admin.skills.loadError");
  expect(render()).not.toContain("rework.admin.skills.empty");
});

it("retains the active switch focus through saving and refresh while guarding rapid activation", async () => {
  state.data.skills = [
    {
      skill: { name: "meeting-minutes", description: "Prepare minutes", builtin: true },
      enabled: true,
      runtime_ids: ["pod-a"],
    },
    { skill: { name: "mermaid", description: "Diagrams", builtin: true }, enabled: true, runtime_ids: ["pod-a"] },
  ];
  let complete: () => void;
  let completeRefresh: () => void;
  state.mutate.mockImplementation(() => ({
    unwrap: () =>
      new Promise<void>((resolve) => {
        complete = resolve;
      }),
  }));
  state.refetch.mockImplementation(
    () =>
      new Promise((resolve) => {
        state.isFetching = true;
        completeRefresh = () => {
          state.isFetching = false;
          state.data = {
            ...state.data,
            skills: state.data.skills.map((entry) => ({ ...entry, enabled: entry.skill.name !== "meeting-minutes" })),
            disabled_skill_names: ["meeting-minutes"],
          };
          resolve({ data: state.data });
        };
      }),
  );
  const container = document.createElement("div");
  document.body.append(container);
  const root = createRoot(container);
  try {
    await act(async () => root.render(<PlatformSkillsPanel />));
    const checkbox = container.querySelector<HTMLInputElement>('input[type="checkbox"]')!;
    expect(checkbox.checked).toBe(true);
    await act(async () => {
      checkbox.focus();
      checkbox.click();
      checkbox.click();
    });
    expect(checkbox.disabled).toBe(false);
    expect(checkbox.getAttribute("aria-disabled")).toBe("true");
    expect(document.activeElement).toBe(checkbox);
    expect(checkbox.checked).toBe(true);
    expect(container.querySelectorAll<HTMLInputElement>('input[type="checkbox"]')[1].disabled).toBe(true);
    expect(state.mutate).toHaveBeenCalledOnce();
    expect(state.mutate).toHaveBeenCalledWith({
      skillName: "meeting-minutes",
      setPlatformSkillEnabledRequest: { enabled: false },
    });
    await act(async () => complete());
    await act(async () => root.render(<PlatformSkillsPanel />));
    expect(checkbox.disabled).toBe(false);
    expect(document.activeElement).toBe(checkbox);
    await act(async () => checkbox.click());
    expect(state.mutate).toHaveBeenCalledOnce();
    await act(async () => completeRefresh());
    expect(container.querySelector<HTMLInputElement>('input[type="checkbox"]')!.checked).toBe(false);
    expect(document.activeElement).toBe(checkbox);
  } finally {
    act(() => root.unmount());
    container.remove();
  }
});

it("keeps the current state and reports a refused write", async () => {
  state.data.skills = [
    {
      skill: { name: "meeting-minutes", description: "Minutes", builtin: true },
      enabled: true,
      runtime_ids: ["pod-a"],
    },
  ];
  state.mutate.mockImplementation(() => ({
    unwrap: async () => {
      throw { status: 409, data: { detail: "Source does not support policy" } };
    },
  }));
  const container = document.createElement("div");
  document.body.append(container);
  const root = createRoot(container);
  try {
    await act(async () => root.render(<PlatformSkillsPanel />));
    await act(async () => container.querySelector<HTMLInputElement>('input[type="checkbox"]')!.click());
    expect(container.querySelector<HTMLInputElement>('input[type="checkbox"]')!.checked).toBe(true);
    expect(container.querySelector('[role="alert"]')?.textContent).toBe("rework.admin.skills.saveUnsupported");
  } finally {
    act(() => root.unmount());
    container.remove();
  }
});

it("blocks new disables for unverified sources and still allows recovery during a total outage", async () => {
  state.data.skills = [
    { skill: { name: "mermaid", description: "Diagrams", builtin: true }, enabled: true, runtime_ids: ["pod-a"] },
  ];
  state.data.unavailable_runtime_ids = ["offline"];
  state.data.disabled_skill_names = ["meeting-minutes"];
  const container = document.createElement("div");
  document.body.append(container);
  const root = createRoot(container);
  try {
    await act(async () => root.render(<PlatformSkillsPanel />));
    expect(container.querySelector<HTMLInputElement>('input[type="checkbox"]')!.disabled).toBe(true);
    state.data.skills = [];
    await act(async () => root.render(<PlatformSkillsPanel />));
    const recovery = Array.from(container.querySelectorAll<HTMLButtonElement>("button")).find(
      (button) => button.textContent === "rework.admin.skills.restore",
    )!;
    expect(recovery.disabled).toBe(false);
    await act(async () => recovery.click());
    expect(state.mutate).toHaveBeenCalledWith({
      skillName: "meeting-minutes",
      setPlatformSkillEnabledRequest: { enabled: true },
    });
  } finally {
    act(() => root.unmount());
    container.remove();
  }
});
