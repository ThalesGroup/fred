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

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type {
  AgentMarketplaceState,
  ManagedAgentInstanceSummary,
  TeamPermission,
  TeamWithPermissions,
} from "../../../../slices/controlPlane/controlPlaneOpenApi";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

type ConfirmOptions = { title: string; message?: string; criticalAction?: boolean; onConfirm: () => void };

const h = vi.hoisted(() => ({
  team: undefined as unknown,
  instances: [] as unknown[],
  refetched: undefined as unknown[] | undefined,
  refetch: vi.fn(),
  patch: vi.fn(),
  publish: vi.fn(),
  unpublish: vi.fn(),
  dismiss: vi.fn(),
  confirm: vi.fn(),
  showError: vi.fn(),
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) => (opts ? `${key} ${JSON.stringify(opts)}` : key),
    i18n: { language: "en" },
  }),
}));

vi.mock("@shared/molecules/Toast/ToastProvider", () => ({
  useToast: () => ({ showSuccess: vi.fn(), showError: h.showError, showWarn: vi.fn() }),
}));

vi.mock("@shared/molecules/ConfirmationDialog/ConfirmationDialogProvider", () => ({
  useConfirmationDialog: () => ({ showConfirmationDialog: h.confirm }),
}));

vi.mock("../../../../hooks/useFrontendBootstrap.ts", () => ({
  useFrontendBootstrap: () => ({ activeTeam: { id: "personal" } }),
}));

vi.mock("../../../../hooks/useFrontendProperties.ts", () => ({
  useFrontendProperties: () => ({
    agentsNicknamePlural: "Agents",
    agentsNicknameSingular: "Agent",
    agentIconName: "smart_toy",
  }),
}));

vi.mock("../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useGetTeamQuery: () => ({ data: h.team }),
  useUsersByIdsQuery: () => ({ data: [] }),
  usePublishAgentMutation: () => [h.publish, { isLoading: false }],
  useUnpublishAgentMutation: () => [h.unpublish, { isLoading: false }],
  useDismissAgentMarketplaceRemovalMutation: () => [h.dismiss, { isLoading: false }],
}));

vi.mock("../../../../slices/controlPlane/controlPlaneOpenApi", () => ({
  useGetTeamAgentInstancesControlPlaneV1TeamsTeamIdAgentInstancesGetQuery: () => ({
    data: h.instances,
    isLoading: false,
    isError: false,
    refetch: h.refetch,
  }),
  useGetTeamAgentTemplatesControlPlaneV1TeamsTeamIdAgentTemplatesGetQuery: () => ({
    data: [{ template_id: "pod:basic", display_name: "Basic", source_runtime_id: "pod" }],
    isLoading: false,
    isError: false,
  }),
  usePatchTeamAgentInstanceControlPlaneV1TeamsTeamIdAgentInstancesAgentInstanceIdPatchMutation: () => [
    h.patch,
    { isLoading: false },
  ],
  usePatchTeamAgentInstanceWithAssetsControlPlaneV1TeamsTeamIdAgentInstancesAgentInstanceIdWithAssetsPatchMutation:
    () => [vi.fn(), { isLoading: false }],
  useDeleteTeamAgentInstanceControlPlaneV1TeamsTeamIdAgentInstancesAgentInstanceIdDeleteMutation: () => [vi.fn()],
  usePostAgentInstanceCopyControlPlaneV1TeamsTeamIdAgentInstancesAgentInstanceIdCopyPostMutation: () => [
    vi.fn(),
    { isLoading: false },
  ],
  usePostTeamAgentInstanceControlPlaneV1TeamsTeamIdAgentInstancesPostMutation: () => [vi.fn(), { isLoading: false }],
  usePostTeamAgentInstanceWithAssetsControlPlaneV1TeamsTeamIdAgentInstancesWithAssetsPostMutation: () => [
    vi.fn(),
    { isLoading: false },
  ],
}));

// The form is exercised elsewhere; here it only needs to submit a save.
vi.mock("./AgentFormModal/AgentFormModal.tsx", () => ({
  default: ({ isOpen, onSubmit }: { isOpen: boolean; onSubmit: (payload: unknown) => void }) =>
    isOpen ? (
      <button
        type="button"
        data-testid="save-agent"
        onClick={() =>
          onSubmit({
            templateId: "pod:basic",
            displayName: "Helper",
            role: "Helps",
            description: "",
            usageStatement: "",
            reasoningEnabled: false,
            reasoningDefaultOn: false,
            tuningFieldValues: {},
            selectedCapabilityIds: [],
            capabilityConfigValues: {},
            capabilityAssetFiles: {},
            templateHasCapabilities: false,
          })
        }
      />
    ) : null,
}));
vi.mock("./CopyAgentDialog/CopyAgentDialog.tsx", () => ({ default: () => null }));
vi.mock("./DuplicateAgentDialog/DuplicateAgentDialog.tsx", () => ({ default: () => null }));

