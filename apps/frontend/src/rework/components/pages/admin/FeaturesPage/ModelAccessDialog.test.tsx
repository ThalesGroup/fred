// @vitest-environment happy-dom
// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { ModelAccessDialog } from "./ModelAccessDialog";
import type { ModelAccessMatrix, StoredModelOffer } from "../../../../../slices/controlPlane/controlPlaneOpenApi";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const h = vi.hoisted(() => ({
  data: undefined as ModelAccessMatrix | undefined,
  error: false,
  fetching: false,
  query: vi.fn(),
  save: vi.fn(),
  refetch: vi.fn(() => ({ unwrap: () => Promise.resolve() })),
  showError: vi.fn(),
  showSuccess: vi.fn(),
}));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock("@shared/molecules/Toast/ToastProvider", () => ({
  useToast: () => ({ showError: h.showError, showSuccess: h.showSuccess }),
}));
vi.mock("../../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useModelAccessMatrixQuery: (args: unknown) => {
    h.query(args);
    return { currentData: h.data, isError: h.error, isFetching: h.fetching, refetch: h.refetch };
  },
  useSetModelAccessMutation: () => [h.save, { isLoading: false }],
}));

let root: Root;
let host: HTMLDivElement;
const prefix = "rework.admin.capabilities.organizationModels.access";
const offer = {
  source_id: "source",
  upstream_model_id: "gpt-6.1-sol",
  metadata: { chat: true },
  selectable: true,
} as StoredModelOffer;
beforeEach(() => {
  h.data = {
    revision: 4,
    organization_permitted: true,
    personal: "default",
    personal_effective: true,
    teams: [
      { team_id: "team-a", name: "Team A", choice: "default", effective: true, locally_disabled: false },
      { team_id: "team-b", name: "Team B", choice: "enabled", effective: false, locally_disabled: true },
    ],
    next_cursor: null,
  };
  h.error = false;
  h.fetching = false;
  h.save.mockImplementation(() => ({ unwrap: () => Promise.resolve() }));
  host = document.createElement("div");
  host.className = "fred-ui";
  document.body.append(host);
  root = createRoot(host);
});
afterEach(() => {
  act(() => root.unmount());
  host.remove();
  vi.clearAllMocks();
});
const render = async () => {
  await act(async () => root.render(<ModelAccessDialog organizationId="org" offer={offer} onClose={() => {}} />));
};
const group = (name: string) => host.querySelector<HTMLElement>(`[role="radiogroup"][aria-label="${name}"]`)!;
const choice = (name: string, position: number) =>
  group(name).querySelectorAll<HTMLButtonElement>('button[role="radio"]')[position];

it("shows teams and the personal class, confirms a restriction and submits its saved revision", async () => {
  await render();
  expect(host.textContent).toContain("Team A");
  expect(host.textContent).toContain(`${prefix}.localRestriction`);
  expect(choice("Team B", 2).getAttribute("aria-checked")).toBe("true");
  expect(choice(`${prefix}.personal`, 1).getAttribute("aria-checked")).toBe("true");
  await act(async () => choice(`${prefix}.personal`, 0).click());
  expect(h.save).not.toHaveBeenCalled();
  const confirmation = document.body.querySelector('[role="alertdialog"]')!;
  expect(confirmation.textContent).toContain(`${prefix}.disableWarning`);
  await act(async () =>
    [...confirmation.querySelectorAll<HTMLButtonElement>("button")]
      .find((button) => button.textContent === "common.confirm")!
      .click(),
  );
  expect(h.save).toHaveBeenCalledExactlyOnceWith({
    organizationId: "org",
    sourceId: "source",
    setModelAccess: { expected_revision: 4, upstream_model_id: "gpt-6.1-sol", team_id: null, choice: "disabled" },
  });
  expect(h.refetch).toHaveBeenCalled();
});

it("can explicitly enable a team and follows inheritance without claiming to remove local restrictions", async () => {
  await render();
  await act(async () => choice("Team A", 2).click());
  expect(h.save).toHaveBeenLastCalledWith({
    organizationId: "org",
    sourceId: "source",
    setModelAccess: { expected_revision: 4, upstream_model_id: "gpt-6.1-sol", team_id: "team-a", choice: "enabled" },
  });
  await act(async () => choice("Team B", 1).click());
  expect(h.save).toHaveBeenLastCalledWith({
    organizationId: "org",
    sourceId: "source",
    setModelAccess: { expected_revision: 4, upstream_model_id: "gpt-6.1-sol", team_id: "team-b", choice: "default" },
  });
  expect(host.textContent).toContain(`${prefix}.localRestriction`);
});

it("cannot grant a model beyond the organization ceiling and distinguishes a query failure", async () => {
  h.data!.organization_permitted = false;
  h.data!.personal_effective = false;
  await render();
  expect(host.textContent).toContain(`${prefix}.organizationDenied`);
  expect(choice("Team A", 2).disabled).toBe(true);
  expect(choice("Team A", 1).disabled).toBe(false);
  h.error = true;
  await render();
  expect(host.querySelector('[role="alert"]')?.textContent).toContain("rework.manager.unavailable");
  expect(host.textContent).not.toContain("matrix.searchEmpty");
  expect(host.querySelector('[role="radiogroup"]')).toBeNull();
});

it("uses the paged team query and resets its cursor when filtering", async () => {
  h.data!.next_cursor = "next-team";
  await render();
  await act(async () =>
    [...host.querySelectorAll<HTMLButtonElement>("button")]
      .find((button) => button.textContent === "dataTable.pagination.next")!
      .click(),
  );
  expect(h.query).toHaveBeenLastCalledWith(expect.objectContaining({ after: "next-team" }));
  const input = host.querySelector<HTMLInputElement>(`input[aria-label="${prefix}.filter"]`)!;
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(input, "Team A");
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
  expect(h.query).toHaveBeenLastCalledWith(expect.objectContaining({ name: "Team A", after: undefined }));
});

it("reports a revision conflict and refetches before another edit", async () => {
  h.save.mockImplementationOnce(() => ({
    unwrap: () => Promise.reject({ status: 409, data: { detail: "Model policy changed" } }),
  }));
  await render();
  await act(async () => choice("Team A", 2).click());
  expect(h.showError).toHaveBeenCalledWith(expect.objectContaining({ detail: "Model policy changed" }));
  expect(h.refetch).toHaveBeenCalled();
});
