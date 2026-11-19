// @vitest-environment happy-dom
// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import type {
  Application,
  CreateApplicationApiArg,
  UpdateApplicationApiArg,
} from "../../../../../slices/controlPlane/controlPlaneOpenApi";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const h = vi.hoisted(() => ({
  admin: true,
  apps: [] as Application[],
  query: vi.fn(),
  create: vi.fn(),
  update: vi.fn(),
  conflict: false,
}));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock("@core/hooks/useManagerPlatformAdmin", () => ({
  useManagerPlatformAdmin: () => ({ isAdmin: h.admin, currentData: {} }),
}));
vi.mock("../../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  usePlatformApplicationsQuery: (args: unknown, options: unknown) => {
    h.query(args, options);
    return { currentData: h.apps };
  },
  useCreateApplicationMutation: () => [
    (args: CreateApplicationApiArg) => ({
      unwrap: async () => {
        h.create(args);
      },
    }),
    { isLoading: false },
  ],
  useUpdateApplicationMutation: () => [
    (args: UpdateApplicationApiArg) => ({
      unwrap: async () => {
        h.update(args);
        if (h.conflict) throw { status: 409 };
      },
    }),
    { isLoading: false },
  ],
}));
vi.mock("@shared/molecules/Dialog/Dialog", () => ({
  Dialog: ({ children, confirmLabel, confirmDisabled, onConfirm, onCancel }) => (
    <div role="dialog">
      {children}
      <button disabled={confirmDisabled} onClick={onConfirm}>
        {confirmLabel}
      </button>
      <button onClick={onCancel}>Cancel</button>
    </div>
  ),
}));
import PlatformApplicationsPage from "./PlatformApplicationsPage";
let root: Root;
let host: HTMLDivElement;
const application: Application = {
  id: "uuid",
  logical_name: "evaluation",
  display_name: "Evaluation",
  description: "Review agents",
  icon: "widgets",
  version: "1.0.0",
  display_name_by_lang: { fr: "Évaluation", de: "Bewertung" },
  description_by_lang: {},
  ui_base_url: "http://evaluation-ui/apps/evaluation/",
  api_base_url: "http://evaluation-api/",
  entry_permission: "run_evaluations",
  enabled: false,
  revision: 7,
  source_id: "$applications",
  capability_id: "application:uuid",
};
beforeEach(() => {
  h.admin = true;
  h.apps = [];
  h.conflict = false;
  h.query.mockClear();
  h.create.mockClear();
  h.update.mockClear();
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
});
afterEach(() => {
  act(() => root.unmount());
  host.remove();
});
const render = () => act(() => root.render(<PlatformApplicationsPage />));
const button = (label: string) =>
  [...host.querySelectorAll<HTMLButtonElement>("button")].find((b) => b.textContent?.endsWith(label))!;
const edit = () =>
  act(() => host.querySelector<HTMLButtonElement>('[aria-label="rework.applications.editNamed"]')!.click());
function type(label: string, value: string) {
  const element = [...host.querySelectorAll("label")].find((l) => l.textContent?.startsWith(label))!;
  const input = host.querySelector<HTMLInputElement>(`#${element.htmlFor}`)!;
  Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(input, value);
  input.dispatchEvent(new Event("input", { bubbles: true }));
}
it("keeps the registry and creation unavailable to a non-platform admin", () => {
  h.admin = false;
  render();
  expect(h.query).toHaveBeenLastCalledWith(undefined, expect.objectContaining({ skip: true }));
  expect(host.textContent).toContain("rework.provisioning.forbidden");
  expect(host.querySelector("button")).toBeNull();
});
it("registers a UI-only application disabled by the server, with read as the default permission", async () => {
  render();
  act(() => button("rework.applications.create").click());
  for (const [field, value] of [
    ["logical_name", "dashboard"],
    ["display_name", "Dashboard"],
    ["ui_base_url", "http://dashboard/apps/dashboard/"],
  ])
    act(() => type(`rework.applications.${field}`, value));
  await act(async () => button("common.save").click());
  expect(h.create).toHaveBeenCalledWith({
    createApplication: expect.objectContaining({
      logical_name: "dashboard",
      api_base_url: null,
      entry_permission: "read",
    }),
  });
  expect(h.create.mock.calls[0][0].createApplication).not.toHaveProperty("enabled");
  expect(host.querySelector('[role="dialog"]')).toBeNull();
});
it("edits destinations and enables an app with revision control, preserving untranslated labels", async () => {
  h.apps = [application];
  render();
  edit();
  act(() => host.querySelector<HTMLInputElement>('[aria-label="rework.applications.enabled"]')!.click());
  await act(async () => button("common.save").click());
  expect(h.update).toHaveBeenCalledWith({
    applicationId: "uuid",
    updateApplication: expect.objectContaining({
      expected_revision: 7,
      enabled: true,
      entry_permission: "run_evaluations",
      display_name_by_lang: { fr: "Évaluation", de: "Bewertung" },
    }),
  });
  expect(h.update.mock.calls[0][0].updateApplication).not.toHaveProperty("logical_name");
});
it("keeps a stale edit open and requires reloading its revision", async () => {
  h.apps = [application];
  h.conflict = true;
  render();
  edit();
  await act(async () => button("common.save").click());
  expect(host.querySelector('[role="alert"]')?.textContent).toContain("rework.applications.conflict");
  expect(button("common.save").disabled).toBe(true);
});
