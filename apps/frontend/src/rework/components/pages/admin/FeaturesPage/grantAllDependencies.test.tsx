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

// The "Enable all" flow of the per-team drawer, and the organization agent
// default-on switch of FeaturesPage.
//
// The drawer bug this covers is a SEQUENCE, not a snapshot: enabling an agent
// template while its `default_capability_ids` were not usable by that team
// used to fire the write immediately, handing the team a template it could not
// use. A static render cannot show the ordering that fixes it, so
// this drives real clicks through `createRoot` + `act`, the repo's idiom (no
// @testing-library/react here).
//
// What is asserted, in order of what would actually break in production:
//   1. the bare write never leaves the client — the dialog intercepts it;
//   2. on confirm, the DEPENDENCY is written before the TEMPLATE (the ordering
//      is the whole guarantee — there is no transaction, so a failure must
//      leave "dependency on, template off", never the inverse);
//   3. a failing dependency aborts before the template.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { CapabilityEnablementItem } from "../../../../../slices/legacyControlPlane/legacyControlPlaneOpenApi";

import type {
  AgentEnablement,
  SetOrganizationAgentDefaultApiArg,
} from "../../../../../slices/controlPlane/controlPlaneOpenApi";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const h = vi.hoisted(() => ({
  organizationAgents: [] as AgentEnablement[],
  organizationWrites: [] as SetOrganizationAgentDefaultApiArg[],
  /** Every drawer write, in call order — the sequence under test. */
  calls: [] as Array<{ id: string; on: boolean }>,
  /** Capability ids whose write should reject. */
  failFor: new Set<string>(),
  errors: [] as string[],
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: { defaultValue?: string }) => opts?.defaultValue ?? key,
    i18n: { language: "en" },
  }),
}));

vi.mock("../../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useOrganizationAgentsQuery: () => ({ currentData: h.organizationAgents, isLoading: false, isError: false }),
  useSetOrganizationAgentDefaultMutation: () => [
    (args: SetOrganizationAgentDefaultApiArg) => ({
      unwrap: async () => {
        h.organizationWrites.push(args);
        if (h.failFor.has(args.agentId)) throw new Error("boom");
        return { capability_id: args.agentId, default_on: args.setDefaultOnRequest.default_on };
      },
    }),
    { isLoading: false },
  ],
  useSetOrganizationCapabilityDefaultMutation: () => [vi.fn(), { isLoading: false }],
  useOrganizationCapabilitiesQuery: () => ({ data: undefined }),
  useLazyOrganizationCapabilityRevokeImpactQuery: () => [vi.fn(), { data: undefined, isFetching: false }],
}));

vi.mock("../../../../../slices/legacyControlPlane/legacyControlPlaneApiEnhancements", () => ({
  useAdminCapabilitiesQuery: () => ({ data: undefined, isLoading: false, isError: false }),
  // The drawer's writes land in the same `h.calls` log, so the team and
  // personal paths assert ordering the same way.
  useEnableTeamCapabilityMutation: () => [
    (args: { capabilityId: string; teamId: string }) => ({
      unwrap: async () => {
        h.calls.push({ id: args.capabilityId, on: true });
        if (h.failFor.has(args.capabilityId)) throw new Error("boom");
        return {};
      },
    }),
    { isLoading: false },
  ],
  useDisableTeamCapabilityMutation: () => [vi.fn(), { isLoading: false }],
  useSetCapabilityPersonalScopeMutation: () => [
    (args: { capabilityId: string }) => ({
      unwrap: async () => {
        h.calls.push({ id: args.capabilityId, on: true });
        if (h.failFor.has(args.capabilityId)) throw new Error("boom");
        return { suspended_instances: 0 };
      },
    }),
    { isLoading: false },
  ],
}));

vi.mock("@shared/molecules/Toast/ToastProvider", () => ({
  useToast: () => ({
    showSuccess: vi.fn(),
    showWarn: vi.fn(),
    showInfo: vi.fn(),
    showError: (arg: { summary?: string }) => h.errors.push(arg?.summary ?? ""),
  }),
}));

