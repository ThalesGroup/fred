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

// @vitest-environment happy-dom

// What these pin: toggling a row goes through the dedicated enabled endpoint
// rather than a full content update — that separation is what keeps
// content_version still, and with it every user's dismissal. Deleting asks
// first, because an announcement is not recoverable. And the header reports
// how many banners are actually live, the number an admin loses track of.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Announcement } from "../../../../../slices/controlPlane/controlPlaneOpenApi";

const listMock = vi.fn();
const createMock = vi.fn();
const updateMock = vi.fn();
const setEnabledMock = vi.fn();
const deleteMock = vi.fn();
const confirmMock = vi.fn();
const showError = vi.fn();
const showSuccess = vi.fn();

vi.mock("../../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useAnnouncementsQuery: () => listMock(),
  useCreateAnnouncementMutation: () => [createMock, { isLoading: false }],
  useUpdateAnnouncementMutation: () => [updateMock, { isLoading: false }],
  useSetAnnouncementEnabledMutation: () => [setEnabledMock, { isLoading: false }],
  useDeleteAnnouncementMutation: () => [deleteMock, { isLoading: false }],
}));
vi.mock("@shared/molecules/ConfirmationDialog/ConfirmationDialogProvider", () => ({
  useConfirmationDialog: () => ({ showConfirmationDialog: confirmMock }),
}));
vi.mock("@shared/molecules/Toast/ToastProvider", () => ({
  useToast: () => ({ showSuccess, showError, showInfo: vi.fn(), showWarning: vi.fn() }),
}));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, unknown>) =>
      options && "count" in options ? `${key}:${options.count}` : key,
    i18n: { language: "en" },
  }),
}));
// The editor drags MDXEditor in; this page's tests are about the list.
vi.mock("./AnnouncementEditorDialog", () => ({
  default: () => <div data-testid="editor" />,
}));

import AnnouncementsPage from "./AnnouncementsPage";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

function announcement(overrides: Partial<Announcement> = {}): Announcement {
  return {
    id: "a1",
    severity: "info",
    title: { en: "Scheduled maintenance" },
    description_short: { en: "Down on Sunday." },
    description_long: {},
    enabled: false,
    dismissible: true,
    content_version: 1,
    created_at: "2026-09-01T10:00:00Z",
    updated_at: "2026-09-01T10:00:00Z",
    ...overrides,
  };
}

let container: HTMLDivElement | null = null;
let root: Root | null = null;

function render(): HTMLDivElement {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => root!.render(<AnnouncementsPage />));
  return container;
}

beforeEach(() => {
  listMock.mockReturnValue({ data: [], isLoading: false });
  setEnabledMock.mockReturnValue({ unwrap: () => Promise.resolve({}) });
  deleteMock.mockReturnValue({ unwrap: () => Promise.resolve({}) });
});

afterEach(() => {
  act(() => root?.unmount());
  container?.remove();
  container = null;
  root = null;
  vi.clearAllMocks();
});

describe("AnnouncementsPage", () => {
  it("offers to create one when there is nothing yet", () => {
    const el = render();

    expect(el.textContent).toContain("rework.announcements.page.empty");
  });

  it("lists each announcement with its title and short description", () => {
    listMock.mockReturnValue({ data: [announcement()], isLoading: false });

    const el = render();

    expect(el.textContent).toContain("Scheduled maintenance");
    expect(el.textContent).toContain("Down on Sunday.");
  });

  it("reports how many announcements are live, not how many exist", () => {
    listMock.mockReturnValue({
      data: [announcement({ id: "a1", enabled: true }), announcement({ id: "a2", enabled: false })],
      isLoading: false,
    });

    expect(render().textContent).toContain("rework.announcements.page.subtitle:1");
  });

  it("previews each announcement with the real banner component", () => {
    // Not a lookalike styled to match: the admin has to be able to trust that
    // this is what users will get, which only holds if it is the same code.
    listMock.mockReturnValue({
      data: [announcement({ severity: "error", description_long: { en: "The full story." } })],
      isLoading: false,
    });

    const el = render();

    expect(el.querySelector('[data-severity="error"]')).not.toBeNull();
    // The banner's own actions render too, so the admin sees what users get.
    expect(el.textContent).toContain("rework.announcements.banner.moreInfo");
    expect(el.querySelector('[aria-label="rework.announcements.banner.dismiss"]')).not.toBeNull();
  });

  it("says which way the switch goes, and that it lands for every user", () => {
    // The switch carries no visible label, so the hint is the only place that
    // spells out the reach of the flick — and it has to follow the state.
    listMock.mockReturnValue({ data: [announcement({ enabled: false })], isLoading: false });
    const el = render();
    const trigger = el.querySelector('[aria-label="rework.announcements.row.enabled"]')!.closest("span")!;

    act(() => void trigger.dispatchEvent(new MouseEvent("mouseover", { bubbles: true })));

    expect(document.body.textContent).toContain("rework.announcements.row.enableHint");
    expect(document.body.textContent).not.toContain("rework.announcements.row.disableHint");
  });

  it("toggles through the dedicated enabled endpoint, not a content update", () => {
    listMock.mockReturnValue({ data: [announcement()], isLoading: false });
    const el = render();
    const toggle = el.querySelector<HTMLInputElement>('[aria-label="rework.announcements.row.enabled"]');

    // React maps a checkbox's onChange onto the click event, not a synthetic
    // "change" — dispatching the latter reaches no handler at all.
    act(() => toggle!.click());

    expect(setEnabledMock).toHaveBeenCalledWith({
      announcementId: "a1",
      setAnnouncementEnabledRequest: { enabled: true },
    });
    // A toggle must never go through the content update — that would bump
    // content_version and resurrect every dismissed banner.
    expect(updateMock).not.toHaveBeenCalled();
  });

  it("asks before deleting, and does not delete until confirmed", () => {
    listMock.mockReturnValue({ data: [announcement()], isLoading: false });
    const el = render();
    const remove = el.querySelector<HTMLButtonElement>('[aria-label="rework.announcements.row.delete"]');

    act(() => remove!.click());

    expect(confirmMock).toHaveBeenCalledTimes(1);
    expect(deleteMock).not.toHaveBeenCalled();

    const options = confirmMock.mock.calls[0][0];
    expect(options.criticalAction).toBe(true);
    act(() => void options.onConfirm());

    expect(deleteMock).toHaveBeenCalledWith({ announcementId: "a1" });
  });

  it("opens the editor from the create action", () => {
    const el = render();
    const create = [...el.querySelectorAll("button")].find((b) =>
      b.textContent?.includes("rework.announcements.page.create"),
    );

    act(() => create!.click());

    expect(el.querySelector('[data-testid="editor"]')).not.toBeNull();
  });
});
