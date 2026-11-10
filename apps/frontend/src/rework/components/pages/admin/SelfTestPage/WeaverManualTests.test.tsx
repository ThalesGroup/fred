// @vitest-environment happy-dom
// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { WeaverManualTests } from "./WeaverManualTests";
import type { WeaverChecks } from "../../../../features/pipeline/weaver/checks";
import type { Role, SpaceMembers } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import { buildReport, type ReportSection } from "./report";

const h = vi.hoisted(() => ({
  provider: "keycloak" as "keycloak" | "oidc" | null,
  actor: "operator",
  realm: { url: "https://private-idp.example/", realm: "test-realm", clientId: "test-client" },
  runCampaign: vi.fn(),
  recoverCampaign: vi.fn(),
  checkPersonalIsolation: vi.fn(),
  roster: vi.fn(),
  fetch: vi.fn<typeof fetch>(),
}));
vi.mock("@shared/molecules/Select/Select", () => ({
  default: ({
    label,
    options,
    value,
    disabled,
    onChange,
  }: {
    label: string;
    options: { value: string; label: string }[];
    value?: string;
    disabled: boolean;
    onChange: (value: string) => void;
  }) => (
    <select
      aria-label={label}
      disabled={disabled}
      value={value ?? ""}
      onChange={(event) => onChange(event.target.value)}
    >
      <option value="">Choose account</option>
      {options.map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  ),
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: { name?: string }) => `${key}${options?.name ? `: ${options.name}` : ""}`,
  }),
}));
vi.mock("@shared/molecules/ConfirmationDialog/ConfirmationDialog", () => ({
  ConfirmationDialog: ({
    open,
    message,
    confirmLabel,
    confirmDisabled,
    onConfirm,
  }: {
    open: boolean;
    message: string;
    confirmLabel: string;
    confirmDisabled: boolean;
    onConfirm: () => void;
  }) =>
    open ? (
      <div role="dialog">
        {message}
        <button disabled={confirmDisabled} onClick={onConfirm}>
          {confirmLabel}
        </button>
      </div>
    ) : null,
}));

vi.mock("../../../../features/imports/managerImportRun", () => ({ managerActor: () => h.actor }));
vi.mock("../../../../../security/KeycloakService", async (original) => {
  const service = await original<typeof import("../../../../../security/KeycloakService")>();
  return {
    ...service,
    KeyCloakService: {
      ...service.KeyCloakService,
      GetIdentityProvider: () => h.provider,
      GetKeycloakRealmConfig: () => h.realm,
    },
  };
});
vi.mock("../../../../../slices/controlPlane/controlPlaneApiEnhancements", async (original) => ({
  ...(await original<typeof import("../../../../../slices/controlPlane/controlPlaneApiEnhancements")>()),
  useSpaceMembersQuery: (...args: unknown[]) => h.roster(...args),
}));
vi.mock("../../../../features/pipeline/weaver/campaign", async (original) => ({
  ...(await original<typeof import("../../../../features/pipeline/weaver/campaign")>()),
  runCampaign: h.runCampaign,
  recoverCampaign: h.recoverCampaign,
}));
vi.mock("../../../../features/pipeline/weaver/authorization", () => ({
  checkPersonalIsolation: h.checkPersonalIsolation,
}));

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const context: WeaverChecks = {
  userId: "operator",
  spaceId: "project",
  spaceKind: "project",
  organizationId: "org",
  dispatch: vi.fn(),
  read: vi.fn(),
};
const team = { ...context, spaceId: "team", spaceKind: "team", roles: ["owner", "editor"] } satisfies WeaverChecks & {
  roles: Role[];
};
const rosterPage: SpaceMembers = {
  items: [
    { user: { id: "operator", username: "operator-account" }, roles: ["owner", "editor"] },
    { user: { id: "first", username: "first-test-account" }, roles: ["member"] },
    {
      user: {
        id: "second",
        username: "dedicated-test-account",
        first_name: "Given name",
        email: "fixture-address@example.test",
      },
      roles: ["analyst"],
    },
    { user: { id: "no-username" }, roles: ["editor"] },
    { user: { id: "no-content", username: "owner-only-account" }, roles: ["owner"] },
  ],
  next_cursor: null,
};
const usernameLabel = "rework.selftest.weaver.manual.usernameLabel";
const passwordLabel = "rework.selftest.authz.testProfile.passwordLabel";
const tokenLabel = "rework.selftest.authz.testProfile.tokenLabel";
const startLabel = "rework.selftest.authz.campaign.run";
const confirmLabel = "rework.selftest.authz.campaign.confirm";

