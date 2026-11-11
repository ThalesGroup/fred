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
  roster: vi.fn(),
  candidates: vi.fn(),
}));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock("react-router-dom", () => ({
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
  useRevokeMutation: () => [h.revoke, { isLoading: false }],
}));
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
  h.settled = true;
  h.section = "members";
  vi.clearAllMocks();
  h.grant.mockReturnValue({ unwrap: () => Promise.resolve() });
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
const checkbox = (username: string, role: string) =>
  container.querySelector<HTMLInputElement>(`input[aria-label="${username}: rework.manager.roles.${role}"]`)!;

it("opens management for an owner without content access and grants nothing automatically", async () => {
  await render(true);
  expect(container.textContent).toContain("navigate:/team/pilote/settings/members");
  await render();
  expect(checkbox("nova.responsable", "owner").checked).toBe(true);
  expect(checkbox("nova.responsable", "member").checked).toBe(false);
  expect(checkbox("nova.responsable", "editor").checked).toBe(false);
  expect(checkbox("bob", "member").checked).toBe(true);
  expect(checkbox("bob", "editor").checked).toBe(true);
  expect(h.grant).not.toHaveBeenCalled();
  expect(h.revoke).not.toHaveBeenCalled();
  await act(async () => checkbox("bob", "analyst").click());
  expect(h.grant).toHaveBeenCalledWith({ id: "pilote", user: "bob", role: "analyst" });
});
it("keeps cumulative roles and reports a refused last-owner removal", async () => {
  h.revoke.mockReturnValue({ unwrap: () => Promise.reject({ status: 409 }) });
  await render();
  await act(async () => checkbox("nova.responsable", "owner").click());
  expect(h.revoke).toHaveBeenCalledWith({ id: "pilote", user: "nova", role: "owner" });
  expect(container.textContent).toContain("rework.spaceMembers.conflict");
  expect(checkbox("nova.responsable", "owner").checked).toBe(true);
});
it("blocks direct access and stops roster reads when management is revoked", async () => {
  await render();
  h.manage = false;
  await render();
  expect(container.querySelector('input[type="checkbox"]')).toBeNull();
  expect(container.textContent).toContain("rework.spaceMembers.forbidden");
  expect(h.roster).toHaveBeenLastCalledWith(
    { id: "pilote", after: undefined },
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
