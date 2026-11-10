// @vitest-environment happy-dom
// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { act, useEffect } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { Provider } from "react-redux";
import { beforeEach, expect, it, vi } from "vitest";
import { store } from "../../../../../common/store";
import { writeRichClipboard } from "@rework/utils/clipboardUtils";
import WeaverSelfTestPage from "./WeaverSelfTestPage";
import { SelfTestView } from "./SelfTestView";
import type { ReportSection } from "./report";
import type { FamilyId, SelfTestFamily } from "../../../../features/pipeline/familyCatalog";

vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en" } }) }));
vi.mock("@core/hooks/useManagerPlatformAdmin", () => ({
  useManagerPlatformAdmin: () => ({ isAdmin: true, currentData: { user_id: "operator" } }),
}));
const scope = vi.hoisted(() => ({
  spaces: [{ id: "owned", kind: "organization", name: "Owned space", roles: ["owner"] }] as {
    id: string;
    kind: string;
    name: string;
    roles: string[];
    parent_id?: string | null;
    organization_id?: string;
  }[],
}));
vi.mock("../../../../../slices/controlPlane/controlPlaneApiEnhancements", async (original) => ({
  ...(await original<typeof import("../../../../../slices/controlPlane/controlPlaneApiEnhancements")>()),
  useMySpacesQuery: () => ({ currentData: scope.spaces }),
}));
vi.mock("@shared/molecules/Select/Select", () => ({
  default: ({
    value,
    onChange,
    options,
    label,
    disabled,
  }: {
    label?: string;
    disabled?: boolean;
    value?: string;
    onChange: (id: string) => void;
    options: { value: string; label: string }[];
  }) => (
    <select
      aria-label={label}
      disabled={disabled}
      value={value ?? ""}
      onChange={(event) => onChange(event.target.value)}
    >
      <option value="">Choose space</option>
      {options.map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  ),
}));
beforeEach(() => {
  scope.spaces = [{ id: "owned", kind: "organization", name: "Owned space", roles: ["owner"] }];
});
vi.mock("@rework/utils/clipboardUtils", () => ({ writeRichClipboard: vi.fn(async () => true) }));

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

it("admits ownership independently of the unselected picker, shows shared checks without a scope and copies unopened results with manual tests still not run", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response("{}", { status: 503 })),
  );
  const host = document.createElement("div");
  const root = createRoot(host);
  const button = (text: string, scope: ParentNode = host) => {
    const match = Array.from(scope.querySelectorAll("button")).find((b) => b.textContent?.includes(text));
    expect(match).toBeDefined();
    return match!;
  };
  try {
    await act(async () =>
      root.render(
        <Provider store={store}>
          <MemoryRouter>
            <WeaverSelfTestPage />
          </MemoryRouter>
        </Provider>,
      ),
    );
    expect(Array.from(host.querySelectorAll("[data-family]"), (el) => el.getAttribute("data-family"))).toEqual([
      "platform",
      "identity",
      "security",
      "observability",
      "authorization",
    ]);
    expect(button("rework.selftest.page.runPath").disabled).toBe(false);
    expect(button("rework.selftest.authz.campaign.run").disabled).toBe(true);
    const sharedGroup = host.querySelector("details")!;
    expect(sharedGroup.open).toBe(false);
    sharedGroup.open = true;
    const group = host.querySelector('[data-family="platform"]')!;
    await act(async () => button("rework.selftest.family.run", group).click());
    await vi.waitFor(async () => {
      await act(async () => {});
      expect(button("rework.selftest.page.runPath").disabled).toBe(false);
    });
    expect(sharedGroup.open).toBe(true);
    sharedGroup.open = false;
    expect(sharedGroup.open).toBe(false);
    await act(async () => button("rework.selftest.page.copyAll").click());
    const text = vi.mocked(writeRichClipboard).mock.lastCall?.[1];
    expect(text).toContain("rework.selftest.authz.campaign.title: Not run");
    expect(text).toContain("rework.selftest.authz.expiry.title: Not run");
  } finally {
    act(() => root.unmount());
    vi.unstubAllGlobals();
  }
});

it("continues a standard run after a failed group and keeps a prior manual result separate", async () => {
  const host = document.createElement("div");
  const root = createRoot(host);
  const events: string[] = [];
  const names: FamilyId[] = ["platform", "knowledge", "authorization"];
  const groups: SelfTestFamily[] = names.map((id) => ({
    id,
    icon: "cloud",
    run: {
      isRunning: false,
      steps: [],
      start: async () => {
        events.push(id);
        await Promise.resolve();
        if (id === "knowledge") throw new Error();
        events.push(`done:${id}`);
      },
    },
  }));
  function PriorManualRun({ update }: { update: (value: ReportSection[]) => void }) {
    useEffect(() => {
      update([{ title: "Manual run", steps: [{ id: "manual", title: "Manual observation", status: "passed" }] }]);
    }, [update]);
    return null;
  }
  const click = async (key: string) =>
    act(async () =>
      Array.from(host.querySelectorAll("button"))
        .find((b) => b.textContent?.includes(key))!
        .click(),
    );
  try {
    await act(async () =>
      root.render(
        <SelfTestView
          families={groups}
          setup={() => null}
          manual={({ onReportsChange }) => <PriorManualRun update={onReportsChange} />}
        />,
      ),
    );
    await click("rework.selftest.page.runStandard");
    expect(events).toEqual(["platform", "done:platform", "knowledge", "authorization", "done:authorization"]);
    await click("rework.selftest.page.copyAll");
    expect(vi.mocked(writeRichClipboard).mock.lastCall?.[1]).toContain("Manual tests: 1 passed");
  } finally {
    act(() => root.unmount());
  }
});

