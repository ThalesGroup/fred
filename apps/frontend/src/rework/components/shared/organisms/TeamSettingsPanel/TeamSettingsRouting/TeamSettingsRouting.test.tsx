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

// The team's Models section: one row per model, the default's badge and its
// locked enable switch, the reasoning switch only where reasoning can run, the
// read-only view, and the disable confirmation that writes nothing on cancel.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";
import type {
  AvailableModelProfileList,
  DisableImpact,
  TeamRoutingPolicy,
  TeamWithPermissions,
} from "../../../../../../slices/controlPlane/controlPlaneOpenApi";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const h = vi.hoisted(() => ({
  policy: undefined as TeamRoutingPolicy | undefined,
  availableModels: undefined as AvailableModelProfileList | undefined,
  impact: { agents: [] } as DisableImpact,
  fetching: false,
  readError: false,
  refetch: vi.fn(),
  showWarn: vi.fn(),
  updateRoutingPolicy: vi.fn((_: unknown) => ({ unwrap: () => Promise.resolve() as Promise<unknown> })),
  fetchDisableImpact: vi.fn((_: unknown, __?: boolean) => ({ unwrap: () => Promise.resolve(h.impact) })),
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock("@shared/molecules/Toast/ToastProvider", () => ({ useToast: () => ({ showWarn: h.showWarn }) }));

vi.mock("../../../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useTeamRoutingPolicyQuery: () => ({
    data: h.policy,
    isLoading: false,
    isFetching: h.fetching,
    isError: h.readError,
    refetch: h.refetch,
  }),
  useAvailableModelProfilesQuery: () => ({ data: h.availableModels, isLoading: false, isFetching: false }),
  useUpdateTeamRoutingPolicyMutation: () => [h.updateRoutingPolicy, { isLoading: false }],
  useLazyDisableImpactQuery: () => [h.fetchDisableImpact],
}));

import TeamSettingsRouting from "./TeamSettingsRouting.tsx";

let container: HTMLDivElement;
let root: Root;

function render(canWrite: boolean) {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => {
    root.render(<TeamSettingsRouting team={TEAM} canWrite={canWrite} />);
  });
}

afterEach(() => {
  act(() => {
    root.unmount();
  });
  container.remove();
  h.updateRoutingPolicy.mockClear();
  h.fetchDisableImpact.mockClear();
  h.refetch.mockClear();
  h.showWarn.mockClear();
  h.fetching = false;
  h.readError = false;
  h.policy = undefined;
  h.availableModels = undefined;
  h.impact = { agents: [] };
});

const TEAM = { id: "team-1", name: "Team One", is_member: true, admins: [], permissions: [] } as TeamWithPermissions;
const MISTRAL = "model__mistral__mistral-small";
const GPT = "model__openai__gpt-5";

const MODELS: AvailableModelProfileList = {
  profiles: [
    { profile_id: "chat.gpt5", capability_id: GPT, name: "gpt-5", display_name: "GPT-5", reasoning_available: true },
    {
      profile_id: "chat.gpt5.alt",
      capability_id: GPT,
      name: "gpt-5",
      display_name: "GPT-5",
      reasoning_available: true,
    },
    { profile_id: "chat.mistral", capability_id: MISTRAL, name: "mistral-small", reasoning_available: false },
  ],
  effective_default_profile_id: "chat.mistral",
};

function policy(patch: Partial<TeamRoutingPolicy> = {}): TeamRoutingPolicy {
  return { team_id: "team-1", version: 1, chat_default_profile_id: null, ...patch };
}

function tiles(): HTMLLIElement[] {
  return Array.from(container.querySelectorAll("li"));
}

function tile(name: string): HTMLLIElement {
  const found = tiles().find((li) => li.textContent?.includes(name));
  if (!found) throw new Error(`no tile for ${name}`);
  return found;
}

function enableSwitch(name: string): HTMLInputElement {
  return tile(name).querySelector('input[aria-label="rework.teamSettings.routing.enabledLabel"]') as HTMLInputElement;
}

function reasoningSwitch(name: string): HTMLInputElement | null {
  return tile(name).querySelector('input[aria-label="rework.teamSettings.routing.reasoningDefaultLabel"]');
}

function defaultButton(name: string): HTMLButtonElement {
  return tile(name).querySelector("button") as HTMLButtonElement;
}