beforeEach(() => {
  h.provider = "keycloak";
  h.actor = "operator";
  h.fetch.mockReset();
  h.runCampaign.mockReset();
  h.recoverCampaign.mockReset();
  h.checkPersonalIsolation.mockReset().mockResolvedValue({ identitiesVerified: true });
  h.roster.mockReset().mockReturnValue({ currentData: rosterPage });
  vi.stubGlobal("fetch", h.fetch);
  vi.stubGlobal("navigator", {
    locks: {
      request: async (name: string, _options: LockOptions, callback: LockGrantedCallback<void>) =>
        callback({ name, mode: "exclusive" }),
    },
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
});

function manualTests() {
  const host = document.createElement("div");
  const root = createRoot(host);
  const onRunningChange = vi.fn();
  const reports = vi.fn<(sections: ReportSection[]) => void>();
  return {
    host,
    reports,
    render: (selected: WeaverChecks = context, campaignContext?: WeaverChecks & { roles: Role[] }) =>
      act(async () =>
        root.render(
          <WeaverManualTests
            context={selected}
            campaignContext={campaignContext}
            campaignScopeName="Research"
            expiryScopeName="Atlas"
            busy={false}
            onRunningChange={onRunningChange}
            onReportsChange={reports}
          />,
        ),
      ),
    unmount: () => act(() => root.unmount()),
    select: () => host.querySelector<HTMLSelectElement>("select"),
    choose: (value: string) =>
      act(async () => {
        const select = host.querySelector("select")!;
        select.value = value;
        select.dispatchEvent(new Event("change", { bubbles: true }));
      }),
    input: (label: string) => {
      const id = Array.from(host.querySelectorAll("label")).find((item) => item.textContent === label)?.htmlFor;
      return Array.from(host.querySelectorAll("input")).find((input) => input.id === id);
    },
    button: (label: string) => Array.from(host.querySelectorAll("button")).find((item) => item.textContent === label)!,
  };
}

function fill(input: HTMLInputElement, value: string) {
  return act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(input, value);
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
}

it("names the parent team and terminal space in manual controls, confirmations and copied sections", async () => {
  const { host, render, reports, button, unmount } = manualTests();
  try {
    await render(context, team);
    expect(host.textContent).toContain("rework.selftest.weaver.manual.campaignTarget: Research");
    expect(host.textContent).toContain("rework.selftest.weaver.manual.expiryTarget: Atlas");
    expect(button("rework.selftest.authz.campaign.run").disabled).toBe(true);
    expect(button("rework.selftest.authz.expiry.run").disabled).toBe(false);
    expect(reports.mock.lastCall?.[0].map((section) => section.title).join(" / ")).toContain("Research");
    expect(reports.mock.lastCall?.[0].map((section) => section.title).join(" / ")).toContain("Atlas");
    await act(async () => button("rework.selftest.authz.expiry.run").click());
    expect(host.querySelector('[role="dialog"]')?.textContent).toContain("expiryConfirmation: Atlas");
  } finally {
    unmount();
  }
});

it("lists eligible usernames and uses the selected identity only after confirmation", async () => {
  h.fetch.mockResolvedValue(Response.json({ access_token: "secondary-secret", refresh_token: "unused-refresh" }));
  const ui = manualTests();
  try {
    await ui.render(context, team);
    expect(ui.input(tokenLabel)).toBeUndefined();
    expect(ui.input(passwordLabel)?.type).toBe("password");
    expect(ui.input(passwordLabel)?.disabled).toBe(true);
    expect(ui.select()?.getAttribute("aria-label")).toBe(usernameLabel);
    expect(Array.from(ui.select()!.options).map((option) => option.textContent)).toEqual([
      "Choose account",
      "first-test-account",
      "dedicated-test-account",
    ]);
    expect(ui.button(startLabel).disabled).toBe(true);
    await ui.choose("first");
    await fill(ui.input(passwordLabel)!, "first-password");
    await ui.choose("second");
    expect(ui.input(passwordLabel)?.value).toBe("");
    expect(ui.button(startLabel).disabled).toBe(true);
    await fill(ui.input(passwordLabel)!, "second-password");
    await act(async () => ui.button(startLabel).click());
    expect(h.fetch).not.toHaveBeenCalled();
    expect(ui.host.querySelector('[role="dialog"]')?.textContent).toContain("confirmation: Research");
    expect(ui.host.querySelector('[role="dialog"]')?.textContent).not.toContain("dedicated-test-account");

    await act(async () => ui.button(confirmLabel).click());
    expect(ui.select()?.value).toBe("");
    expect(ui.input(passwordLabel)?.value).toBe("");
    expect(h.fetch).toHaveBeenCalledTimes(1);
    const [endpoint, request] = h.fetch.mock.calls[0];
    expect(endpoint).toBe("https://private-idp.example/realms/test-realm/protocol/openid-connect/token");
    expect(request).toMatchObject({ method: "POST", credentials: "omit", redirect: "error" });
    expect(Object.fromEntries(request!.body as URLSearchParams)).toEqual({
      grant_type: "password",
      client_id: "test-client",
      username: "dedicated-test-account",
      password: "second-password",
    });
    expect(h.runCampaign).toHaveBeenCalledWith(
      team,
      "secondary-secret",
      expect.anything(),
      expect.anything(),
      expect.anything(),
    );
    expect(h.checkPersonalIsolation).toHaveBeenCalledWith(
      "operator",
      "second",
      "secondary-secret",
      expect.any(Function),
      expect.any(AbortSignal),
    );
    expect(localStorage.length).toBe(0);
    const report = buildReport(ui.reports.mock.lastCall![0][0].steps);
    expect(report).toContain("[PASSED] Sign in as the dedicated test account");
    for (const value of ["dedicated-test-account", "second-password", "secondary-secret", "unused-refresh", endpoint]) {
      expect(report).not.toContain(value);
    }
  } finally {
    ui.unmount();
  }
});

it.each([
  {
    failure: () => Promise.reject(new Error("Network error for https://private-idp.example/password-secret")),
    message: "Could not reach the test account sign-in endpoint",
  },
  {
    failure: async () =>
      Response.json({ error: "invalid_grant", error_description: "dedicated-account" }, { status: 400 }),
    message: "Invalid test account username or password",
  },
  {
    failure: async () =>
      Response.json(
        { error: "unauthorized_client", error_description: "https://private-idp.example" },
        { status: 401 },
      ),
    message: "This Keycloak client does not allow direct-grant login for test accounts",
  },
  {
    failure: async () => Response.json({ error: "dedicated-account password-secret" }, { status: 503 }),
    message: "Test account sign-in failed: HTTP 503",
  },
  {
    failure: async () => new Response("dedicated-account password-secret"),
    message: "Test account sign-in returned no usable access token",
  },
])("fails the login safely with $message", async ({ failure, message }) => {
  h.fetch.mockImplementation(failure);
  const ui = manualTests();
  try {
    await ui.render(context, team);
    await ui.choose("second");
    await fill(ui.input(passwordLabel)!, "password-secret");
    await act(async () => ui.button(startLabel).click());
    await act(async () => ui.button(confirmLabel).click());
    const report = buildReport(ui.reports.mock.lastCall![0][0].steps);
    expect(report).toContain("[FAILED] Sign in as the dedicated test account");
    expect(report).toContain(message);
    expect(report).not.toMatch(/dedicated-(?:test-)?account|password-secret|https:\/\//);
    expect(ui.select()?.value).toBe("");
    expect(ui.input(passwordLabel)?.value).toBe("");
    expect(h.runCampaign).not.toHaveBeenCalled();
    expect(h.checkPersonalIsolation).not.toHaveBeenCalled();
    expect(localStorage.length).toBe(0);
  } finally {
    ui.unmount();
  }
});

it("keeps expiry available and explains why the campaign is unavailable with generic OIDC", async () => {
  h.provider = "oidc";
  const ui = manualTests();
  try {
    await ui.render(context, team);
    expect(ui.host.textContent).toContain("rework.selftest.weaver.manual.authRequired");
    expect(ui.select()).toBeNull();
    expect(ui.input(passwordLabel)).toBeUndefined();
    expect(ui.input(tokenLabel)).toBeUndefined();
    expect(ui.button(startLabel).disabled).toBe(true);
    expect(ui.button("rework.selftest.authz.expiry.run").disabled).toBe(false);
    expect(h.roster).toHaveBeenLastCalledWith(expect.anything(), expect.objectContaining({ skip: true }));
  } finally {
    ui.unmount();
  }
});

it("offers eligible accounts on later pages after an empty page and supports retrying a failed page", async () => {
  const ui = manualTests();
  const retry = vi.fn();
  const nextPage: SpaceMembers = { ...rosterPage };
  let nextUnavailable = true;
  h.roster.mockImplementation(({ after }: { after?: string }) =>
    after
      ? nextUnavailable
        ? { isError: true, refetch: retry }
        : { currentData: nextPage }
      : { currentData: { items: [], next_cursor: "next-page" } },
  );
  try {
    await ui.render(context, team);
    expect(ui.host.textContent).toContain("rework.selftest.weaver.manual.accountsEmpty");
    expect(ui.select()?.disabled).toBe(true);
    await act(async () => ui.button("dataTable.pagination.next").click());
    expect(h.roster).toHaveBeenLastCalledWith(
      { id: "team", after: "next-page" },
      expect.objectContaining({ skip: false }),
    );
    expect(ui.host.querySelector('[role="alert"]')?.textContent).toContain("accountsUnavailable");
    expect(ui.button("dataTable.pagination.prev").disabled).toBe(false);
    await act(async () => ui.button("rework.spaceMembers.refresh").click());
    expect(retry).toHaveBeenCalledOnce();
    nextUnavailable = false;
    await ui.render(context, team);
    await ui.choose("second");
    await fill(ui.input(passwordLabel)!, "password-secret");
    expect(ui.button(startLabel).disabled).toBe(false);
    await act(async () => ui.button("dataTable.pagination.prev").click());
    expect(ui.select()?.value).toBe("");
    expect(ui.input(passwordLabel)?.value).toBe("");
    expect(ui.button(startLabel).disabled).toBe(true);
  } finally {
    ui.unmount();
  }
});

it("requires the selected team to give the operator both owner and content roles", async () => {
  const ui = manualTests();
  try {
    await ui.render(context, { ...team, roles: ["owner"] });
    expect(ui.host.textContent).toContain("rework.selftest.weaver.manual.campaignMissingRole");
    expect(ui.select()).toBeNull();
    expect(ui.button(startLabel).disabled).toBe(true);
    expect(h.roster).toHaveBeenLastCalledWith(
      { id: "team", after: undefined },
      expect.objectContaining({ skip: true }),
    );
  } finally {
    ui.unmount();
  }
});

it("refuses the project campaign when sign-in yields a different account", async () => {
  h.fetch.mockResolvedValue(Response.json({ access_token: "different-account-token" }));
  h.checkPersonalIsolation.mockResolvedValue({ identitiesVerified: false });
  const ui = manualTests();
  try {
    await ui.render(context, team);
    await ui.choose("second");
    await fill(ui.input(passwordLabel)!, "password-secret");
    await act(async () => ui.button(startLabel).click());
    await act(async () => ui.button(confirmLabel).click());
    expect(h.checkPersonalIsolation).toHaveBeenCalledOnce();
    expect(h.runCampaign).not.toHaveBeenCalled();
    expect(localStorage.length).toBe(0);
  } finally {
    ui.unmount();
  }
});

it("recovers with the operator and saved journal without credentials or a selected team", async () => {
  h.provider = null;
  localStorage.setItem("selftest-weaver-role-campaign:operator", "{}");
  const ui = manualTests();
  try {
    const organization = { ...context, spaceId: "org", spaceKind: "organization" } satisfies WeaverChecks;
    await ui.render(organization);
    expect(ui.host.textContent).toContain("rework.selftest.weaver.manual.campaignMissingScope");
    expect(ui.host.textContent).toContain("rework.selftest.weaver.manual.expiryMissingScope");
    expect(ui.select()).toBeNull();
    expect(ui.input(tokenLabel)).toBeUndefined();
    expect(ui.button(startLabel).disabled).toBe(true);
    expect(ui.button("rework.selftest.authz.expiry.run").disabled).toBe(true);
    await act(async () => ui.button("rework.selftest.weaver.manual.recover").click());
    expect(h.recoverCampaign).toHaveBeenCalledWith(organization, expect.anything(), expect.anything());
    expect(h.runCampaign).not.toHaveBeenCalled();
    expect(h.fetch).not.toHaveBeenCalled();
  } finally {
    ui.unmount();
  }
});

it("clears unconfirmed credentials and closes the confirmation when the operator changes", async () => {
  const ui = manualTests();
  try {
    await ui.render(context, team);
    await ui.choose("second");
    await fill(ui.input(passwordLabel)!, "password-secret");
    await act(async () => ui.button(startLabel).click());
    h.actor = "another-operator";
    await ui.render({ ...context, userId: h.actor }, { ...team, userId: h.actor });
    expect(ui.select()?.value).toBe("");
    expect(ui.input(passwordLabel)?.value).toBe("");
    expect(ui.host.querySelector('[role="dialog"]')).toBeNull();
    expect(h.fetch).not.toHaveBeenCalled();
  } finally {
    ui.unmount();
  }
});

it.each(["operator change", "unmount"])("discards an in-flight test login after %s", async (interruption) => {
  let resolveGrant!: (response: Response) => void;
  h.fetch.mockReturnValue(
    new Promise((resolve) => {
      resolveGrant = resolve;
    }),
  );
  const ui = manualTests();
  let mounted = true;
  try {
    await ui.render(context, team);
    await ui.choose("second");
    await fill(ui.input(passwordLabel)!, "password-secret");
    await act(async () => ui.button(startLabel).click());
    await act(async () => ui.button(confirmLabel).click());
    expect(h.fetch).toHaveBeenCalledTimes(1);
    if (interruption === "unmount") {
      ui.unmount();
      mounted = false;
      expect(h.fetch.mock.calls[0][1]?.signal?.aborted).toBe(true);
    } else {
      h.actor = "another-operator";
    }
    await act(async () => resolveGrant(Response.json({ access_token: "late-token" })));
    expect(h.checkPersonalIsolation).not.toHaveBeenCalled();
    expect(h.runCampaign).not.toHaveBeenCalled();
    expect(localStorage.length).toBe(0);
  } finally {
    if (mounted) ui.unmount();
  }
});
