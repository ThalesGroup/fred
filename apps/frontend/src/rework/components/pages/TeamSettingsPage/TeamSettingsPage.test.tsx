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
    currentData: h.spacesLoading
      ? undefined
      : [{ id: "pilote", name: "Pilote", kind: h.kind, roles: ["member", "owner"] }],
    isError: h.spacesError,
  }),
  useSpaceMembersQuery: (...args: unknown[]) => {
    h.roster(...args);
    return {
      currentData: {
        items: [
          { user: { id: "nova", username: "nova.responsable" }, roles: ["member", "owner"] },
          { user: { id: "bob", username: "bob" }, roles: ["member", "editor"] },
          ...(h.kind === "organization"
            ? [{ user: { id: "oscar", username: "oscar" }, roles: ["member", "organization_admin"] }]
            : []),
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
  h.read = true;
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

it("offers the roles added to membership, never membership itself, and grants nothing automatically", async () => {
  await render();
  expect(roleButton("nova.responsable", "owner").getAttribute("aria-pressed")).toBe("true");
  expect(roleButton("nova.responsable", "editor").getAttribute("aria-pressed")).toBe("false");
  expect(roleButton("bob", "editor").getAttribute("aria-pressed")).toBe("true");
  expect(roleButton("bob", "member")).toBeNull();
  expect(container.textContent).not.toContain("rework.manager.roles.member");
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
it("blocks direct access and stops roster reads when membership is revoked", async () => {
  await render();
  h.manage = false;
  h.read = false;
  await render();
  expect(container.querySelector("button[aria-pressed]")).toBeNull();
  expect(container.textContent).toContain("rework.spaceMembers.forbidden");
  expect(h.roster).toHaveBeenLastCalledWith(
    { id: "pilote", after: undefined, search: undefined },
    expect.objectContaining({ skip: true }),
  );
});
it("waits for current authorization and sends members to the team's projects", async () => {
  h.settled = false;
  await render(true);
  expect(container.textContent).not.toContain("navigate:");
  h.settled = true;
  await render(true);
  expect(container.textContent).toContain("navigate:/team/pilote/projects");
});
const addButton = () =>
  Array.from(container.querySelectorAll("button")).find((b) =>
    b.textContent?.includes("rework.teamSettings.members.addMembersDialog.buttonLabel"),
  );
it("opens the add dialog over an unchanged roster and gives focus back on close", async () => {
  await render();
  expect(h.candidates).not.toHaveBeenCalled();
  addButton()!.focus();
  await act(async () => addButton()!.click());
  const dialog = document.querySelector<HTMLElement>('[role="dialog"]')!;
  expect(dialog.textContent).toContain("rework.spaceMembers.add.eligibility.team");
  expect(dialog.contains(document.activeElement)).toBe(true);
  expect(roleButton("bob", "editor")).toBeTruthy();
  expect(addButton()).toBeTruthy();
  expect(container.textContent).not.toContain("rework.spaceMembers.roster");
  expect(h.roster).toHaveBeenLastCalledWith(expect.anything(), expect.objectContaining({ skip: false }));
  const cancel = Array.from(dialog.querySelectorAll("button")).find((b) => b.textContent === "common.cancel")!;
  await act(async () => cancel.click());
  expect(document.querySelector('[role="dialog"]')).toBeNull();
  expect(document.activeElement).toBe(addButton());
  expect(h.grant).not.toHaveBeenCalled();
});
it("offers no add dialog in a personal space, which accepts no one else", async () => {
  h.kind = "personal";
  await render();
  expect(addButton()).toBeUndefined();
});

it.each([
  ["team", "projects"],
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

it("sends every organization landing to Home, its panel, whatever the access", async () => {
  h.kind = "organization";
  await render(true);
  expect(container.textContent).toBe("navigate:/home");
  h.manage = false;
  h.read = true;
  await render(true);
  expect(container.textContent).toBe("navigate:/home");
  h.read = false;
  await render(true);
  expect(container.textContent).toBe("navigate:/home");
  expect(h.grant).not.toHaveBeenCalled();
});

it("keeps a forbidden landing when the space is not listed", async () => {
  h.manage = false;
  h.read = false;
  h.spacesError = true;
  await render(true);
  expect(container.textContent).toBe("rework.spaceMembers.forbidden");
});

it("lets a reader view explicit roles and leave without granting management", async () => {
  h.manage = false;
  h.read = true;
  await render();
  expect(container.querySelector('input[type="checkbox"]')).toBeNull();
  expect(container.textContent).toContain("rework.manager.roles.editor");
  expect(roleButton("nova.responsable", "owner").getAttribute("aria-pressed")).toBe("true");
  expect(roleButton("bob", "editor").getAttribute("aria-disabled")).toBe("true");
  await act(async () => roleButton("bob", "editor").click());
  expect(h.grant).not.toHaveBeenCalled();
  expect(h.revoke).not.toHaveBeenCalled();
  await act(async () =>
    container.querySelector<HTMLButtonElement>('button[aria-label="rework.teamSettings.members.moreActions"]')!.click(),
  );
  const leave = Array.from(document.querySelectorAll<HTMLElement>('[role="option"]')).find((b) =>
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
it("keeps the header lean: no search button, no tooltip on more, a plain info icon", async () => {
  await render();
  expect(container.querySelector('button[type="submit"]')).toBeNull();
  const more = container.querySelector<HTMLElement>('[aria-label="rework.teamSettings.members.moreActions"]')!;
  expect(more.tagName).toBe("BUTTON");
  expect(more.closest("[tabindex='0']")).toBeNull();
  // The info icon is not a button; its tooltip trigger stays reachable by keyboard.
  const info = container.querySelector<HTMLElement>(".material-symbols-outlined")!.closest<HTMLElement>("[tabindex]")!;
  expect(info.textContent).toBe("info");
  expect(info.closest("button")).toBeNull();
  expect(container.querySelector("input")!.closest('[data-size="xs"]')).toBeTruthy();
});

it("lets an organization's owners manage its members, showing governance roles read-only", async () => {
  h.kind = "organization";
  await render();
  expect(h.roster).toHaveBeenLastCalledWith(expect.anything(), expect.objectContaining({ skip: false }));
  expect(roleButton("bob", "editor").getAttribute("aria-pressed")).toBe("true");
  const admin = roleButton("oscar", "organization_admin");
  expect(admin.getAttribute("aria-pressed")).toBe("true");
  expect(admin.getAttribute("aria-disabled")).toBe("true");
  await act(async () => admin.click());
  expect(h.revoke).not.toHaveBeenCalled();
  expect(roleButton("bob", "organization_admin")).toBeNull();
  expect(removeButton("oscar")).toBeTruthy();
  await act(async () => addButton()!.click());
  expect(document.querySelector('[role="dialog"]')!.textContent).toContain(
    "rework.spaceMembers.add.eligibility.organization",
  );
});
it("keeps an organization's roster from members who do not manage it", async () => {
  h.kind = "organization";
  h.manage = false;
  await render();
  expect(container.textContent).toContain("rework.spaceMembers.forbidden");
  expect(h.roster).toHaveBeenLastCalledWith(expect.anything(), expect.objectContaining({ skip: true }));
});
it("explains that an organization member leaves its teams first", async () => {
  h.kind = "organization";
  h.remove.mockReturnValue({
    unwrap: () =>
      Promise.reject({ status: 409, data: { code: "conflict", detail: "remove dependent child roles first" } }),
  });
  await render();
  await act(async () => removeButton("oscar").click());
  await act(async () => confirmRemoval().click());
  expectRefusal("dependentTeams");
});

const removeButton = (username: string) =>
  container.querySelector<HTMLButtonElement>(`button[aria-label="rework.spaceMembers.remove: ${username}"]`)!;
const confirmRemoval = () =>
  Array.from(document.querySelectorAll("button")).find((b) => b.textContent === "rework.spaceMembers.remove")!;
// A refusal keeps the dialog open, explains why and offers a single close action.
const expectRefusal = (reason: string) => {
  const dialog = document.querySelector('[role="alertdialog"]')!;
  expect(dialog.textContent).toContain("rework.spaceMembers.removeImpossible");
  expect(dialog.textContent).toContain(`rework.spaceMembers.${reason}`);
  expect(confirmRemoval()).toBeUndefined();
  expect(Array.from(dialog.querySelectorAll("button")).map((b) => b.textContent)).toEqual(["common.close"]);
  expect(container.querySelector('[role="alert"]')).toBeNull();
};

it("removes a person from the space through its row, never by unticking membership", async () => {
  await render();
  await act(async () => removeButton("nova.responsable").click());
  await act(async () => confirmRemoval().click());
  expect(h.remove).toHaveBeenCalledWith({ id: "pilote", user: "nova" });
  expect(h.revoke).not.toHaveBeenCalled();
});

it.each([
  [{ status: 409, data: { code: "conflict", detail: "remove dependent child roles first" } }, "dependentProjects"],
  [{ status: 409, data: { code: "conflict", detail: "a non-personal space must retain an owner" } }, "lastOwner"],
  [{ status: 409, data: { code: "membership_removal_required", detail: "x" } }, "membershipRemovalRequired"],
  [{ status: 409, data: { code: "conflict", detail: "x" } }, "conflict"],
  [{ status: 403, data: { detail: "x" } }, "forbidden"],
])("explains a refused removal in its dialog", async (failure, reason) => {
  h.remove.mockReturnValue({ unwrap: () => Promise.reject(failure) });
  await render();
  await act(async () => removeButton("nova.responsable").click());
  await act(async () => confirmRemoval().click());
  expectRefusal(reason);
  const close = document.querySelector<HTMLButtonElement>('[role="alertdialog"] button')!;
  await act(async () => close.click());
  expect(document.querySelector('[role="alertdialog"]')).toBeNull();
  await act(async () => removeButton("nova.responsable").click());
  expect(confirmRemoval()).toBeTruthy();
});