it.each(["team", "personal"])(
  "selects a writable %s for the common run and preserves an explicit organization choice on refresh",
  async (kind) => {
    const organization = { id: "org", kind: "organization", name: "Organization", roles: ["owner"] };
    scope.spaces = [
      organization,
      { id: "read-only", kind: "team", name: "Owner-only team", roles: ["owner"] },
      { id: "supported", kind, name: "Supported space", roles: ["editor"] },
    ];
    const host = document.createElement("div");
    const root = createRoot(host);
    const render = () =>
      root.render(
        <Provider store={store}>
          <MemoryRouter>
            <WeaverSelfTestPage />
          </MemoryRouter>
        </Provider>,
      );
    try {
      await act(async () => render());
      expect(host.querySelector("select")?.value).toBe("supported");
      expect(host.querySelector("select")?.querySelectorAll("option")).toHaveLength(5);
      await act(async () => {
        const picker = host.querySelector("select")!;
        picker.value = "org";
        picker.dispatchEvent(new Event("change", { bubbles: true }));
      });
      scope.spaces = [...scope.spaces];
      await act(async () => render());
      expect(host.querySelector("select")?.value).toBe("org");
    } finally {
      act(() => root.unmount());
    }
  },
);

it("leaves the picker empty when only an owner-only team is available", async () => {
  scope.spaces = [{ id: "owner-only", kind: "team", name: "Owner-only team", roles: ["owner"] }];
  const host = document.createElement("div");
  const root = createRoot(host);
  try {
    await act(async () =>
      root.render(
        <Provider store={store}>
          <MemoryRouter>
            <WeaverSelfTestPage />
          </MemoryRouter>
        </Provider>,
      ),
    );
    expect(host.querySelector("select")?.value).toBe("");
    expect(host.querySelectorAll("option")).toHaveLength(3);
  } finally {
    act(() => root.unmount());
  }
});

it("cascades verified memberships, clears children and preserves direct grants", async () => {
  scope.spaces = [
    { id: "org", kind: "organization", name: "North", roles: ["owner"], parent_id: null, organization_id: "org" },
    { id: "team", kind: "team", name: "Research", roles: ["editor"], parent_id: "org", organization_id: "org" },
    { id: "project", kind: "project", name: "Atlas", roles: ["editor"], parent_id: "team", organization_id: "org" },
    { id: "other", kind: "organization", name: "South", roles: ["owner"], parent_id: null, organization_id: "other" },
    {
      id: "direct",
      kind: "project",
      name: "Direct grant",
      roles: ["editor"],
      parent_id: "missing",
      organization_id: "org",
    },
    {
      id: "mismatch",
      kind: "project",
      name: "Different organization",
      roles: ["editor"],
      parent_id: "team",
      organization_id: "other",
    },
  ];
  const host = document.createElement("div");
  const root = createRoot(host);
  const pick = async (label: string, value: string) =>
    act(async () => {
      const picker = host.querySelector<HTMLSelectElement>(`select[aria-label="rework.selftest.path.${label}"]`)!;
      picker.value = value;
      picker.dispatchEvent(new Event("change", { bubbles: true }));
    });
  try {
    await act(async () =>
      root.render(
        <Provider store={store}>
          <MemoryRouter>
            <WeaverSelfTestPage />
          </MemoryRouter>
        </Provider>,
      ),
    );
    expect(Array.from(host.querySelectorAll("select"), (picker) => picker.value)).toEqual(["org", "team", "team"]);
    const projectPicker = host.querySelector<HTMLSelectElement>(
      'select[aria-label="rework.selftest.path.chooseProject"]',
    )!;
    expect(Array.from(projectPicker.options, (option) => option.value)).toEqual(["", "team", "project"]);
    await pick("chooseProject", "project");
    expect(host.textContent).toContain("North");
    expect(host.textContent).toContain("Research");
    expect(host.textContent).toContain("Atlas");
    await pick("root", "other");
    expect(Array.from(host.querySelectorAll("select"), (picker) => picker.value)).toEqual(["other", "other"]);
    await pick("root", "direct");
    expect(host.querySelectorAll("select")).toHaveLength(1);
    expect(host.querySelector("select")?.value).toBe("direct");
    expect(host.querySelectorAll('[data-family="platform"]')).toHaveLength(1);
  } finally {
    act(() => root.unmount());
  }
});
