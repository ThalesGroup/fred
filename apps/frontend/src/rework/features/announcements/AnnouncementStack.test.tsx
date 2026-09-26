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

// What these pin: the stack is the only thing that decides what is on screen.
// Ordering puts an incident above a week-old notice; a banner this browser
// already dismissed never renders; and an edited announcement comes back — both
// on a later load and in a tab that stayed open, which needs the in-session
// state keyed exactly like the stored one.
//
// There is deliberately no "unauthenticated" case here: the stack is mounted
// inside GcuGuard/BootstrapGuard, so reaching it already means both passed.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Announcement } from "../../../slices/controlPlane/controlPlaneOpenApi";

const queryMock = vi.fn();

vi.mock("../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useActiveAnnouncementsQuery: (...args: unknown[]) => queryMock(...args),
}));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en" } }),
}));

import AnnouncementStack from "./AnnouncementStack";
import { clearDismissed, markDismissed } from "./announcementDismissal";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

function announcement(overrides: Partial<Announcement> = {}): Announcement {
  return {
    id: "a1",
    severity: "info",
    title: { en: "Title" },
    description_short: { en: "Short" },
    description_long: {},
    enabled: true,
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
  vi.useFakeTimers();
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => root!.render(<AnnouncementStack />));
  return container;
}

beforeEach(() => {
  queryMock.mockReturnValue({ data: [], refetch: vi.fn() });
});

afterEach(() => {
  vi.useRealTimers();
  act(() => root?.unmount());
  container?.remove();
  container = null;
  root = null;
  clearDismissed();
  vi.clearAllMocks();
});

describe("AnnouncementStack", () => {
  it("renders nothing when no announcement is enabled", () => {
    const el = render();

    expect(el.innerHTML).toBe("");
  });

  it("renders nothing while the data is still undefined", () => {
    queryMock.mockReturnValue({ data: undefined, refetch: vi.fn() });

    expect(render().innerHTML).toBe("");
  });

  it("orders by severity, most severe first", () => {
    queryMock.mockReturnValue({
      data: [
        announcement({ id: "info", severity: "info", title: { en: "INFO" } }),
        announcement({ id: "error", severity: "error", title: { en: "ERROR" } }),
        announcement({ id: "warning", severity: "warning", title: { en: "WARNING" } }),
      ],
      refetch: vi.fn(),
    });

    const text = render().textContent ?? "";

    expect(text.indexOf("ERROR")).toBeLessThan(text.indexOf("WARNING"));
    expect(text.indexOf("WARNING")).toBeLessThan(text.indexOf("INFO"));
  });

  it("orders oldest first within one severity", () => {
    queryMock.mockReturnValue({
      data: [
        announcement({ id: "new", title: { en: "NEWER" }, created_at: "2026-09-10T10:00:00Z" }),
        announcement({ id: "old", title: { en: "OLDER" }, created_at: "2026-09-01T10:00:00Z" }),
      ],
      refetch: vi.fn(),
    });

    const text = render().textContent ?? "";

    expect(text.indexOf("OLDER")).toBeLessThan(text.indexOf("NEWER"));
  });

  it("hides a banner this browser already dismissed", () => {
    markDismissed("a1", 1);
    queryMock.mockReturnValue({ data: [announcement()], refetch: vi.fn() });

    expect(render().innerHTML).toBe("");
  });

  it("shows a dismissed banner again once its content version moves", () => {
    markDismissed("a1", 1);
    queryMock.mockReturnValue({ data: [announcement({ content_version: 2 })], refetch: vi.fn() });

    expect(render().textContent).toContain("Title");
  });

  it("subscribes with the shared cross-session refresh contract", () => {
    render();

    expect(queryMock).toHaveBeenCalledWith(
      undefined,
      expect.objectContaining({ skip: false, pollingInterval: 60_000 }),
    );
  });

  it("brings a banner back in the SAME tab once its content version moves", () => {
    // In-session dismissal state is keyed like the stored one. Keyed on the id
    // alone, an announcement edited while this tab stayed open would remain
    // suppressed until a reload — the exact case the version key exists for.
    queryMock.mockReturnValue({ data: [announcement()], refetch: vi.fn() });
    const el = render();
    const close = el.querySelector<HTMLButtonElement>('[aria-label="rework.announcements.banner.dismiss"]');
    act(() => close!.click());
    act(() => void vi.advanceTimersByTime(400));
    expect(el.innerHTML).toBe("");

    // The admin edits it; the next poll delivers version 2.
    queryMock.mockReturnValue({ data: [announcement({ content_version: 2 })], refetch: vi.fn() });
    act(() => root!.render(<AnnouncementStack />));

    expect(el.textContent).toContain("Title");
  });
});