// The page reads the applications deployment gate on every render, and that
// hook goes through RTK Query. Left unmocked it needs a store this suite has no
// reason to build. It stays off, which is both the deployment default and
// irrelevant to the agent-only flow below.
vi.mock("@hooks/useFrontendFeatureFlag.ts", () => ({
  useFrontendFeatureFlag: () => ({ enabled: false, isLoading: false }),
}));

const { default: FeaturesPage } = await import("./FeaturesPage");
const { CapabilityTeamMatrixDrawer } = await import("./CapabilityTeamMatrixDrawer");

const cap = (over: Partial<CapabilityEnablementItem>): CapabilityEnablementItem =>
  ({
    id: "x",
    version: "1.0.0",
    name: "cap.x",
    description: "",
    icon: "tune",
    default_on: false,
    kind: "tool",
    enabled_team_ids: [],
    disabled_team_ids: [],
    team_settings_fields: [],
    ...over,
  }) as CapabilityEnablementItem;

const DEP = cap({ id: "platform_postgres" });

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  h.organizationAgents = [];
  h.organizationWrites = [];
  h.calls = [];
  h.failFor = new Set();
  h.errors = [];
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

const defaultOnSwitch = () => container.querySelector('input[type="checkbox"]') as HTMLInputElement | null;

// ConfirmationDialog renders through `<Portal id="modal-portal">`, i.e. OUTSIDE
// the test container — so the dialog is queried from the document, not from
// `container`, and `dialog()` is what the "is it open" assertions read.
const dialog = () => document.querySelector('[role="alertdialog"]');
const dialogButton = (keySuffix: string) =>
  Array.from(document.querySelectorAll('[role="alertdialog"] button')).find((b) =>
    b.textContent?.includes(`grantAllConfirm.${keySuffix}`),
  ) as HTMLElement | undefined;

const clickConfirm = async () => {
  const confirm = dialogButton("confirm");
  expect(confirm, "the Enable all button should be in the dialog").toBeTruthy();
  await act(async () => confirm!.click());
};

// The drawer's two paths share one ordering guarantee, but each grants at its
// OWN scope: a team row enables the dependency for that team, the personal
// class row sets its personal scope.
describe("CapabilityTeamMatrixDrawer grant-all (#2470)", () => {
  const AGENT_DEP = cap({ id: "platform_ops", kind: "agent", default_capability_ids: ["platform_postgres"] });

  function renderDrawer(over: Partial<Parameters<typeof CapabilityTeamMatrixDrawer>[0]> = {}) {
    act(() =>
      root.render(
        <CapabilityTeamMatrixDrawer
          capability={AGENT_DEP}
          allCapabilities={[AGENT_DEP, DEP]}
          teams={[{ id: "nb", name: "Nightly Build" }]}
          teamsLoading={false}
          teamsError={false}
          open
          onClose={() => {}}
          {...over}
        />,
      ),
    );
  }

  /** The "Enable" segment of a row — CHOICES order is disable/default/enable. */
  const enableButton = (personal: boolean) => {
    const rows = Array.from(container.querySelectorAll("li"));
    const row = rows.find((r) =>
      personal ? r.className.includes("personalRow") : !r.className.includes("personalRow"),
    );
    return row!.querySelectorAll("button")[2] as HTMLElement;
  };

  it("team row: opens the dialog instead of writing, then grants dependency before template", async () => {
    renderDrawer();
    act(() => enableButton(false).click());
    expect(h.calls).toEqual([]);
    expect(dialog()?.textContent).toContain("grantAllConfirm.messageTeam");

    await clickConfirm();
    expect(h.calls.map((c) => c.id)).toEqual(["platform_postgres", "platform_ops"]);
  });

  it("team row: a failing dependency aborts before the template", async () => {
    h.failFor = new Set(["platform_postgres"]);
    renderDrawer();
    act(() => enableButton(false).click());
    await clickConfirm();

    expect(h.calls.map((c) => c.id)).toEqual(["platform_postgres"]);
    expect(h.errors.join()).toContain("grantAllConfirm.depFailed");
  });

  it("personal class row: grants dependency personal scope before the template", async () => {
    renderDrawer();
    act(() => enableButton(true).click());
    expect(h.calls).toEqual([]);
    expect(dialog()?.textContent).toContain("grantAllConfirm.messagePersonal");

    await clickConfirm();
    expect(h.calls.map((c) => c.id)).toEqual(["platform_postgres", "platform_ops"]);
  });

  it("personal class row: a failing dependency aborts before the template", async () => {
    h.failFor = new Set(["platform_postgres"]);
    renderDrawer();
    act(() => enableButton(true).click());
    await clickConfirm();

    expect(h.calls.map((c) => c.id)).toEqual(["platform_postgres"]);
  });

  it("warns that the settings form still has to be saved when the template carries fields", () => {
    // `startEnable` only OPENS the form in that case, so "Enable all" must not
    // claim it finished the job.
    renderDrawer({
      capability: cap({
        ...AGENT_DEP,
        team_settings_fields: [{ key: "token", type: "string", required: false, title: "Token" }],
      }),
    });
    act(() => enableButton(false).click());
    expect(dialog()?.textContent).toContain("grantAllConfirm.thenSettingsForm");
  });

  it("no dialog at all once the dependency is usable by that team", async () => {
    renderDrawer({ allCapabilities: [AGENT_DEP, cap({ id: "platform_postgres", enabled_team_ids: ["nb"] })] });
    await act(async () => enableButton(false).click());

    expect(dialog()).toBeNull();
    expect(h.calls.map((c) => c.id)).toEqual(["platform_ops"]);
  });
});

