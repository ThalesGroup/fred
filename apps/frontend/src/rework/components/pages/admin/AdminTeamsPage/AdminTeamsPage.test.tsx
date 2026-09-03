// @vitest-environment happy-dom
// Copyright Thales 2026
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

// Team deletion has no undo on the backend, so the guarantee under test is
// that the request cannot leave the client unconfirmed. The real
// ConfirmationDialogProvider is mounted rather than stubbed, so the
// assertions run against the dialog users actually see.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const h = vi.hoisted(() => ({
  /** Every team id the delete mutation was fired for, in call order. */
  deleted: [] as string[],
  deleteFails: false,
  errors: [] as string[],
  successes: [] as string[],
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) => (opts?.name ? `${key}:${String(opts.name)}` : key),
    i18n: { language: "en" },
  }),
}));

vi.mock("../../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useListUsersQuery: () => ({ data: [] }),
  useListAllTeamsQuery: () => ({
    data: [
      { id: "team-a", name: "Swiftpost", admins: [] },
      { id: "team-b", name: "Fredlab", admins: [] },
    ],
  }),
  useCreateTeamMutation: () => [vi.fn(), { isLoading: false }],
  // The request leaves on the trigger call, not on `unwrap()`. Recording it
  // there is what makes "no request without a confirm" a real assertion
  // rather than an assertion about awaiting.
  useDeleteTeamMutation: () => [
    (args: { teamId: string }) => {
      h.deleted.push(args.teamId);
      return {
        unwrap: async () => {
          if (h.deleteFails) throw new Error("boom");
          return null;
        },
      };
    },
    { isLoading: false },
  ],
}));

vi.mock("@shared/molecules/Toast/ToastProvider", () => ({
  useToast: () => ({
    showSuccess: (arg: { summary?: string }) => h.successes.push(arg?.summary ?? ""),
    showError: (arg: { summary?: string }) => h.errors.push(arg?.summary ?? ""),
    showWarn: vi.fn(),
    showInfo: vi.fn(),
  }),
}));

const { default: AdminTeamsPage } = await import("./AdminTeamsPage");
const { ConfirmationDialogProvider } = await import("@shared/molecules/ConfirmationDialog/ConfirmationDialogProvider");

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  h.deleted = [];
  h.deleteFails = false;
  h.errors = [];
  h.successes = [];
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

// The dialog renders through `<Portal id="modal-portal">`, i.e. outside the
// test container, so it is queried from the document.
const dialog = () => document.querySelector('[role="alertdialog"]');

const deleteButton = (teamName: string) =>
  container.querySelector<HTMLElement>(`button[aria-label="rework.adminTeams.deleteTeam.action:${teamName}"]`);

const dialogButton = (label: string) =>
  Array.from(document.querySelectorAll<HTMLElement>('[role="alertdialog"] button')).find(
    (b) => b.textContent?.trim() === label,
  );

function render() {
  act(() =>
    root.render(
      <ConfirmationDialogProvider>
        <AdminTeamsPage />
      </ConfirmationDialogProvider>,
    ),
  );
}

describe("AdminTeamsPage team deletion", () => {
  it("never deletes on the bare click - the dialog intercepts it", () => {
    render();
    const button = deleteButton("Swiftpost");
    expect(button, "each team row carries a delete action").toBeTruthy();

    act(() => button!.click());

    expect(h.deleted).toEqual([]);
    expect(dialog()).not.toBeNull();
  });

  it("names the team in both the title and the consequences copy", () => {
    render();
    act(() => deleteButton("Swiftpost")!.click());

    expect(dialog()!.textContent).toContain("rework.adminTeams.deleteTeam.dialogTitle:Swiftpost");
    expect(dialog()!.textContent).toContain("rework.adminTeams.deleteTeam.dialogMessage:Swiftpost");
  });

  it("deletes only the confirmed team", async () => {
    render();
    act(() => deleteButton("Fredlab")!.click());
    await act(async () => dialogButton("rework.adminTeams.deleteTeam.confirm")!.click());

    expect(h.deleted).toEqual(["team-b"]);
    expect(h.successes).toEqual(["rework.adminTeams.deleteTeam.successSummary"]);
    expect(dialog()).toBeNull();
  });

  it("cancelling fires no request", async () => {
    render();
    act(() => deleteButton("Swiftpost")!.click());
    await act(async () => dialogButton("rework.adminTeams.deleteTeam.cancel")!.click());

    expect(h.deleted).toEqual([]);
    expect(dialog()).toBeNull();
  });

  it("surfaces a failed deletion as an error toast", async () => {
    h.deleteFails = true;
    render();
    act(() => deleteButton("Swiftpost")!.click());
    await act(async () => dialogButton("rework.adminTeams.deleteTeam.confirm")!.click());

    expect(h.deleted).toEqual(["team-a"]);
    expect(h.successes).toEqual([]);
    expect(h.errors).toEqual(["rework.adminTeams.deleteTeam.errors.summary"]);
  });
});
