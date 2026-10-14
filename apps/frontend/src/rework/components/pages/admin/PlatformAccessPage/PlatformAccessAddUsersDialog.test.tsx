// SPDX-License-Identifier: Apache-2.0
// @vitest-environment happy-dom
import { act } from "react";
import { createRoot, Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import type { PlatformAccessUser } from "../../../../../slices/controlPlane/controlPlaneOpenApi";

const state = vi.hoisted(() => ({
  users: [] as PlatformAccessUser[],
  total: undefined as number | undefined,
  fetching: false,
  error: false,
  query: vi.fn(),
}));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, unknown>) => (options ? `${key} ${JSON.stringify(options)}` : key),
  }),
}));
vi.mock("../../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  usePlatformAccessUsersQuery: (args: unknown, options: { skip: boolean }) => {
    state.query(args, options);
    if (options.skip) return { isFetching: false, isError: false };
    return {
      isFetching: state.fetching,
      isError: state.error,
      currentData:
        state.fetching || state.error ? undefined : { total: state.total ?? state.users.length, items: state.users },
    };
  },
}));
import PlatformAccessAddUsersDialog from "./PlatformAccessAddUsersDialog";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const person = (id: string, username: string, kinds: PlatformAccessUser["sources"][number]["kind"][] = []) =>
  ({ user_id: id, username, email: null, sources: kinds.map((kind) => ({ kind })) }) as PlatformAccessUser;
const alice = person("a", "alice");
const bob = person("b", "bob");
const onClose = vi.fn();
const onConfirm = vi.fn();
let host: HTMLDivElement, root: Root;
const show = (props: { open?: boolean; busy?: boolean } = {}) =>
  act(() =>
    root.render(
      <PlatformAccessAddUsersDialog
        open={props.open ?? true}
        busy={props.busy ?? false}
        onClose={onClose}
        onConfirm={onConfirm}
      />,
    ),
  );
const portal = () => document.getElementById("modal-portal")!;
const input = () => portal().querySelector("input") as HTMLInputElement;
const type = (value: string) =>
  act(() => {
    input().focus();
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(input(), value);
    input().dispatchEvent(new Event("input", { bubbles: true }));
  });
const search = (value: string) => {
  type(value);
  act(() => vi.advanceTimersByTime(300));
};
const options = () => [...portal().querySelectorAll<HTMLElement>('[role="option"]')];
const option = (text: string) => options().find((node) => node.textContent?.includes(text))!;
const button = (text: string) => [...portal().querySelectorAll("button")].find((node) => node.textContent === text)!;
const confirm = () => button("rework.platformAccess.addDialog.confirm");
const pendingText = () => portal().querySelector('ul[class*="pendingList"]')?.textContent ?? "";

beforeEach(() => {
  state.users = [alice, bob];
  state.total = undefined;
  state.fetching = false;
  state.error = false;
  vi.clearAllMocks();
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
});
afterEach(() => {
  act(() => root.unmount());
  host.remove();
  document.getElementById("modal-portal")?.remove();
  vi.useRealTimers();
});

it("renders nothing and sends no request while closed", () => {
  show({ open: false });
  expect(document.getElementById("modal-portal")).toBeNull();
  expect(state.query.mock.calls.every(([, options]) => options.skip)).toBe(true);
});

it("searches all known users after a pause, from two characters, one bounded page at a time", () => {
  show();
  expect(state.query.mock.calls.every(([, options]) => options.skip)).toBe(true);
  search("a");
  expect(state.query.mock.calls.every(([, options]) => options.skip)).toBe(true);
  type(" al");
  type(" ali ");
  expect(state.query.mock.calls.every(([, options]) => options.skip)).toBe(true);
  expect(portal().textContent).toContain("rework.platformAccess.addDialog.searching");
  act(() => vi.advanceTimersByTime(300));
  // No exceptionsOnly: the dialog looks among every known user, not only the whitelist.
  expect(state.query.mock.lastCall).toEqual([{ offset: 0, limit: 25, query: "ali" }, { skip: false }]);
  expect(state.query.mock.calls.some(([args]) => args.query === "al")).toBe(false);
  expect(options().map((node) => node.textContent)).toEqual(["alice", "bob"]);
});

it("keeps the selection across searches and grants it in one confirmation", () => {
  show();
  expect(confirm().disabled).toBe(true);
  search("al");
  act(() => option("alice").click());
  expect(pendingText()).toContain("alice");
  state.users = [bob];
  search("bo");
  act(() => option("bob").click());
  expect(pendingText()).toContain("alice");
  expect(pendingText()).toContain("bob");
  act(() => confirm().click());
  expect(onConfirm).toHaveBeenCalledWith(["a", "b"]);
});

it("leaves already selected people out of the suggestions and lets them be removed", () => {
  show();
  search("al");
  act(() => option("alice").click());
  search("al");
  expect(options().map((node) => node.textContent)).toEqual(["bob"]);
  act(() =>
    portal()
      .querySelector<HTMLButtonElement>('button[aria-label^="rework.platformAccess.addDialog.removeAria"]')!
      .click(),
  );
  expect(pendingText()).toBe("");
  expect(confirm().disabled).toBe(true);
});

it("shows a person who already has individual access as such and not selectable", () => {
  state.users = [person("m", "manual-user", ["manual"]), person("t", "imported-user", ["t0", "team"]), bob];
  show();
  search("user");
  for (const name of ["manual-user", "imported-user"]) {
    expect(option(name).textContent).toContain("rework.platformAccess.addDialog.alreadyGranted");
    expect(option(name).getAttribute("aria-disabled")).toBe("true");
    act(() => option(name).click());
  }
  expect(pendingText()).toBe("");
  expect(option("bob").getAttribute("aria-disabled")).not.toBe("true");
  expect(option("bob").textContent).not.toContain("alreadyGranted");
});

it("says how many more people match than the page shows, on a line that cannot be selected", () => {
  state.total = 40;
  show();
  search("al");
  const more = option("rework.platformAccess.addDialog.more");
  expect(more.textContent).toContain('{"count":38}');
  act(() => more.click());
  expect(pendingText()).toBe("");
});

it("tells searching, no match and a failed search apart, never showing an earlier answer", () => {
  show();
  search("al");
  state.fetching = true;
  search("alz");
  expect(options()).toHaveLength(0);
  expect(portal().textContent).toContain("rework.platformAccess.addDialog.searching");
  state.fetching = false;
  state.users = [];
  search("alzz");
  expect(portal().textContent).toContain("rework.platformAccess.addDialog.noMatch");
  state.error = true;
  search("alzzz");
  expect(portal().textContent).toContain("rework.platformAccess.addDialog.searchFailed");
  // Typing again hides the previous answer until the new one arrives.
  state.error = false;
  state.users = [alice];
  search("al");
  type("alx");
  expect(options()).toHaveLength(0);
});

it("starts empty on every opening", () => {
  show();
  search("al");
  act(() => option("alice").click());
  show({ open: false });
  show();
  expect(pendingText()).toBe("");
  expect(confirm().disabled).toBe(true);
});

it("cannot be confirmed twice or dismissed while the grant is being saved", () => {
  show();
  search("al");
  act(() => option("alice").click());
  show({ busy: true });
  expect(confirm().disabled).toBe(true);
  act(() => button("common.cancel").click());
  expect(onClose).not.toHaveBeenCalled();
  expect(pendingText()).toContain("alice");
  show({ busy: false });
  act(() => button("common.cancel").click());
  expect(onClose).toHaveBeenCalledTimes(1);
});
