// SPDX-License-Identifier: Apache-2.0
// @vitest-environment happy-dom
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import type { RefreshPlatformT0 } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
const state = vi.hoisted(() => ({
  complete: true,
  filtering: false,
  fetching: false,
  stale: false,
  fail: false,
  queries: vi.fn(),
  success: vi.fn(),
  close: vi.fn(),
  refetch: vi.fn(async () => undefined),
  submit: vi.fn((_arg: { body: RefreshPlatformT0 }) => ({ unwrap: async () => ({ imported_count: 2 }) })),
}));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock("@shared/molecules/Toast/ToastProvider", () => ({ useToast: () => ({ showSuccess: state.success }) }));
vi.mock("../../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  usePlatformAccessStateQuery: () => ({
    data: { revision: 3, filtering_enabled: state.filtering },
    isFetching: false,
    isError: false,
    refetch: state.refetch,
  }),
  usePlatformAccessT0Query: (args: { refreshMode?: string }) => {
    state.queries(args);
    const data = {
      completed_at: "2026-10-01T12:00:00Z",
      revision: 3,
      removal_history_complete: state.complete,
      candidates: 2,
      matching: 0,
      removed_skipped: 1,
    };
    return {
      data,
      currentData: args.refreshMode && state.stale ? undefined : data,
      isFetching: !!args.refreshMode && state.fetching,
      isError: state.fail,
      isUninitialized: false,
      refetch: state.refetch,
    };
  },
  useImportPlatformT0Mutation: () => [state.submit],
}));
import PlatformAccessT0RefreshDialog from "./PlatformAccessT0RefreshDialog";
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
let host: HTMLDivElement, root: Root;
const key = (name: string) => `rework.platformAccess.t0Refresh.${name}`;
const button = (name: string) =>
  [...document.querySelectorAll<HTMLButtonElement>("button")].find((node) => node.textContent === name)!;
const render = () => act(() => root.render(<PlatformAccessT0RefreshDialog onClose={state.close} />));
const selectInclude = () => {
  act(() => document.querySelector<HTMLButtonElement>('[aria-haspopup="listbox"]')!.click());
  act(() =>
    [...document.querySelectorAll<HTMLElement>('[role="option"]')]
      .find((node) => node.textContent?.includes(key("include_removed")))!
      .click(),
  );
};
beforeEach(() => {
  vi.clearAllMocks();
  state.complete = true;
  state.filtering = false;
  state.fetching = false;
  state.stale = false;
  state.fail = false;
  state.submit.mockImplementation(() => ({ unwrap: async () => ({ imported_count: 2 }) }));
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
});
afterEach(() => {
  act(() => root.unmount());
  host.remove();
});

it.each([false, true])("starts on preservation and submits with filtering=%s", async (filtering) => {
  state.filtering = filtering;
  render();
  expect(state.submit).not.toHaveBeenCalled();
  expect(state.queries).toHaveBeenCalledWith({ refreshMode: "preserve_removals" });
  await act(async () => button(key("confirm")).click());
  expect(state.submit).toHaveBeenCalledWith({
    body: { mode: "preserve_removals", expected_revision: 3, expected_completed_at: "2026-10-01T12:00:00Z" },
  });
  expect(state.success).toHaveBeenCalledWith({ summary: key("success") });
  expect(state.close).toHaveBeenCalledOnce();
});

it.each([false, true])(
  "warns before including removed people with filtering=%s and resets after reopening",
  async (filtering) => {
    state.filtering = filtering;
    render();
    selectInclude();
    expect(document.body.textContent).toContain(key("includeWarning"));
    expect(state.submit).not.toHaveBeenCalled();
    await act(async () => button(key("confirm")).click());
    expect(state.submit.mock.calls[0][0].body.mode).toBe("include_removed");
    act(() => root.unmount());
    root = createRoot(host);
    render();
    expect(document.querySelector('[aria-haspopup="listbox"]')?.textContent).toContain(key("preserve_removals"));
  },
);

it.each([false, true])(
  "requires inclusion with missing history and filtering=%s until reset succeeds",
  async (filtering) => {
    state.filtering = filtering;
    state.complete = false;
    render();
    expect(document.body.textContent).toContain(key("missingHistory"));
    expect(state.queries).toHaveBeenCalledWith({ refreshMode: "include_removed" });
    act(() => document.querySelector<HTMLButtonElement>('[aria-haspopup="listbox"]')!.click());
    const preserve = [...document.querySelectorAll('[role="option"]')].find((node) =>
      node.textContent?.includes(key("preserve_removals")),
    )!;
    expect(preserve.getAttribute("aria-disabled")).toBe("true");
    expect(state.submit).not.toHaveBeenCalled();
    await act(async () => button(key("confirm")).click());
    expect(state.submit.mock.calls[0][0].body.mode).toBe("include_removed");
    act(() => root.unmount());
    root = createRoot(host);
    state.complete = true;
    render();
    expect(document.body.textContent).not.toContain(key("missingHistory"));
    expect(document.querySelector('[aria-haspopup="listbox"]')?.textContent).toContain(key("preserve_removals"));
  },
);

it("does not import when cancelled", () => {
  render();
  act(() => button("common.cancel").click());
  expect(state.close).toHaveBeenCalledOnce();
  expect(state.submit).not.toHaveBeenCalled();
});

it.each(["fetching", "stale", "fail"] as const)("prevents confirmation while %s", (condition) => {
  state[condition] = true;
  render();
  expect(button(key("confirm")).disabled).toBe(true);
  expect(state.submit).not.toHaveBeenCalled();
});

it("refreshes a conflicting snapshot and retains the dialog without announcing success", async () => {
  state.submit.mockImplementation(() => ({
    unwrap: async () => {
      throw { status: 409, data: { detail: "platform_access_t0_snapshot_changed" } };
    },
  }));
  render();
  await act(async () => button(key("confirm")).click());
  expect(document.body.textContent).toContain(key("conflict"));
  expect(state.refetch).toHaveBeenCalledTimes(3);
  expect(state.close).not.toHaveBeenCalled();
  expect(state.success).not.toHaveBeenCalled();
});

it("hides the previous mode estimate until current results arrive", () => {
  render();
  expect(document.body.textContent).toContain(key("preview"));
  state.stale = true;
  state.fetching = true;
  selectInclude();
  expect(document.body.textContent).not.toContain(key("preview"));
  expect(button(key("confirm")).disabled).toBe(true);
  state.stale = false;
  state.fetching = false;
  render();
  expect(button(key("confirm")).disabled).toBe(false);
});
