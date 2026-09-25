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

// What these pin: the two actions are conditional, and each on a different
// thing. "More info" appears only when there is a long description to show —
// an empty dialog is worse than no button. The close button appears only when
// the announcement is dismissible, because a maintenance notice an operator
// marked non-dismissible must survive a user's reflex click. And closing the
// dialog must not take the banner with it: they are separate dismissals.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";
import AnnouncementBanner, { HIDE_TRANSITION_MS } from "./AnnouncementBanner";
import type { Announcement } from "../../../../../slices/controlPlane/controlPlaneOpenApi";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en" } }),
}));

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

function announcement(overrides: Partial<Announcement> = {}): Announcement {
  return {
    id: "a1",
    severity: "warning",
    title: { en: "Scheduled maintenance" },
    description_short: { en: "Fred is down on Sunday." },
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

function render(element: React.ReactElement): HTMLDivElement {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => root!.render(element));
  return container;
}

afterEach(() => {
  act(() => root?.unmount());
  container?.remove();
  container = null;
  root = null;
  vi.useRealTimers();
});

describe("AnnouncementBanner", () => {
  it("shows the title and the short description", () => {
    const el = render(<AnnouncementBanner announcement={announcement()} onDismissed={() => {}} />);

    expect(el.textContent).toContain("Scheduled maintenance");
    expect(el.textContent).toContain("Fred is down on Sunday.");
  });

  it("marks the banner with its severity so the accent and icon follow", () => {
    const el = render(<AnnouncementBanner announcement={announcement({ severity: "error" })} onDismissed={() => {}} />);

    expect(el.querySelector('[data-severity="error"]')).not.toBeNull();
  });

  it("falls back to any authored locale rather than rendering an empty strip", () => {
    // The backend requires only one non-empty locale and the editor opens on
    // the French tab, so a French-only announcement is ordinary. Resolving it
    // to nothing for an English viewer would paint an accented strip with an
    // icon, a close button and no words in it.
    const el = render(
      <AnnouncementBanner
        announcement={announcement({
          title: { fr: "Maintenance prévue" },
          description_short: { fr: "Fred sera coupé dimanche." },
        })}
        onDismissed={() => {}}
      />,
    );

    expect(el.textContent).toContain("Maintenance prévue");
    expect(el.textContent).toContain("Fred sera coupé dimanche.");
  });

  it("falls back to English when the viewer's locale has no entry", () => {
    const el = render(
      <AnnouncementBanner
        announcement={announcement({ title: { en: "English only" }, description_short: { fr: "Français" } })}
        onDismissed={() => {}}
      />,
    );

    expect(el.textContent).toContain("English only");
  });

  it("offers no more-info action when there is no long description", () => {
    const el = render(<AnnouncementBanner announcement={announcement()} onDismissed={() => {}} />);

    expect(el.textContent).not.toContain("rework.announcements.banner.moreInfo");
  });

  it("offers the more-info action when a long description exists", () => {
    const el = render(
      <AnnouncementBanner
        announcement={announcement({ description_long: { en: "The full story." } })}
        onDismissed={() => {}}
      />,
    );

    expect(el.textContent).toContain("rework.announcements.banner.moreInfo");
  });

  it("opens a dialog with the long description, and closing it leaves the banner", () => {
    const el = render(
      <AnnouncementBanner
        announcement={announcement({ description_long: { en: "The full story." } })}
        onDismissed={() => {}}
      />,
    );
    const moreInfo = [...el.querySelectorAll("button")].find((b) =>
      b.textContent?.includes("rework.announcements.banner.moreInfo"),
    );

    act(() => moreInfo!.click());
    expect(document.body.textContent).toContain("The full story.");

    const close = [...document.body.querySelectorAll("button")].find((b) =>
      b.textContent?.includes("rework.announcements.dialog.close"),
    );
    act(() => close!.click());

    expect(document.body.textContent).not.toContain("The full story.");
    // The banner itself is untouched — closing the dialog is not a dismissal.
    expect(el.textContent).toContain("Scheduled maintenance");
  });

  it("offers no dismiss action on a non-dismissible announcement", () => {
    const el = render(
      <AnnouncementBanner announcement={announcement({ dismissible: false })} onDismissed={() => {}} />,
    );

    expect(el.querySelector('[aria-label="rework.announcements.banner.dismiss"]')).toBeNull();
  });

  it("keeps the close button but does nothing on click in preview mode", () => {
    // The admin list renders the real banner so the preview is trustworthy —
    // the close button has to be visible (users will have one) without
    // collapsing the row it sits in.
    vi.useFakeTimers();
    const onDismissed = vi.fn();
    const el = render(<AnnouncementBanner announcement={announcement()} onDismissed={onDismissed} preview />);
    const close = el.querySelector<HTMLButtonElement>('[aria-label="rework.announcements.banner.dismiss"]');

    expect(close).not.toBeNull();
    act(() => close!.click());
    act(() => void vi.advanceTimersByTime(HIDE_TRANSITION_MS * 2));

    expect(onDismissed).not.toHaveBeenCalled();
    // The collapse never starts: assert on the wrapper, not on any
    // aria-hidden in the subtree — the severity icon carries one too.
    expect(el.firstElementChild?.getAttribute("aria-hidden")).toBeNull();
    expect(el.textContent).toContain("Scheduled maintenance");
  });

  it("reports the dismissal only once the collapse has finished", () => {
    vi.useFakeTimers();
    const onDismissed = vi.fn();
    const el = render(<AnnouncementBanner announcement={announcement()} onDismissed={onDismissed} />);
    const close = el.querySelector<HTMLButtonElement>('[aria-label="rework.announcements.banner.dismiss"]');

    act(() => close!.click());
    // The exit is playing: the WRAPPER goes aria-hidden (querying the subtree
    // would match the severity icon and prove nothing), and nothing is
    // reported yet.
    expect(el.firstElementChild?.getAttribute("aria-hidden")).toBe("true");
    expect(onDismissed).not.toHaveBeenCalled();

    act(() => void vi.advanceTimersByTime(HIDE_TRANSITION_MS));

    expect(onDismissed).toHaveBeenCalledTimes(1);
    expect(onDismissed.mock.calls[0][0].id).toBe("a1");
  });
});
