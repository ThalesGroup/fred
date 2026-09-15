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

// One role goes to every picked user; a user whose grant failed stays picked.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const h = vi.hoisted(() => ({
  users: [
    { id: "u-alice", username: "alice", first_name: "Alice", last_name: "Watson" },
    { id: "u-bob", username: "bob", first_name: "Bob", last_name: "Durand" },
    { id: "u-carol", username: "carol", first_name: "Carol", last_name: "Diaz" },
  ],
  grantRole: vi.fn(),
  showSuccess: vi.fn(),
  notifyApiError: vi.fn(),
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en" } }),
}));

vi.mock("@shared/molecules/Toast/ToastProvider", () => ({
  useToast: () => ({ showSuccess: h.showSuccess, showError: vi.fn() }),
}));

vi.mock("@core/hooks/useApiErrorToast.ts", () => ({
  useApiErrorToast: () => ({ notifyApiError: h.notifyApiError }),
}));

vi.mock("../../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  usePlatformRolesQuery: () => ({
    data: { holders: [], caller_is_bootstrap_root: true },
    isLoading: false,
    isError: false,
  }),
  useListUsersQuery: () => ({ data: h.users }),
  useGrantPlatformRoleMutation: () => [h.grantRole],
  useRevokePlatformRoleMutation: () => [vi.fn()],
}));

import PlatformRolesPage from "./PlatformRolesPage";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

let container: HTMLDivElement;
let root: Root;

const input = () => container.querySelector("input") as HTMLInputElement;
// Chip labels only: the suggestion menu renders list items too.
const pickedNames = () =>
  Array.from(container.querySelectorAll("span[title]"))
    .filter((label) => !label.closest('[role="option"]'))
    .map((label) => label.textContent);
const submit = () =>
  Array.from(container.querySelectorAll("button")).find((button) =>
    button.textContent?.includes("rework.platformRoles.grant.submit"),
  ) as HTMLButtonElement;

// Picks the first suggestion, which is the first user not picked yet.
function pickNextUser() {
  act(() => input().blur());
  act(() => input().focus());
  act(() => {
    input().dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true }));
  });
}

beforeEach(() => {
  h.grantRole.mockReset();
  h.showSuccess.mockReset();
  h.notifyApiError.mockReset();
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => root.render(<PlatformRolesPage />));
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

describe("PlatformRolesPage grant", () => {
  it("grants the chosen role to every picked user", async () => {
    h.grantRole.mockReturnValue({ unwrap: () => Promise.resolve(null) });
    pickNextUser();
    pickNextUser();
    expect(pickedNames()).toEqual(["Alice Watson", "Bob Durand"]);

    await act(async () => submit().click());

    expect(h.grantRole.mock.calls.map(([arg]) => arg)).toEqual([
      { userId: "u-alice", grantPlatformRoleRequest: { relation: "team_manager" } },
      { userId: "u-bob", grantPlatformRoleRequest: { relation: "team_manager" } },
    ]);
    expect(h.showSuccess).toHaveBeenCalledTimes(1);
    expect(h.notifyApiError).not.toHaveBeenCalled();
    expect(pickedNames()).toEqual([]);
  });

  it("keeps only the users whose grant failed picked", async () => {
    h.grantRole.mockImplementation(({ userId }: { userId: string }) => ({
      unwrap: () => (userId === "u-bob" ? Promise.reject({ status: 403 }) : Promise.resolve(null)),
    }));
    pickNextUser();
    pickNextUser();

    await act(async () => submit().click());

    expect(h.showSuccess).toHaveBeenCalledTimes(1);
    expect(h.notifyApiError).toHaveBeenCalledTimes(1);
    expect(pickedNames()).toEqual(["Bob Durand"]);
  });

  it("does not offer a user who is already picked", () => {
    pickNextUser();
    act(() => input().blur());
    act(() => input().focus());

    const options = Array.from(container.querySelectorAll('[role="option"]')).map((option) => option.textContent);
    expect(options).toEqual(["Bob Durand (bob)", "Carol Diaz (carol)"]);
  });
});
