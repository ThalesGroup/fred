// @vitest-environment happy-dom
// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const h = vi.hoisted(() => ({
  kind: "team",
  spacesLoading: false,
  spacesError: false,
  manage: true,
  read: false,
  settled: true,
  section: "members",
  grant: vi.fn(),
  revoke: vi.fn(),
  remove: vi.fn(),
  navigate: vi.fn(),
  roster: vi.fn(),
  candidates: vi.fn(),
}));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock("react-router-dom", () => ({
  useNavigate: () => h.navigate,
  useParams: () => ({ teamId: "pilote", section: h.section }),
  Navigate: ({ to }: { to: string }) => <p>{`navigate:${to}`}</p>,
}));
vi.mock("@core/hooks/useSpaceAccess", () => ({
  useSpaceAccess: (_id: string, permission: string) => ({
    allowed: permission === "manage" ? h.manage : h.read,
    settled: h.settled,
  }),
}));
vi.mock("../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useMySpacesQuery: () => ({
    currentData: h.spacesLoading ? undefined : [{ id: "pilote", name: "Pilote", kind: h.kind, roles: ["owner"] }],
    isError: h.spacesError,
  }),
  useSpaceMembersQuery: (...args: unknown[]) => {
    h.roster(...args);
    return {
      currentData: {
        items: [
          { user: { id: "nova", username: "nova.responsable" }, roles: ["owner"] },
          { user: { id: "bob", username: "bob" }, roles: ["member", "editor"] },
        ],
        next_cursor: null,
      },
      refetch: vi.fn(),
    };
  },
  useSpaceMemberCandidatesQuery: (...args: unknown[]) => {
    h.candidates(...args);
    return { currentData: { items: [], next_cursor: null }, refetch: vi.fn() };
  },
  useGrantMutation: () => [h.grant, { isLoading: false }],
  useRemoveSpaceMemberMutation: () => [h.remove, { isLoading: false }],
  useRevokeMutation: () => [h.revoke, { isLoading: false }],
}));
vi.mock("../../../../security/KeycloakService", () => ({ KeyCloakService: { GetUserId: () => "bob" } }));
import TeamSettingsPage from "./TeamSettingsPage";
import TeamLandingPage from "./TeamLandingPage";
let container: HTMLDivElement;
let root: Root;
beforeEach(() => {
  h.kind = "team";
  h.spacesLoading = false;
  h.spacesError = false;
  h.manage = true;
  h.read = false;
  h.read = false;
  h.settled = true;
  h.section = "members";
  vi.clearAllMocks();
  h.grant.mockReturnValue({ unwrap: () => Promise.resolve() });
  h.remove.mockReturnValue({ unwrap: () => Promise.resolve() });
  h.revoke.mockReturnValue({ unwrap: () => Promise.resolve() });
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});
afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
});
const render = async (landing = false) => {
  await act(async () => root.render(landing ? <TeamLandingPage /> : <TeamSettingsPage />));
};
const roleButton = (username: string, role: string) =>
  container.querySelector<HTMLButtonElement>(`button[aria-label="${username}: rework.manager.roles.${role}"]`)!;