import TeamAgentsPage from "./TeamAgentsPage";

const PUBLISHED: AgentMarketplaceState = {
  state: "published",
  version: 3,
  published_at: "2026-10-01T10:00:00Z",
  like_count: 1,
  import_count: 2,
};

const MEMBER: TeamPermission[] = ["can_read"];
const EDITOR: TeamPermission[] = [
  ...MEMBER,
  "can_update_agents",
  "can_publish_marketplace_agents",
  "can_unpublish_marketplace_agents",
];

function team(permissions: TeamPermission[], published = 1, quota = 5): TeamWithPermissions {
  return {
    id: "team-1",
    name: "Team",
    visibility: "public",
    permissions,
    marketplace: {
      agents_publishing_enabled: true,
      agents_publish_quota: quota,
      published_count: published,
    },
  };
}

function agent(over: Partial<ManagedAgentInstanceSummary> = {}): ManagedAgentInstanceSummary {
  return {
    agent_instance_id: "a1",
    team_id: "team-1",
    template_id: "pod:basic",
    display_name: "Helper",
    role: "Helps",
    status: "enabled",
    ...over,
  };
}

const resolved = (value: unknown = {}) => ({ unwrap: () => Promise.resolve(value) });
const rejected = (error: unknown) => ({ unwrap: () => Promise.reject(error) });

let container: HTMLDivElement;
let root: Root;

async function render() {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => {
    root.render(
      <MemoryRouter initialEntries={["/team/team-1/agents"]}>
        <Routes>
          <Route path="/team/:teamId/agents" element={<TeamAgentsPage />} />
        </Routes>
      </MemoryRouter>,
    );
  });
}

async function click(el: Element | null | undefined) {
  if (!el) throw new Error("element not found");
  await act(async () => {
    (el as HTMLElement).click();
  });
}

function menuItem(key: string): HTMLElement | undefined {
  return Array.from(document.querySelectorAll('[role="option"]')).find((el) => el.textContent?.includes(key)) as
    | HTMLElement
    | undefined;
}

async function openMenu() {
  await click(container.querySelector('[aria-label="rework.agentCard.moreMenu"]'));
}

const bar = () => container.querySelector('[aria-label="rework.agentMarketplace.barLabel"]');

const lastConfirm = (): ConfirmOptions => h.confirm.mock.lastCall?.[0] as ConfirmOptions;

beforeEach(() => {
  h.refetched = undefined;
  h.refetch.mockImplementation(() => Promise.resolve({ data: h.refetched ?? h.instances }));
  h.patch.mockImplementation(() => resolved());
  h.publish.mockImplementation(() => resolved());
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  document.body.innerHTML = "";
  vi.clearAllMocks();
});