function dialogButton(label: string): HTMLButtonElement | undefined {
  return Array.from(document.body.querySelectorAll('[role="alertdialog"] button')).find(
    (button) => button.textContent === label,
  ) as HTMLButtonElement | undefined;
}

async function flush() {
  await act(async () => {
    await Promise.resolve();
  });
}

describe("TeamSettingsRouting", () => {
  it("lists one row per model, the effective default badged and the others offering Set as default", () => {
    h.policy = policy();
    h.availableModels = MODELS;
    render(true);

    expect(tiles()).toHaveLength(2);
    expect(defaultButton("Mistral Small").textContent).toContain("rework.teamSettings.routing.isDefault");
    expect(defaultButton("Mistral Small").disabled).toBe(true);
    expect(defaultButton("GPT-5").textContent).toBe("rework.teamSettings.routing.setDefault");
    expect(defaultButton("GPT-5").disabled).toBe(false);
  });

  it("disables the default model's enable switch", () => {
    h.policy = policy({ chat_default_profile_id: "chat.gpt5" });
    h.availableModels = MODELS;
    render(true);

    expect(enableSwitch("GPT-5").disabled).toBe(true);
    expect(enableSwitch("Mistral Small").disabled).toBe(false);
  });

  it("shows the reasoning switch only for a model whose reasoning the platform enabled", () => {
    h.policy = policy({ reasoning_default_off_model_ids: [GPT] });
    h.availableModels = MODELS;
    render(true);

    expect(reasoningSwitch("GPT-5")?.checked).toBe(false);
    expect(reasoningSwitch("Mistral Small")).toBeNull();
  });

  it("lists a team-disabled model unchecked", () => {
    h.policy = policy({ disabled_model_ids: [GPT] });
    h.availableModels = MODELS;
    render(true);

    expect(enableSwitch("GPT-5").checked).toBe(false);
    expect(enableSwitch("Mistral Small").checked).toBe(true);
  });

  it("is read-only for a team editor or analyst", () => {
    h.policy = policy();
    h.availableModels = MODELS;
    render(false);

    expect(container.textContent).toContain("rework.teamSettings.routing.readOnly");
    container.querySelectorAll("input").forEach((input) => expect(input.disabled).toBe(true));
    container.querySelectorAll("button").forEach((button) => expect(button.disabled).toBe(true));
  });

  it("is editable for a team admin, and Set as default saves the whole policy", () => {
    h.policy = policy({ disabled_model_ids: [], reasoning_default_off_model_ids: [GPT] });
    h.availableModels = MODELS;
    render(true);

    act(() => defaultButton("GPT-5").click());
    expect(h.updateRoutingPolicy).toHaveBeenCalledWith({
      teamId: "team-1",
      updateTeamRoutingPolicyRequest: {
        chat_default_profile_id: "chat.gpt5",
        disabled_model_ids: [],
        reasoning_default_off_model_ids: [GPT],
        expected_version: 1,
      },
    });
  });

  it("keeps the stored default when only the reasoning default changes", () => {
    h.policy = policy();
    h.availableModels = MODELS;
    render(true);

    act(() => reasoningSwitch("GPT-5")!.click());
    expect(h.updateRoutingPolicy).toHaveBeenCalledWith({
      teamId: "team-1",
      updateTeamRoutingPolicyRequest: {
        chat_default_profile_id: null,
        disabled_model_ids: [],
        reasoning_default_off_model_ids: [GPT],
        expected_version: 1,
      },
    });
  });

  it("lists the recommending agents and the conversation fallback, then saves on confirm", async () => {
    h.policy = policy();
    h.availableModels = MODELS;
    h.impact = { agents: [{ agent_instance_id: "x", display_name: "Agent X" }] };
    render(true);

    act(() => enableSwitch("GPT-5").click());
    await flush();

    expect(h.fetchDisableImpact).toHaveBeenCalledWith({ teamId: "team-1", capabilityId: GPT }, false);
    const dialog = document.body.querySelector('[role="alertdialog"]');
    expect(dialog?.textContent).toContain("Agent X");
    expect(dialog?.textContent).toContain("rework.teamSettings.routing.disableDialog.conversations");
    expect(h.updateRoutingPolicy).not.toHaveBeenCalled();

    act(() => dialogButton("rework.teamSettings.routing.disableDialog.confirm")!.click());
    await flush();
    expect(h.updateRoutingPolicy).toHaveBeenCalledWith({
      teamId: "team-1",
      updateTeamRoutingPolicyRequest: {
        chat_default_profile_id: null,
        disabled_model_ids: [GPT],
        reasoning_default_off_model_ids: [],
        expected_version: 1,
      },
    });
  });

  it("writes nothing when the disable dialog is cancelled", async () => {
    h.policy = policy();
    h.availableModels = MODELS;
    render(true);

    act(() => enableSwitch("GPT-5").click());
    await flush();
    act(() => dialogButton("common.cancel")!.click());
    await flush();

    expect(document.body.querySelector('[role="alertdialog"]')).toBeNull();
    expect(h.updateRoutingPolicy).not.toHaveBeenCalled();
  });

  it("re-enables a disabled model without a dialog", () => {
    h.policy = policy({ disabled_model_ids: [GPT] });
    h.availableModels = MODELS;
    render(true);

    act(() => enableSwitch("GPT-5").click());
    expect(h.fetchDisableImpact).not.toHaveBeenCalled();
    expect(h.updateRoutingPolicy).toHaveBeenCalledWith(
      expect.objectContaining({ updateTeamRoutingPolicyRequest: expect.objectContaining({ disabled_model_ids: [] }) }),
    );
  });

  it("flags a stored default the team can no longer use", () => {
    h.policy = policy({ chat_default_profile_id: "chat.revoked" });
    h.availableModels = MODELS;
    render(true);

    expect(container.textContent).toContain("rework.teamSettings.routing.defaultUnavailable");
  });

  it("locks every write while the policy is being refetched", () => {
    h.policy = policy();
    h.availableModels = MODELS;
    h.fetching = true;
    render(true);

    container.querySelectorAll("input").forEach((input) => expect(input.disabled).toBe(true));
    container.querySelectorAll("button").forEach((button) => expect(button.disabled).toBe(true));
  });

  it("reloads and warns, without an error line, when another admin saved meanwhile", async () => {
    h.policy = policy();
    h.availableModels = MODELS;
    h.updateRoutingPolicy.mockImplementationOnce(() => ({
      unwrap: () => Promise.reject({ status: 409, data: { detail: "changed" } }),
    }));
    render(true);

    act(() => defaultButton("GPT-5").click());
    await flush();

    expect(h.refetch).toHaveBeenCalled();
    expect(h.showWarn).toHaveBeenCalledWith(
      expect.objectContaining({ summary: "rework.teamSettings.routing.conflict" }),
    );
    expect(container.querySelector('[role="alert"]')).toBeNull();
  });

  it("shows a load error, not the empty state, when the policy cannot be read", () => {
    h.policy = undefined;
    h.availableModels = { profiles: [] };
    h.readError = true;
    render(true);

    expect(container.textContent).toContain("rework.teamSettings.routing.loadError");
    expect(container.textContent).not.toContain("rework.teamSettings.routing.emptyState");
    expect(container.querySelectorAll("input, button")).toHaveLength(0);
  });

  it("explains the default's locked switch in visible text tied to it, with no nested labels", () => {
    h.policy = policy();
    h.availableModels = MODELS;
    render(true);

    const helper = tile("Mistral Small").querySelector("[id]") as HTMLElement;
    expect(helper.textContent).toBe("rework.teamSettings.routing.defaultCannotBeDisabled");
    expect(enableSwitch("Mistral Small").getAttribute("aria-describedby")).toBe(helper.id);
    expect(container.querySelector("label label")).toBeNull();
  });

  it("badges the default once when it is a second profile of a model", () => {
    h.policy = policy({ chat_default_profile_id: "chat.gpt5.alt" });
    h.availableModels = MODELS;
    render(true);

    expect(tiles()).toHaveLength(2);
    expect(defaultButton("GPT-5").textContent).toContain("rework.teamSettings.routing.isDefault");
    expect(container.textContent).not.toContain("rework.teamSettings.routing.defaultUnavailable");
  });

  it("shows the empty state when the platform allows no model", () => {
    h.policy = policy();
    h.availableModels = { profiles: [] };
    render(true);

    expect(container.textContent).toContain("rework.teamSettings.routing.emptyState");
  });
});
