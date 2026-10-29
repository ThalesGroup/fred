// @vitest-environment happy-dom
// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

// The dialog against the real generated client and store; fetch is stubbed, and the
// dialog shell and search field are reduced to plain elements.
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { Provider } from "react-redux";
import { configureStore } from "@reduxjs/toolkit";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

const h = vi.hoisted(() => ({ showError: vi.fn(), showSuccess: vi.fn() }));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, args?: Record<string, string>) => (args ? `${key} ${Object.values(args).join(" ")}` : key),
  }),
}));
vi.mock("../../../../../security/KeycloakService", () => ({
  KeyCloakService: {
    GetToken: () => "operator-token",
    GetUserId: () => "operator",
    GetSessionIdentity: () => "fixture/operator",
    ensureFreshToken: vi.fn().mockResolvedValue(true),
    CallLogout: vi.fn(),
  },
}));
vi.mock("../../../../../common/platformAccess", () => ({ handlePlatformAccessDenial: vi.fn() }));
vi.mock("@shared/molecules/Toast/ToastProvider", () => ({
  useToast: () => ({ showSuccess: h.showSuccess, showError: h.showError }),
}));
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
      <input aria-label={textInput["aria-label"]} onChange={(event) => onFieldValueChange(event.target.value)} />
      {options.map((option) => (
        <button type="button" key={option.key} onClick={() => onSelect(option.value)}>
          Select {option.key}
        </button>
      ))}
    </div>
  ),
}));

import { enhancedControlPlaneApi as api } from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import type { OrganizationDetail, Space, UserSummary } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import OrganizationFormDialog from "./OrganizationFormDialog";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const SAVE = "rework.organizations.editOrganization.submit";
const ORG = { id: "a", name: "Demo" } as Space;
const person = (id: string, username: string | null = id): UserSummary => ({
  id,
  username,
  first_name: null,
  last_name: null,
  email: null,
  avatar_image_url: null,
});
const detail = (name: string, owners = [person("olivia")], admins = [person("adam")]): OrganizationDetail => ({
  organization: { ...ORG, name },
  owners,
  admins,
});
const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

const NativeRequest = globalThis.Request;
let replies: ((request: Request) => Promise<Response>)[];
let requests: Request[];
let store: ReturnType<typeof makeStore>;
let host: HTMLDivElement;
let root: Root;
const makeStore = () =>
  configureStore({
    reducer: { [api.reducerPath]: api.reducer },
    middleware: (defaults) => defaults().concat(api.middleware),
  });

