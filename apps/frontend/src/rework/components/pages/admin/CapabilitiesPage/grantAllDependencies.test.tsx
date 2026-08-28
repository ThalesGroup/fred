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

// #2470 — the "Enable all" flow on the platform-wide default-on switch.
//
// The bug this covers is a SEQUENCE, not a snapshot: flipping an agent template
// default-on while its `default_capability_ids` were not default-on themselves
// used to fire the write immediately, handing every team a template none of
// them could use. A static render cannot show the ordering that fixes it, so
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
import type { CapabilityEnablementItem } from "../../../../../slices/controlPlane/controlPlaneOpenApi";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const h = vi.hoisted(() => ({
  items: [] as CapabilityEnablementItem[],
  /** Every default-on write, in call order — the sequence under test. */
  calls: [] as Array<{ id: string; on: boolean }>,
  /** Capability ids whose default-on write should reject. */
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
  useAdminCapabilitiesQuery: () => ({ data: { items: h.items }, isLoading: false, isError: false }),
  useListAllTeamsQuery: () => ({ data: [], isLoading: false, isError: false }),
  useSetCapabilityDefaultOnMutation: () => [
    (args: { capabilityId: string; setCapabilityDefaultOnRequest: { default_on: boolean } }) => ({
      unwrap: async () => {
        h.calls.push({ id: args.capabilityId, on: args.setCapabilityDefaultOnRequest.default_on });
        if (h.failFor.has(args.capabilityId)) throw new Error("boom");
        return { suspended_instances: 0 };
      },
    }),
    { isLoading: false },
  ],
  useSetModelReasoningMutation: () => [vi.fn(), { isLoading: false }],
  useLazyCapabilityRevokeImpactQuery: () => [vi.fn(), { data: undefined, isFetching: false }],
  // The drawer's own writes land in the same `h.calls` log, so the team and
  // personal paths assert ordering exactly like the platform one does.
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
  usePlatformModelBindingQuery: () => ({
    data: { model_capability: "chat", binding: null },
    isLoading: false,
    isError: false,
  }),
  useSetPlatformModelBindingMutation: () => [vi.fn(), { isLoading: false }],
  useDeletePlatformModelBindingMutation: () => [vi.fn(), { isLoading: false }],
}));

vi.mock("@shared/molecules/Toast/ToastProvider", () => ({
  useToast: () => ({
    showSuccess: vi.fn(),
    showWarn: vi.fn(),
    showInfo: vi.fn(),
    showError: (arg: { summary?: string }) => h.errors.push(arg?.summary ?? ""),
  }),
}));

vi.mock("./SuspendedInstancesDrawer", () => ({ SuspendedInstancesDrawer: () => null }));
vi.mock("./PlatformModelBindingsPanel/PlatformModelBindingsPanel", () => ({
  PlatformModelBindingsPanel: () => null,
}));

const { default: CapabilitiesPage } = await import("./CapabilitiesPage");
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

const AGENT = cap({ id: "platform_ops", kind: "agent", default_capability_ids: ["platform_postgres"] });
const DEP = cap({ id: "platform_postgres" });

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  h.items = [];
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

/** Render the page and switch to the Agents tab, where `kind="agent"` rows live. */
function renderAgentsTab(items: CapabilityEnablementItem[]) {
  h.items = items;
  act(() => root.render(<CapabilitiesPage />));
  // KIND_FILTERS order is [tool, agent, model]; the tab strip is the first radio group.
  const tabs = container.querySelectorAll('[role="radio"]');
  act(() => (tabs[1] as HTMLElement).click());
}

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

describe("CapabilitiesPage default-on grant-all (#2470)", () => {
  it("intercepts the bare write and opens the confirmation instead", () => {
    renderAgentsTab([AGENT, DEP]);
    act(() => defaultOnSwitch()!.click());

    // The whole point: nothing reached the wire.
    expect(h.calls).toEqual([]);
    expect(dialog()?.textContent).toContain("grantAllConfirm.title");
  });

  it("writes the dependency BEFORE the template on confirm", async () => {
    renderAgentsTab([AGENT, DEP]);
    act(() => defaultOnSwitch()!.click());
    await clickConfirm();

    expect(h.calls).toEqual([
      { id: "platform_postgres", on: true },
      { id: "platform_ops", on: true },
    ]);
  });

  it("aborts before the template when a dependency fails", async () => {
    h.failFor = new Set(["platform_postgres"]);
    renderAgentsTab([AGENT, DEP]);
    act(() => defaultOnSwitch()!.click());
    await clickConfirm();

    // "dependency attempted, template untouched" — never a template granted
    // without what it needs, which is the state #2470 exists to prevent.
    expect(h.calls.map((c) => c.id)).toEqual(["platform_postgres"]);
    expect(h.errors.join()).toContain("grantAllConfirm.depFailed");
  });

  it("cancel writes nothing at all", () => {
    renderAgentsTab([AGENT, DEP]);
    act(() => defaultOnSwitch()!.click());
    const cancel = dialogButton("cancel");
    expect(cancel, "the Cancel button should be in the dialog").toBeTruthy();
    act(() => cancel!.click());

    expect(h.calls).toEqual([]);
    expect(dialog()).toBeNull();
  });

  it("names only the dependencies still missing when several are declared", async () => {
    const multi = cap({
      id: "platform_ops",
      kind: "agent",
      default_capability_ids: ["dep_a", "dep_b", "dep_c"],
    });
    renderAgentsTab([multi, cap({ id: "dep_a" }), cap({ id: "dep_b", default_on: true }), cap({ id: "dep_c" })]);
    act(() => defaultOnSwitch()!.click());
    await clickConfirm();

    // `dep_b` is already default-on: re-granting it would be a write the admin
    // never asked for. Order still puts the template last.
    expect(h.calls.map((c) => c.id)).toEqual(["dep_a", "dep_c", "platform_ops"]);
  });

  it("fires the write directly when the dependency is already default-on", async () => {
    renderAgentsTab([AGENT, cap({ id: "platform_postgres", default_on: true })]);
    await act(async () => defaultOnSwitch()!.click());

    // No dialog, no dependency write — just the template.
    expect(h.calls).toEqual([{ id: "platform_ops", on: true }]);
  });
});

// The drawer's two paths (#2470). Same ordering guarantee as the platform
// switch above, but each grants at its OWN scope: a team row enables the
// dependency for that team, the personal class row sets its personal scope.
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
