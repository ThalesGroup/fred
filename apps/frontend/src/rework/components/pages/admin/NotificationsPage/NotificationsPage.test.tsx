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

// One row per type the backend lists, named from its value; switching on saves at
// once, switching off asks first; a failure is reported in a toast.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const h = vi.hoisted(() => ({
  query: {
    data: {
      items: [
        { type: "agent.republish_needed", enabled: true },
        { type: "agent.marketplace_removed", enabled: false },
        { type: "future.type", enabled: true },
      ],
    },
    isLoading: false,
    isFetching: false,
    isError: false,
  },
  save: vi.fn(),
  showError: vi.fn(),
  confirm: vi.fn(),
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: "en" },
  }),
}));
vi.mock("@shared/molecules/Toast/ToastProvider", () => ({
  useToast: () => ({ showSuccess: vi.fn(), showError: h.showError }),
}));
vi.mock("@shared/molecules/ConfirmationDialog/ConfirmationDialogProvider", () => ({
  useConfirmationDialog: () => ({ showConfirmationDialog: h.confirm }),
}));
vi.mock("../../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useNotificationTypesQuery: () => h.query,
  useSetNotificationTypeMutation: () => [h.save, { isLoading: false }],
}));

import NotificationsPage from "./NotificationsPage";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

let container: HTMLDivElement;
let root: Root;

const rows = () => Array.from(container.querySelectorAll("li"));
const switchOf = (row: Element) => row.querySelector('input[type="checkbox"]') as HTMLInputElement;

beforeEach(() => {
  h.save.mockReset();
  h.showError.mockReset();
  h.confirm.mockReset();
  h.save.mockReturnValue({ unwrap: () => Promise.resolve({}) });
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => root.render(<NotificationsPage />));
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

describe("NotificationsPage", () => {
  it("lists every type the backend returns with its switch", () => {
    expect(rows().map((row) => row.textContent)).toEqual([
      expect.stringContaining("rework.notifications.types.republishNeeded.name"),
      expect.stringContaining("rework.notifications.types.marketplaceRemoved.name"),
      expect.stringContaining("future.type"),
    ]);
    expect(rows().map((row) => switchOf(row).checked)).toEqual([true, false, true]);
  });

  it("switches a type on at once", async () => {
    await act(async () => switchOf(rows()[1]).click());
    expect(h.confirm).not.toHaveBeenCalled();
    expect(h.save).toHaveBeenCalledWith({
      notificationType: "agent.marketplace_removed",
      setNotificationTypeRequest: { enabled: true },
    });
    expect(h.showError).not.toHaveBeenCalled();
  });

  it("asks before switching a type off, saving only once confirmed", async () => {
    await act(async () => switchOf(rows()[0]).click());
    expect(h.save).not.toHaveBeenCalled();
    expect(h.confirm).toHaveBeenCalledWith(
      expect.objectContaining({
        title: "rework.notificationSettings.turnOff.title",
        message: "rework.notificationSettings.turnOff.message",
        criticalAction: true,
      }),
    );

    await act(async () => h.confirm.mock.calls[0][0].onConfirm());
    expect(h.save).toHaveBeenCalledWith({
      notificationType: "agent.republish_needed",
      setNotificationTypeRequest: { enabled: false },
    });
  });

  it("reports a failed save in a toast", async () => {
    h.save.mockReturnValue({ unwrap: () => Promise.reject({ status: 500, data: { detail: "boom" } }) });
    await act(async () => switchOf(rows()[1]).click());
    expect(h.showError).toHaveBeenCalledWith(
      expect.objectContaining({ summary: "rework.notificationSettings.saveFailed" }),
    );
  });
});
