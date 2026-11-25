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
  apps: [] as Application[],
  query: vi.fn(),
  create: vi.fn(),
  update: vi.fn(),
  conflict: false,
}));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock("../../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useOrganizationApplicationsQuery: (args: unknown, options: unknown) => {
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
import OrganizationApplications from "./OrganizationApplications";
let root: Root;
let host: HTMLDivElement;
const application: Application = {
  id: "uuid",
  organization_id: "org",
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
const render = () => act(() => root.render(<OrganizationApplications organizationId="org" />));
const button = (label: string) =>
  [...document.body.querySelectorAll<HTMLButtonElement>("button")].find((b) => b.textContent?.endsWith(label))!;
const edit = () =>
  act(() => document.body.querySelector<HTMLButtonElement>('[aria-label="rework.applications.editNamed"]')!.click());
function type(label: string, value: string) {
  const element = [...document.body.querySelectorAll("label")].find((l) => l.textContent?.startsWith(label))!;
  const input = document.body.querySelector<HTMLInputElement>(`#${element.htmlFor}`)!;
  Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(input, value);
  input.dispatchEvent(new Event("input", { bubbles: true }));
}
it("loads only the selected organization's registry", () => {
  render();
  expect(h.query).toHaveBeenLastCalledWith(
    { organizationId: "org" },
    expect.objectContaining({ refetchOnMountOrArgChange: true }),
  );
});
it("registers a UI-only application disabled by the server, with read as the default permission", async () => {
  render();
  act(() => button("rework.applications.create").click());
  for (const [field, value] of [
    ["logical_name", "dashboard"],
    ["display_name", "Dashboard"],
    ["ui_base_url", "http://dashboard/apps/dashboard/"],
  ]) {
    if (field === "ui_base_url") act(() => button("rework.applications.sections.connection").click());
    act(() => type(`rework.applications.${field}`, value));
  }
  await act(async () => button("common.save").click());
  expect(h.create).toHaveBeenCalledWith({
    organizationId: "org",
    createApplication: expect.objectContaining({
      logical_name: "dashboard",
      api_base_url: null,
      entry_permission: "read",
    }),
  });
  expect(h.create.mock.calls[0][0].createApplication).not.toHaveProperty("enabled");
  expect(document.body.querySelector('[role="dialog"]')).toBeNull();
});
it("edits settings without changing authorization, preserving translations and revision control", async () => {
  h.apps = [application];
  render();
  edit();
  expect(document.querySelector('[role="dialog"] input[type="checkbox"]')).toBeNull();
  act(() => button("rework.applications.sections.connection").click());
  act(() => type("rework.applications.ui_base_url", "http://new-ui/apps/evaluation/"));
  act(() => button("rework.applications.sections.translations").click());
  const frenchName = document.querySelector<HTMLInputElement>('[aria-labelledby="application-locale-fr"] input')!;
  act(() => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(frenchName, "Évaluer");
    frenchName.dispatchEvent(new Event("input", { bubbles: true }));
  });
  await act(async () => button("common.save").click());
  expect(h.update).toHaveBeenCalledWith({
    organizationId: "org",
    applicationId: "uuid",
    updateApplication: expect.objectContaining({
      expected_revision: 7,
      enabled: false,
      ui_base_url: "http://new-ui/apps/evaluation/",
      entry_permission: "run_evaluations",
      display_name_by_lang: { fr: "Évaluer", de: "Bewertung" },
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
  expect(document.body.querySelector('[role="alert"]')?.textContent).toContain("rework.applications.conflict");
  expect(button("common.save").disabled).toBe(true);
});

it("authorizes directly from the list without opening settings or changing metadata", async () => {
  h.apps = [application];
  render();
  await act(async () =>
    document.querySelector<HTMLInputElement>('[aria-label="rework.applications.authorizeNamed"]')!.click(),
  );
  expect(document.querySelector('[role="dialog"]')).toBeNull();
  expect(h.update).toHaveBeenCalledWith({
    organizationId: "org",
    applicationId: "uuid",
    updateApplication: expect.objectContaining({
      enabled: true,
      expected_revision: 7,
      icon: "widgets",
      ui_base_url: application.ui_base_url,
      entry_permission: "run_evaluations",
      display_name_by_lang: { fr: "Évaluation", de: "Bewertung" },
    }),
  });
  expect(h.update.mock.calls[0][0].updateApplication).not.toHaveProperty("logical_name");
});
it("keeps the server authorization state when a concurrent update fails", async () => {
  h.apps = [{ ...application, enabled: true }];
  h.conflict = true;
  render();
  await act(async () =>
    document.querySelector<HTMLInputElement>('[aria-label="rework.applications.authorizeNamed"]')!.click(),
  );
  expect(document.querySelector<HTMLInputElement>('[aria-label="rework.applications.authorizeNamed"]')!.checked).toBe(
    true,
  );
  expect(document.querySelector('[role="alert"]')?.textContent).toContain("rework.applications.authorizationConflict");
});
it("returns to the missing required field's section instead of silently disabling Save", async () => {
  render();
  act(() => button("rework.applications.create").click());
  act(() => type("rework.applications.display_name", "Evaluation"));
  act(() => type("rework.applications.logical_name", "evaluation"));
  act(() => button("rework.applications.sections.translations").click());
  await act(async () => button("common.save").click());
  expect(document.querySelector('[role="tab"][aria-selected="true"]')?.textContent).toContain(
    "rework.applications.sections.connection",
  );
  expect(document.querySelector('input[aria-invalid="true"]')?.getAttribute("required")).not.toBeNull();
  expect(h.create).not.toHaveBeenCalled();
});
it("offers supported icons visually and saves the selected icon", async () => {
  h.apps = [application];
  render();
  edit();
  const label = [...document.querySelectorAll("label")].find(
    (node) => node.textContent === "rework.applications.icon",
  )!;
  act(() => document.getElementById(label.htmlFor)!.click());
  const option = [...document.querySelectorAll<HTMLElement>('[role="option"]')].find((node) =>
    node.textContent?.endsWith("fact check"),
  )!;
  expect(option).toBeDefined();
  expect(option.textContent).toContain("fact_check");
  act(() => option.click());
  await act(async () => button("common.save").click());
  expect(h.update.mock.calls[0][0].updateApplication.icon).toBe("fact_check");
});
it("preserves an absent API when authorizing a UI-only application", async () => {
  h.apps = [{ ...application, api_base_url: null }];
  render();
  await act(async () =>
    document.querySelector<HTMLInputElement>('[aria-label="rework.applications.authorizeNamed"]')!.click(),
  );
  expect(h.update.mock.calls[0][0].updateApplication.api_base_url).toBeNull();
});

it("saves an application from Enter in a text field without duplicate submissions", async () => {
  h.apps = [application];
  render();
  edit();
  const label = [...document.querySelectorAll("label")].find((item) =>
    item.textContent?.startsWith("rework.applications.display_name"),
  )!;
  const input = label.control!;
  await act(async () => {
    for (let i = 0; i < 2; i++)
      input.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true }));
  });
  expect(h.update).toHaveBeenCalledTimes(1);
  expect(h.update.mock.calls[0][0].updateApplication.enabled).toBe(false);
});