beforeEach(() => {
  vi.stubGlobal(
    "Request",
    class extends NativeRequest {
      constructor(input: RequestInfo | URL, init?: RequestInit) {
        super(typeof input === "string" ? new URL(input, "http://localhost") : input, init);
      }
    },
  );
  replies = [];
  requests = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (request: Request) => {
      requests.push(request);
      return replies.shift()!(request);
    }),
  );
  store = makeStore();
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
});
afterEach(() => {
  act(() => root.unmount());
  host.remove();
  store.dispatch(api.util.resetApiState());
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

const open = (organization: Space | undefined, onClose = () => {}) =>
  act(() =>
    root.render(
      <Provider store={store}>
        <OrganizationFormDialog organization={organization} onSaved={() => {}} onClose={onClose} />
      </Provider>,
    ),
  );
const close = () => act(() => root.render(<Provider store={store}>{null}</Provider>));
const dialog = () => host.querySelector('[role="dialog"]')!;
const nameInput = () => dialog().querySelector<HTMLInputElement>("input");
const save = () => [...host.querySelectorAll("button")].find((b) => b.textContent === SAVE)!;
function type(input: HTMLInputElement, value: string) {
  Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(input, value);
  input.dispatchEvent(new Event("input", { bubbles: true }));
}
async function waitForForm() {
  await act(() => vi.waitFor(() => expect(nameInput()).not.toBeNull()));
}

it("reopened within the cache lifetime, pre-fills from this open's fetch, not the cached copy", async () => {
  replies.push(async () => json(detail("Demo")));
  open(ORG);
  await waitForForm();
  act(() => type(nameInput()!, "Renamed"));
  replies.push(async () => json(detail("Renamed")));
  await act(async () => save().click());
  expect(requests[1].method).toBe("PATCH");
  // The committed detail replaces the cached one.
  expect(api.endpoints.getOrganization.select({ id: "a" })(store.getState()).data?.organization.name).toBe("Renamed");
  close();
  let release!: (response: Response) => void;
  replies.push(() => new Promise((resolve) => (release = resolve)));
  open(ORG);
  await act(() => vi.waitFor(() => expect(requests).toHaveLength(3)));
  // The refetch is in flight: no form yet, even though a cached detail exists.
  expect(nameInput()).toBeNull();
  expect(dialog().textContent).toContain("common.loading");
  await act(async () => release(json(detail("Renamed elsewhere"))));
  await waitForForm();
  expect(nameInput()!.value).toBe("Renamed elsewhere");
});

it("names a holder the directory no longer describes by id, and still saves a rename", async () => {
  replies.push(async () => json(detail("Demo", [person("subject-1", null)], [person("adam")])));
  open(ORG);
  await waitForForm();
  expect(dialog().textContent).toContain("subject-1");
  expect(dialog().textContent).not.toContain("null");
  act(() => type(nameInput()!, "Renamed"));
  expect(save().disabled).toBe(false);
  replies.push(async () => json(detail("Renamed", [person("subject-1", null)])));
  await act(async () => save().click());
  expect(await requests[1].json()).toEqual({ name: "Renamed" });
});

it("warns that a new holder replaces every current one", async () => {
  replies.push(async () => json(detail("Demo", [person("olivia"), person("oscar")])));
  open(ORG);
  await waitForForm();
  const notes = [...dialog().querySelectorAll('[role="note"]')].map((n) => n.textContent);
  expect(notes).toEqual(["rework.organizations.editOrganization.severalOwners olivia, oscar"]);
});

it.each([
  [403, "forbidden", "forbiddenDetail"],
  [422, "unprocessable", "validationDetail"],
  [409, "conflict", "conflictDetail"],
  [409, "space_pending_deletion", "retiredDetail"],
  [404, "not_found", "notFoundDetail"],
  [500, "internal", "fallbackDetail"],
])("shows our wording, never the server detail, for an edit refused with %i %s", async (status, code, key) => {
  replies.push(async () => json(detail("Demo")));
  open(ORG);
  await waitForForm();
  act(() => type(nameInput()!, "Renamed"));
  replies.push(async () => json({ detail: "server says no", code }, status));
  await act(async () => save().click());
  await act(() => vi.waitFor(() => expect(h.showError).toHaveBeenCalled()));
  expect(h.showError).toHaveBeenCalledExactlyOnceWith({
    summary: "rework.organizations.editOrganization.errors.summary",
    detail: `rework.organizations.editOrganization.errors.${key}`,
  });
});

it.each([
  [403, "forbiddenDetail"],
  [422, "validationDetail"],
  [409, "conflictDetail"],
  [503, "fallbackDetail"],
])("shows our wording, never the server detail, for a creation refused with %i", async (status, key) => {
  open(undefined);
  act(() => type(nameInput()!, "New"));
  for (const who of ["owner", "admin"]) {
    const field = dialog().querySelector<HTMLInputElement>(`input[aria-label="rework.organizations.${who}"]`)!;
    replies.push(async () => json([person(who)]));
    act(() => type(field, who));
    const option = await act(() =>
      vi.waitFor(() => {
        const found = [...host.querySelectorAll("button")].find((b) => b.textContent === `Select ${who}`);
        expect(found).toBeDefined();
        return found!;
      }),
    );
    act(() => option.click());
  }
  replies.push(async () => json({ detail: "server says no", code: "x" }, status));
  await act(async () => [...host.querySelectorAll("button")].find((b) => b.textContent?.endsWith("submit"))!.click());
  await act(() => vi.waitFor(() => expect(h.showError).toHaveBeenCalled()));
  expect(h.showError).toHaveBeenCalledExactlyOnceWith({
    summary: "rework.organizations.createOrganization.errors.summary",
    detail: `rework.organizations.createOrganization.errors.${key}`,
  });
});