describe("TeamAgentsPage marketplace", () => {
  it("offers Publish to an editor and no menu to a member", async () => {
    h.team = team(MEMBER);
    h.instances = [agent()];
    await render();
    expect(container.querySelector('[aria-label="rework.agentCard.moreMenu"]')).toBeNull();
    act(() => root.unmount());
    container.remove();
    document.body.innerHTML = "";

    h.team = team(EDITOR);
    await render();
    await openMenu();
    expect(menuItem("menu.publish")).toBeDefined();
  });

  it("shows no bar for an unpublished agent, to an editor or a member", async () => {
    h.team = team(EDITOR);
    h.instances = [agent()];
    await render();
    expect(bar()).toBeNull();
    act(() => root.unmount());
    container.remove();
    document.body.innerHTML = "";

    h.team = team(MEMBER);
    await render();
    expect(bar()).toBeNull();
  });

  it("shows the bar only on published cards in a mixed team", async () => {
    h.team = team(EDITOR);
    h.instances = [agent(), agent({ agent_instance_id: "a2", display_name: "Other", marketplace: PUBLISHED })];
    await render();
    expect(container.querySelectorAll('[aria-label="rework.agentMarketplace.barLabel"]')).toHaveLength(1);
  });

  it("shows no bar on any card when the team cannot publish", async () => {
    h.instances = [agent(), agent({ agent_instance_id: "a2", display_name: "Other", marketplace: PUBLISHED })];
    const off = team(EDITOR);
    h.team = { ...off, marketplace: { ...off.marketplace!, agents_publishing_enabled: false } };
    await render();
    expect(bar()).toBeNull();
    act(() => root.unmount());
    container.remove();
    document.body.innerHTML = "";

    h.team = { ...team(EDITOR), visibility: "private" };
    await render();
    expect(bar()).toBeNull();
  });

  it("gives a team admin who is not an editor a menu with Remove only", async () => {
    h.team = team(["can_read", "can_administer_members", "can_unpublish_marketplace_agents"]);
    h.instances = [agent({ marketplace: PUBLISHED })];
    await render();
    await openMenu();
    const options = Array.from(document.querySelectorAll('[role="option"]'));
    expect(options).toHaveLength(1);
    expect(options[0].textContent).toContain("menu.remove");
  });

  it("confirms the deactivation of a published agent as a critical action", async () => {
    h.team = team(EDITOR);
    h.instances = [agent({ marketplace: PUBLISHED })];
    await render();
    await openMenu();
    await click(menuItem("rework.agentCard.deactivate"));
    expect(h.patch).not.toHaveBeenCalled();
    expect(lastConfirm()).toMatchObject({
      criticalAction: true,
      title: "rework.agentMarketplace.deactivateDialog.title",
    });
    await act(async () => lastConfirm().onConfirm());
    expect(h.patch).toHaveBeenCalledWith(
      expect.objectContaining({ updateAgentInstanceRequest: { status: "disabled" } }),
    );
  });

  it("says the deletion of a published agent removes it from the marketplace", async () => {
    h.team = team(EDITOR);
    h.instances = [agent({ marketplace: PUBLISHED })];
    await render();
    await openMenu();
    await click(menuItem("rework.agentCard.delete"));
    expect(lastConfirm().criticalAction).toBe(true);
    expect(lastConfirm().message).toContain("rework.agentMarketplace.deleteRemoves");
  });

  it("proposes to update the marketplace after an editor saves a change, then opens the warning dialog", async () => {
    h.team = team(EDITOR);
    h.instances = [agent({ marketplace: PUBLISHED })];
    h.refetched = [agent({ marketplace: { ...PUBLISHED, modified: true } })];
    await render();
    await openMenu();
    await click(menuItem("rework.agentCard.edit"));
    await click(container.querySelector('[data-testid="save-agent"]'));

    const proposal = document.querySelector('[role="alertdialog"]');
    expect(proposal?.textContent).toContain("rework.agentMarketplace.proposal.saved");
    const update = Array.from(proposal?.querySelectorAll("button") ?? []).find((b) =>
      b.textContent?.includes("proposal.update"),
    );
    await click(update);
    expect(document.querySelector('[role="dialog"]')?.textContent).toContain("publishDialog.titleRepublish");
  });

  it("does not propose to republish after a save that changed nothing", async () => {
    h.team = team(EDITOR);
    h.instances = [agent({ marketplace: PUBLISHED })];
    await render();
    await openMenu();
    await click(menuItem("rework.agentCard.edit"));
    await click(container.querySelector('[data-testid="save-agent"]'));
    expect(document.querySelector('[role="alertdialog"]')).toBeNull();
  });

  it("proposes to publish again after reactivation, greyed when the quota is reached", async () => {
    h.team = team(EDITOR, 5, 5);
    h.instances = [
      agent({
        status: "disabled",
        marketplace: { ...PUBLISHED, state: "removed", removed_reason: "deactivated", removed_at: "2026-10-02" },
      }),
    ];
    await render();
    await openMenu();
    await click(menuItem("rework.agentCard.activate"));
    const proposal = document.querySelector('[role="alertdialog"]');
    expect(proposal?.textContent).toContain("rework.agentMarketplace.proposal.reactivated");
    expect(proposal?.textContent).toContain("rework.agentMarketplace.blocked.quotaReached");
    const publish = Array.from(proposal?.querySelectorAll("button") ?? []).find((b) =>
      b.textContent?.includes("proposal.publish"),
    ) as HTMLButtonElement;
    expect(publish.disabled).toBe(true);
  });

  it("refreshes the card and explains a stale version on publish", async () => {
    h.team = team(EDITOR);
    h.instances = [agent({ marketplace: { ...PUBLISHED, state: "dismissed" } })];
    h.publish.mockImplementation(() =>
      rejected({ status: 409, data: { detail: { code: "marketplace_version_conflict", message: "stale" } } }),
    );
    await render();
    await openMenu();
    await click(menuItem("menu.publish"));
    await click(document.querySelector('[role="dialog"] input[type="checkbox"]'));
    const confirm = Array.from(document.querySelectorAll('[role="dialog"] button')).find((b) =>
      b.textContent?.includes("publishDialog.confirm"),
    );
    await click(confirm);

    expect(h.publish).toHaveBeenCalledWith({
      teamId: "team-1",
      agentInstanceId: "a1",
      publishAgentRequest: { expected_version: 3 },
    });
    expect(h.refetch).toHaveBeenCalled();
    expect(h.showError).toHaveBeenCalledWith(
      expect.objectContaining({ detail: expect.stringContaining("marketplace_version_conflict") }),
    );
  });

  it("removes with the version the card shows", async () => {
    h.team = team(EDITOR);
    h.instances = [agent({ marketplace: PUBLISHED })];
    h.unpublish.mockImplementation(() => resolved());
    await render();
    await openMenu();
    await click(menuItem("menu.remove"));
    await act(async () => lastConfirm().onConfirm());
    expect(h.unpublish).toHaveBeenCalledWith({
      teamId: "team-1",
      agentInstanceId: "a1",
      unpublishAgentRequest: { expected_version: 3 },
    });
  });
});
