// @vitest-environment happy-dom
// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
const h = vi.hoisted(() => ({
  access: { isAdmin: true, isLoading: false, isFetching: false, isError: false, refetch: vi.fn() },
  registry: {
    currentData: { items: [{ id: "a", name: "Demo" }], next_cursor: null as string | null },
    isError: false,
    isFetching: false,
    refetch: vi.fn(),
  },
  result: { isLoading: false, error: undefined as unknown },
  submit: vi.fn(),
  query: vi.fn(),
}));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string, args?: { name: string }) => (args?.name ? `${key} ${args.name}` : key) }),
}));
vi.mock("@core/hooks/useManagerPlatformAdmin", () => ({ useManagerPlatformAdmin: () => h.access }));
vi.mock("../../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useOrganizationRegistryQuery: (args, options) => {
    h.query(args, options);
    return h.registry;
  },
  useCreateOrganizationMutation: () => [h.submit, h.result],
  useSearchOrganizationCandidatesQuery: ({ query }, { skip }) => ({
    currentData: skip ? undefined : [{ id: query, username: query, first_name: query, last_name: "" }],
    isFetching: false,
    isError: false,
  }),
}));
vi.mock("@shared/molecules/Autocomplete/Autocomplete", () => ({
  default: ({ textInput, onFieldValueChange, options, onSelect }) => (
    <div>
      <input {...textInput} onChange={(event) => onFieldValueChange(event.target.value)} />
      {options.map((option) => (
        <button type="button" key={option.key} onClick={() => onSelect(option.value)}>
          Select {option.key}
        </button>
      ))}
    </div>
  ),
}));
import OrganizationsPage from "./OrganizationsPage";
let host: HTMLDivElement;
let root: Root;
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
beforeEach(() => {
  vi.clearAllMocks();
  Object.assign(h.access, { isAdmin: true, isLoading: false, isFetching: false, isError: false });
  Object.assign(h.registry, {
    currentData: { items: [{ id: "a", name: "Demo" }], next_cursor: null },
    isError: false,
    isFetching: false,
  });
  Object.assign(h.result, { isLoading: false, error: undefined });
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
  h.submit.mockReturnValue({ unwrap: () => Promise.resolve({ id: "new", name: "New Org" }) });
});
afterEach(() => {
  act(() => root.unmount());
  host.remove();
});
function render() {
  act(() => root.render(<OrganizationsPage />));
}
function fill() {
  act(() => {
    const inputs = host.querySelectorAll("input");
    [" New Org ", " owner ", " admin "].forEach((value, i) => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(inputs[i], value);
      inputs[i].dispatchEvent(new Event("input", { bubbles: true }));
    });
  });
  act(() => {
    for (const label of ["Select owner", "Select admin"]) {
      [...host.querySelectorAll("button")].find((button) => button.textContent === label)!.click();
    }
  });
}
function submit() {
  host.querySelector("form")!.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
}
it("distinguishes unavailable, loading and successful empty lists without stale rows", () => {
  render();
  expect(host.textContent).toContain("Demo");
  h.registry.isError = true;
  render();
  expect(host.textContent).not.toContain("Demo");
  expect(host.textContent).toContain("rework.organizations.loadFailed");
  h.registry.isError = false;
  h.registry.isFetching = true;
  render();
  expect(host.textContent).not.toContain("Demo");
  expect(host.textContent).toContain("common.loading");
  h.registry.isFetching = false;
  h.registry.currentData.items = [];
  render();
  expect(host.textContent).toContain("rework.organizations.empty");
});
it("skips registry and form when platform ownership is absent", () => {
  h.access.isAdmin = false;
  render();
  expect(host.querySelector("form")).toBeNull();
  expect(h.query).toHaveBeenLastCalledWith({ after: undefined }, expect.objectContaining({ skip: true }));
});
it("uses cursor pages and resets to the first after confirmed creation", async () => {
  h.registry.currentData.next_cursor = "next";
  render();
  act(() => [...host.querySelectorAll("button")].find((b) => b.textContent === "dataTable.pagination.next")!.click());
  expect(h.query).toHaveBeenLastCalledWith({ after: "next" }, expect.anything());
  fill();
  await act(async () => submit());
  expect(h.submit).toHaveBeenCalledExactlyOnceWith({
    createOrganization: { name: "New Org", owner_username: "owner", admin_username: "admin" },
  });
  expect(h.query).toHaveBeenLastCalledWith({ after: undefined }, expect.anything());
  expect(host.textContent).toContain("rework.organizations.created New Org");
});
it("prevents duplicate submits and ignores success after unmount", async () => {
  let resolve!: (value: unknown) => void;
  h.submit.mockReturnValue({
    unwrap: () =>
      new Promise((done) => {
        resolve = done;
      }),
  });
  render();
  fill();
  act(() => {
    submit();
    submit();
  });
  expect(h.submit).toHaveBeenCalledOnce();
  act(() => root.render(<p>Another account</p>));
  await act(async () => resolve({ name: "Old" }));
  expect(host.textContent).toBe("Another account");
  expect(h.registry.refetch).not.toHaveBeenCalled();
});
it("reports failure without automatic replay or successful creation", () => {
  h.result.error = { status: 409, data: { detail: "already attached" } };
  render();
  expect(host.querySelector('[role="alert"]')?.textContent).toContain("already attached");
  expect(host.textContent).not.toContain("rework.organizations.created");
  expect(h.submit).not.toHaveBeenCalled();
});