it("opens management for an owner without content access and grants nothing automatically", async () => {
  await render(true);
  expect(container.textContent).toContain("navigate:/team/pilote/settings/members");
  await render();
  expect(roleButton("nova.responsable", "owner").getAttribute("aria-pressed")).toBe("true");
  expect(roleButton("nova.responsable", "member").getAttribute("aria-pressed")).toBe("false");
  expect(roleButton("nova.responsable", "editor").getAttribute("aria-pressed")).toBe("false");
  expect(roleButton("bob", "member").getAttribute("aria-pressed")).toBe("true");
  expect(roleButton("bob", "editor").getAttribute("aria-pressed")).toBe("true");
  expect(h.grant).not.toHaveBeenCalled();
  expect(h.revoke).not.toHaveBeenCalled();
  await act(async () => roleButton("bob", "analyst").click());
  expect(h.grant).toHaveBeenCalledWith({ id: "pilote", user: "bob", role: "analyst" });
});
it("keeps cumulative roles and reports a refused last-owner removal", async () => {
  h.revoke.mockReturnValue({ unwrap: () => Promise.reject({ status: 409 }) });
  await render();
  await act(async () => roleButton("nova.responsable", "owner").click());
  expect(h.revoke).toHaveBeenCalledWith({ id: "pilote", user: "nova", role: "owner" });
  expect(container.textContent).toContain("rework.spaceMembers.conflict");
  expect(roleButton("nova.responsable", "owner").getAttribute("aria-pressed")).toBe("true");
});
it("blocks direct access and stops roster reads when management is revoked", async () => {
  await render();
  h.manage = false;
  await render();
  expect(container.querySelector("button[aria-pressed]")).toBeNull();
  expect(container.textContent).toContain("rework.spaceMembers.forbidden");
  expect(h.roster).toHaveBeenLastCalledWith(
    { id: "pilote", after: undefined, search: undefined },
    expect.objectContaining({ skip: true }),
  );
});
it("waits for current authorization and sends content users to agents", async () => {
  h.settled = false;
  await render(true);
  expect(container.textContent).not.toContain("navigate:");
  h.settled = true;
  h.read = true;
  await render(true);
  expect(container.textContent).toContain("navigate:/team/pilote/agents");
});
it("loads eligible parent users only on explicit request", async () => {
  await render();
  expect(h.candidates).toHaveBeenLastCalledWith(expect.anything(), expect.objectContaining({ skip: true }));
  const button = Array.from(container.querySelectorAll("button")).find((b) =>
    b.textContent?.includes("rework.spaceMembers.candidates"),
  )!;
  await act(async () => button.click());
  expect(h.candidates).toHaveBeenLastCalledWith(expect.anything(), expect.objectContaining({ skip: false }));
  expect(h.grant).not.toHaveBeenCalled();
});

it.each([
  ["organization", "resources"],
  ["team", "agents"],
  ["project", "agents"],
  ["personal", "agents"],
])("lands a reader of a %s space on %s", async (kind, destination) => {
  h.kind = kind;
  h.read = true;
  h.manage = false;
  await render(true);
  expect(container.textContent).toBe(`navigate:/team/pilote/${destination}`);
  expect(h.grant).not.toHaveBeenCalled();
});

it("waits for the organization kind and never falls through to agents after a failed lookup", async () => {
  h.kind = "organization";
  h.read = true;
  h.spacesLoading = true;
  await render(true);
  expect(container.textContent).toBe("common.loading");
  h.spacesLoading = false;
  h.spacesError = true;
  await render(true);
  expect(container.textContent).toBe("rework.manager.unavailable");
});

it("preserves management-only and forbidden organization landings", async () => {
  h.kind = "organization";
  await render(true);
  expect(container.textContent).toBe("navigate:/team/pilote/settings/members");
  h.manage = false;
  await render(true);
  expect(container.textContent).toBe("rework.spaceMembers.forbidden");
  expect(h.grant).not.toHaveBeenCalled();
});

it("lets a reader view explicit roles and leave without granting management", async () => {
  h.manage = false;
  h.read = true;
  await render();
  expect(container.querySelector('input[type="checkbox"]')).toBeNull();
  expect(container.textContent).toContain("rework.manager.roles.editor");
  expect(roleButton("nova.responsable", "owner").getAttribute("aria-pressed")).toBe("true");
  expect(roleButton("nova.responsable", "member").getAttribute("aria-pressed")).toBe("false");
  expect(roleButton("bob", "editor").getAttribute("aria-disabled")).toBe("true");
  await act(async () => roleButton("bob", "editor").click());
  expect(h.grant).not.toHaveBeenCalled();
  expect(h.revoke).not.toHaveBeenCalled();
  const leave = Array.from(container.querySelectorAll("button")).find((b) =>
    b.textContent?.includes("rework.teamSettings.navigation.leaveTeam"),
  )!;
  await act(async () => leave.click());
  const confirm = Array.from(document.querySelectorAll("button")).find(
    (b) => b.textContent === "rework.spaceMembers.remove",
  )!;
  await act(async () => confirm.click());
  expect(h.remove).toHaveBeenCalledWith({ id: "pilote", user: "bob" });
  expect(h.navigate).toHaveBeenCalledWith("/home", { replace: true });
});
it("submits a scoped search and resets pagination", async () => {
  await render();
  const input =
    container.querySelector<HTMLInputElement>('input[type="search"]') ??
    container.querySelector<HTMLInputElement>('input[type="text"]')!;
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(input, "Bob");
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
  await act(async () =>
    container.querySelector("form")!.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true })),
  );
  expect(h.roster).toHaveBeenLastCalledWith({ id: "pilote", after: undefined, search: "Bob" }, expect.anything());
});
