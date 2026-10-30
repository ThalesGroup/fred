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
  result: { isLoading: false },
  submit: vi.fn(),
  update: vi.fn(),
  detail: { currentData: undefined as unknown, isError: false, error: undefined as unknown },
  detailQuery: vi.fn(),
  showError: vi.fn(),
  query: vi.fn(),
  showSuccess: vi.fn(),
}));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string, args?: { name: string }) => (args?.name ? `${key} ${args.name}` : key) }),
}));
vi.mock("@core/hooks/useManagerPlatformAdmin", () => ({ useManagerPlatformAdmin: () => h.access }));
vi.mock("@shared/molecules/Toast/ToastProvider", () => ({
  useToast: () => ({ showSuccess: h.showSuccess, showError: h.showError }),
}));
vi.mock("../../../../../slices/controlPlane/controlPlaneApiEnhancements", async () => {
  const { useEffect, useState } = await import("react");
  return {
    useOrganizationRegistryQuery: (args, options) => {
      h.query(args, options);
      return h.registry;
    },
    useCreateOrganizationMutation: () => [h.submit, h.result],
    useUpdateOrganizationMutation: () => [h.update, { isLoading: false }],
    // A cold cache: the detail arrives from a request made after the dialog mounted.
    useGetOrganizationQuery: (args, options) => {
      h.detailQuery(args, options);
      const [fetched, setFetched] = useState(false);
      useEffect(() => setFetched(true), []);
      if (options.skip) return { currentData: undefined, isError: false };
      return fetched ? { ...h.detail, requestId: "this-open" } : { currentData: undefined, isFetching: true };
    },
    useSearchOrganizationCandidatesQuery: ({ query }, { skip }) => ({
      currentData: skip ? undefined : [{ id: query, username: query, first_name: query, last_name: "" }],
      isFetching: false,
      isError: false,
    }),
  };
});
vi.mock("@shared/molecules/Dialog/Dialog", () => ({
  Dialog: ({ title, children, confirmLabel, confirmDisabled, onConfirm }) => (
    <div role="dialog" aria-label={title}>
      {children}
      <button type="button" disabled={confirmDisabled} onClick={onConfirm}>
        {confirmLabel}
      </button>
    </div>
  ),
}));
vi.mock("@shared/molecules/Autocomplete/Autocomplete", () => ({
  default: ({ textInput, onFieldValueChange, options, onSelect }) => (
    <div>
      <input
        placeholder={textInput.placeholder}
        aria-label={textInput["aria-label"]}
        onChange={(event) => onFieldValueChange(event.target.value)}
      />
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
const OPEN = "rework.organizations.createOrganization.open";
const SUBMIT = "rework.organizations.createOrganization.submit";
const SAVE = "rework.organizations.editOrganization.submit";
const user = (name: string) => ({ id: name, username: name, first_name: name, last_name: "" });
const DETAIL = { organization: { id: "a", name: "Demo" }, admins: [user("olivia")], owners: [user("adam")] };
beforeEach(() => {
  vi.clearAllMocks();
  Object.assign(h.access, { isAdmin: true, isLoading: false, isFetching: false, isError: false });
  Object.assign(h.registry, {
    currentData: { items: [{ id: "a", name: "Demo" }], next_cursor: null },
    isError: false,
    isFetching: false,
  });
  h.result.isLoading = false;
  Object.assign(h.detail, { currentData: DETAIL, isError: false, error: undefined });
  h.update.mockReturnValue({
    unwrap: () => Promise.resolve({ ...DETAIL, organization: { id: "a", name: "Renamed" } }),
  });
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
const button = (label: string) => [...host.querySelectorAll("button")].find((b) => b.textContent?.endsWith(label));
const dialog = () => host.querySelector('[role="dialog"]');
function type(input: HTMLInputElement, value: string) {
  Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(input, value);
  input.dispatchEvent(new Event("input", { bubbles: true }));
}
function openAndFill() {
  act(() => button(OPEN)!.click());
  act(() => type(dialog()!.querySelector("input")!, " New Org "));
  for (const who of ["admin", "owner"]) {
    const label = `rework.organizations.${who}`;
    act(() => type(dialog()!.querySelector<HTMLInputElement>(`input[aria-label="${label}"]`)!, who));
    act(() => button(`Select ${who}`)!.click());
  }
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
it("hides the create button and skips the registry when platform adminship is absent", () => {
  h.access.isAdmin = false;
  render();
  expect(button(OPEN)).toBeUndefined();
  expect(h.query).toHaveBeenLastCalledWith({ after: undefined }, expect.objectContaining({ skip: true }));
});
it("creates from the dialog, closes it and resets to the first page", async () => {
  h.registry.currentData.next_cursor = "next";
  render();
  expect(dialog()).toBeNull();
  act(() => button("dataTable.pagination.next")!.click());
  expect(h.query).toHaveBeenLastCalledWith({ after: "next" }, expect.anything());
  openAndFill();
  await act(async () => button(SUBMIT)!.click());
  expect(h.submit).toHaveBeenCalledExactlyOnceWith({
    createOrganization: { name: "New Org", admin_username: "admin", owner_username: "owner" },
  });
  expect(h.query).toHaveBeenLastCalledWith({ after: undefined }, expect.anything());
  expect(h.showSuccess).toHaveBeenCalledWith({
    summary: "rework.organizations.createOrganization.successSummary New Org",
  });
  expect(dialog()).toBeNull();
});
it("keeps submit disabled until every field is set and while a creation runs", () => {
  render();
  act(() => button(OPEN)!.click());
  expect(button(SUBMIT)!.disabled).toBe(true);
  act(() => root.unmount());
  root = createRoot(host);
  h.result.isLoading = true;
  render();
  openAndFill();
  expect(button(SUBMIT)!.disabled).toBe(true);
});
it("reports failure through the error toast and keeps the dialog open", async () => {
  const error = { status: 409, data: { detail: "already exists", code: "conflict" } };
  h.submit.mockReturnValue({ unwrap: () => Promise.reject(error) });
  render();
  openAndFill();
  await act(async () => button(SUBMIT)!.click());
  expect(h.showError).toHaveBeenCalledWith({
    summary: "rework.organizations.createOrganization.errors.summary",
    detail: "rework.organizations.createOrganization.errors.conflictDetail",
  });
  expect(h.showSuccess).not.toHaveBeenCalled();
  expect(dialog()).not.toBeNull();
});
const openEdit = () =>
  act(() =>
    host
      .querySelector<HTMLButtonElement>('[aria-label="rework.organizations.editOrganization.openAria Demo"]')!
      .click(),
  );
const nameInput = () => dialog()!.querySelector<HTMLInputElement>("input")!;
it("opens the edit pre-filled from the organization's detail, with nothing to save yet", () => {
  render();
  openEdit();
  expect(h.detailQuery).toHaveBeenLastCalledWith({ id: "a" }, expect.objectContaining({ skip: false }));
  expect(nameInput().value).toBe("Demo");
  expect(dialog()!.textContent).toContain("(olivia)");
  expect(dialog()!.textContent).toContain("(adam)");
  expect(button(SAVE)!.disabled).toBe(true);
  act(() => type(nameInput(), " Demo "));
  expect(button(SAVE)!.disabled).toBe(true);
});
it("shows a loading state until the detail arrives", () => {
  h.detail.currentData = undefined;
  render();
  openEdit();
  expect(dialog()!.textContent).toContain("common.loading");
  expect(button(SAVE)!.disabled).toBe(true);
  h.detail.error = { status: 404, data: { detail: "not found" } };
  h.detail.isError = true;
  render();
  expect(dialog()!.textContent).toContain("rework.organizations.editOrganization.errors.notFoundDetail");
});
it("sends only the changed fields, then closes without reloading the list", async () => {
  render();
  openEdit();
  act(() => type(nameInput(), "Renamed"));
  act(() =>
    [...dialog()!.querySelectorAll("button")].find((b) => b.getAttribute("aria-label")?.includes("adam"))!.click(),
  );
  act(() => type(dialog()!.querySelector<HTMLInputElement>('input[aria-label="rework.organizations.owner"]')!, "zoe"));
  act(() => button("Select zoe")!.click());
  await act(async () => button(SAVE)!.click());
  expect(h.update).toHaveBeenCalledExactlyOnceWith({
    id: "a",
    updateOrganization: { name: "Renamed", owner_username: "zoe" },
  });
  expect(h.showSuccess).toHaveBeenCalledWith({
    summary: "rework.organizations.editOrganization.successSummary Renamed",
  });
  expect(h.registry.refetch).not.toHaveBeenCalled();
  expect(dialog()).toBeNull();
});
it("keeps the edit open and explains a refusal in plain words", async () => {
  const error = { status: 409, data: { detail: "the user already belongs to another organization", code: "conflict" } };
  h.update.mockReturnValue({ unwrap: () => Promise.reject(error) });
  render();
  openEdit();
  act(() => type(nameInput(), "Renamed"));
  await act(async () => button(SAVE)!.click());
  expect(h.showError).toHaveBeenCalledWith({
    summary: "rework.organizations.editOrganization.errors.summary",
    detail: "rework.organizations.editOrganization.errors.conflictDetail",
  });
  expect(h.showSuccess).not.toHaveBeenCalled();
  expect(dialog()).not.toBeNull();
});