describe("organization agent default", () => {
  const ralph = (on: boolean): AgentEnablement => ({
    id: "template-o1",
    runtime_id: "native",
    source_id: "ralph",
    name: "Ralph",
    description: "Hello world",
    version: "1",
    public_version: "0.1.0",
    icon: "smart_toy",
    kind: "agent",
    team_scope: "admin_gated",
    default_on: on,
    default_capability_ids: [],
  });
  function renderOrganization(on: boolean) {
    h.organizationAgents = [ralph(on)];
    act(() => root.render(<FeaturesPage organizationId="O1" />));
  }
  const offButton = (suffix: string) =>
    Array.from(document.querySelectorAll('[role="alertdialog"] button')).find((button) =>
      button.textContent?.includes(`defaultOffConfirm.${suffix}`),
    ) as HTMLElement;

  it("uses the organization mutation and waits for server data to change the switch", async () => {
    renderOrganization(false);
    expect(container.querySelectorAll('[role="radio"]').length).toBe(4);
    await act(async () => defaultOnSwitch()!.click());
    expect(h.organizationWrites).toEqual([
      {
        organizationId: "O1",
        agentId: "template-o1",
        setDefaultOnRequest: { default_on: true },
      },
    ]);
    expect(h.calls).toEqual([]);
    expect(defaultOnSwitch()!.checked).toBe(false);
    renderOrganization(true);
    expect(defaultOnSwitch()!.checked).toBe(true);
  });

  it("preserves cancellation", async () => {
    renderOrganization(true);
    act(() => defaultOnSwitch()!.click());
    expect(dialog()?.textContent).toContain("defaultOffConfirm.organizationMessage");
    act(() => offButton("cancel").click());
    expect(h.organizationWrites).toEqual([]);
    act(() => defaultOnSwitch()!.click());
    await act(async () => offButton("confirm").click());
    expect(h.organizationWrites[0].setDefaultOnRequest.default_on).toBe(false);
    expect(h.calls).toEqual([]);
  });

  it("leaves the server state unchanged and reports a rejected write", async () => {
    renderOrganization(false);
    h.failFor.add("template-o1");
    await act(async () => defaultOnSwitch()!.click());
    expect(defaultOnSwitch()!.checked).toBe(false);
    expect(h.errors).toContain("rework.admin.capabilities.defaultToggleError");
  });
});
