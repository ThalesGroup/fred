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

// The options form must never open editable on the declared defaults when the
// stored settings could not be read: saving it would overwrite them.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { CapabilityEnablementItem } from "../../../../../slices/controlPlane/controlPlaneOpenApi";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const h = vi.hoisted(() => ({
  readResult: null as null | { settings: Record<string, unknown> } | Error,
  saves: [] as unknown[],
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: { team?: string }) => (opts?.team ? `${key}:${opts.team}` : key),
    i18n: { language: "en" },
  }),
}));

vi.mock("../../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useEnableTeamCapabilityMutation: () => [vi.fn(), { isLoading: false }],
  useDisableTeamCapabilityMutation: () => [vi.fn(), { isLoading: false }],
  useSetCapabilityPersonalScopeMutation: () => [vi.fn(), { isLoading: false }],
  useLazyAdminTeamCapabilitySettingsQuery: () => [
    () => ({
      unwrap: async () => {
        if (h.readResult instanceof Error) throw h.readResult;
        return h.readResult;
      },
    }),
    { isLoading: false },
  ],
  useSetTeamCapabilitySettingsMutation: () => [
    (args: unknown) => ({ unwrap: async () => void h.saves.push(args) }),
    { isLoading: false },
  ],
  useCapabilityTeamSettingsMapQuery: () => ({ data: undefined, refetch: vi.fn() }),
}));

vi.mock("@shared/molecules/Toast/ToastProvider", () => ({
  useToast: () => ({ showSuccess: vi.fn(), showError: vi.fn(), showWarn: vi.fn(), showInfo: vi.fn() }),
}));

// The real renderer needs an RTK store; a probe exposing key and value is enough.
vi.mock("../../TeamAgentsPage/AgentFormModal/TuningFieldRenderer.tsx", () => ({
  TuningFieldRenderer: ({ field, value }: { field: { key: string }; value: unknown }) => (
    <input data-field={field.key} data-value={String(value)} readOnly />
  ),
}));

const { CapabilityTeamMatrixDrawer } = await import("./CapabilityTeamMatrixDrawer");

const JS_FIELD = { key: "allow_javascript", type: "boolean" as const, title: "js", default: false };

const capability: CapabilityEnablementItem = {
  id: "html_artifact",
  name: "cap.html_artifact",
  version: "1.0.0",
  icon: "extension",
  team_scope: "admin_gated",
  default_on: false,
  enabled_team_ids: ["t1"],
  team_settings_fields: [JS_FIELD],
};

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  h.saves = [];
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

async function openOptions() {
  await act(async () => {
    root.render(
      <CapabilityTeamMatrixDrawer
        capability={capability}
        allCapabilities={[capability]}
        teams={[{ id: "t1", name: "Alpha" }]}
        teamsLoading={false}
        teamsError={false}
        open
        onClose={vi.fn()}
      />,
    );
  });
  const button = container.querySelector<HTMLButtonElement>(
    '[aria-label="rework.admin.capabilities.matrix.editSettingsAria:Alpha"]',
  );
  expect(button).not.toBeNull();
  await act(async () => button!.click());
}

const submitButton = () => container.querySelector<HTMLButtonElement>('form button[type="submit"]');

describe("CapabilityTeamMatrixDrawer stored-settings read", () => {
  it("shows an error with retry and no editable defaults when the read fails", async () => {
    h.readResult = new Error("boom");
    await openOptions();

    expect(container.textContent).toContain("rework.admin.capabilities.matrix.settingsLoadError");
    expect(container.querySelector("[data-field]")).toBeNull();
    expect(submitButton()).toBeNull();
    // Even a forced submit (Enter key) must not write.
    await act(async () => container.querySelector("form")!.requestSubmit());
    expect(h.saves).toHaveLength(0);

    // Retry re-reads and, once it succeeds, seeds the stored value.
    h.readResult = { settings: { allow_javascript: true } };
    const retry = [...container.querySelectorAll<HTMLButtonElement>("form button")].find(
      (b) => b.textContent === "common.retry",
    );
    await act(async () => retry!.click());
    expect(container.querySelector("[data-field]")?.getAttribute("data-value")).toBe("true");
  });

  it("seeds the form with the stored values when the read succeeds", async () => {
    h.readResult = { settings: { allow_javascript: true } };
    await openOptions();

    expect(container.querySelector('[data-field="allow_javascript"]')?.getAttribute("data-value")).toBe("true");
    expect(submitButton()).not.toBeNull();
    await act(async () => submitButton()!.click());
    expect(h.saves).toEqual([
      {
        capabilityId: "html_artifact",
        teamId: "t1",
        setTeamCapabilitySettingsRequest: { settings: { allow_javascript: true } },
      },
    ]);
  });
});
