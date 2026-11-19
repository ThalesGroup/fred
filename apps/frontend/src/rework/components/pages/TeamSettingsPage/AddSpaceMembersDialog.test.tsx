// @vitest-environment happy-dom
// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import type { SpaceMember } from "../../../../slices/controlPlane/controlPlaneOpenApi";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const h = vi.hoisted(() => ({
  pages: {} as Record<string, { items: SpaceMember[]; next_cursor: string | null }>,
  error: false,
  query: vi.fn(),
  grant: vi.fn(),
}));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock("../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useSpaceMemberCandidatesQuery: (args: { after?: string }, options: { skip: boolean }) => {
    h.query(args, options);
    if (options.skip) return { isFetching: false, isError: false };
    if (h.error) return { isFetching: false, isError: true };
    return { isFetching: false, isError: false, currentData: h.pages[args.after ?? ""] };
  },
  useGrantMutation: () => [h.grant],
}));
import AddSpaceMembersDialog from "./AddSpaceMembersDialog";

const person = (id: string, roles: SpaceMember["roles"] = []): SpaceMember => ({ user: { id, username: id }, roles });
const onClose = vi.fn();
let host: HTMLDivElement;
let root: Root;
const portal = () => document.getElementById("modal-portal")!;
const input = () => portal().querySelector("input") as HTMLInputElement;
const search = (value: string) => {
  act(() => {
    input().focus();
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(input(), value);
    input().dispatchEvent(new Event("input", { bubbles: true }));
  });
  act(() => vi.advanceTimersByTime(300));
};
const options = () => [...document.querySelectorAll<HTMLElement>('[role="option"]')];
const option = (text: string) => options().find((node) => node.textContent?.includes(text))!;
const button = (label: string) =>
  [...portal().querySelectorAll<HTMLButtonElement>("button")].find(
    (node) => node.textContent === label || node.getAttribute("aria-label") === label,
  )!;
const confirm = () => button("rework.teamSettings.members.addMembersDialog.confirm");

beforeEach(() => {
  h.pages = { "": { items: [person("alice"), person("bob"), person("carol", ["member"])], next_cursor: null } };
  h.error = false;
  vi.clearAllMocks();
  h.grant.mockReturnValue({ unwrap: () => Promise.resolve() });
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
  act(() => root.render(<AddSpaceMembersDialog spaceId="pilote" kind="project" onClose={onClose} />));
});
afterEach(() => {
  act(() => root.unmount());
  host.remove();
  document.getElementById("modal-portal")?.remove();
  vi.useRealTimers();
});

it("explains eligibility for the space kind and searches eligible people after a pause", () => {
  expect(portal().textContent).toContain("rework.spaceMembers.add.eligibility.project");
  expect(document.activeElement).toBe(input());
  expect(h.query.mock.calls.every(([, opts]) => opts.skip)).toBe(true);
  search("a");
  expect(h.query.mock.calls.every(([, opts]) => opts.skip)).toBe(true);
  search("al");
  expect(h.query).toHaveBeenLastCalledWith({ id: "pilote", after: undefined, search: "al" }, expect.anything());
  expect(option("carol").getAttribute("aria-disabled")).toBe("true");
  expect(option("carol").textContent).toContain("rework.spaceMembers.add.alreadyMember");
});

it("follows the cursor past an empty slice instead of reporting no match", () => {
  h.pages = { "": { items: [], next_cursor: "m" }, m: { items: [person("zoe")], next_cursor: null } };
  search("zo");
  expect(h.query).toHaveBeenLastCalledWith({ id: "pilote", after: "m", search: "zo" }, expect.anything());
  expect(option("zoe")).toBeTruthy();
});

it("adds several people with several roles only on the explicit Add", async () => {
  expect(confirm().disabled).toBe(true);
  search("al");
  act(() => option("alice").click());
  search("bo");
  act(() => option("bob").click());
  expect(h.grant).not.toHaveBeenCalled();
  act(() => button("bob: rework.manager.roles.editor").click());
  act(() => button("alice: rework.manager.roles.member").click());
  expect(confirm().disabled).toBe(true);
  expect(portal().textContent).toContain("rework.spaceMembers.add.roleRequired");
  act(() => button("alice: rework.manager.roles.analyst").click());
  await act(async () => confirm().click());
  expect(h.grant.mock.calls.map(([args]) => args)).toEqual([
    { id: "pilote", user: "alice", role: "analyst" },
    { id: "pilote", user: "bob", role: "member" },
    { id: "pilote", user: "bob", role: "editor" },
  ]);
  expect(onClose).toHaveBeenCalledOnce();
});

it("keeps only failed grants selected and shows the error", async () => {
  h.grant.mockImplementation(({ user }: { user: string }) => ({
    unwrap: () => (user === "bob" ? Promise.reject({ status: 409 }) : Promise.resolve()),
  }));
  search("al");
  act(() => option("alice").click());
  search("bo");
  act(() => option("bob").click());
  await act(async () => confirm().click());
  expect(onClose).not.toHaveBeenCalled();
  expect(portal().querySelector('[role="alert"]')?.textContent).toBe("rework.spaceMembers.conflict");
  const pending = portal().querySelector("ul")!.textContent;
  expect(pending).toContain("bob");
  expect(pending).not.toContain("alice");
});

it("reports a failed search", () => {
  h.error = true;
  search("al");
  expect(document.body.textContent).toContain("rework.spaceMembers.add.searchFailed");
});
