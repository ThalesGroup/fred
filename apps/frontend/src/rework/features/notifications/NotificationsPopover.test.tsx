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


// What these pin: opening marks seen up to the newest listed notification, and
// only from an answer fetched for this opening; a click marks read and follows
// the link; delete and clear all call their routes; the empty state; load more
// asks for the next page by cursor.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { NotificationItem } from "./notificationTypes";

const listMock = vi.fn();
const markSeen = vi.fn();
const markRead = vi.fn();
const deleteNotification = vi.fn();
const clearNotifications = vi.fn();
const navigate = vi.fn();

vi.mock("../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  enhancedControlPlaneApi: { util: { invalidateTags: vi.fn() } },
  useNotificationsQuery: (...args: unknown[]) => listMock(...args),
  useMarkNotificationsSeenMutation: () => [markSeen],
  useMarkNotificationReadMutation: () => [markRead],
  useDeleteNotificationMutation: () => [deleteNotification],
  useClearNotificationsMutation: () => [clearNotifications, { isLoading: false }],
}));
vi.mock("react-router-dom", () => ({ useNavigate: () => navigate }));
vi.mock("react-redux", () => ({ useDispatch: () => vi.fn() }));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en" } }),
}));

import NotificationsPopover from "./NotificationsPopover";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

function notification(id: string, overrides: Partial<NotificationItem> = {}): NotificationItem {
  return {
    id,
    team_id: "team-1",
    created_at: "2026-10-20T10:00:00Z",
    expires_at: "2026-11-19T10:00:00Z",
    type: "agent.republish_needed",
    payload: {
      team_id: "team-1",
      agent_instance_id: "agent-1",
      agent_name: "RFP writer",
      entry_id: "entry-1",
      editor_name: "Léa",
    },
    ...overrides,
  } as NotificationItem;
}

const FRESH = Number.MAX_SAFE_INTEGER;

/** One answer per page: the first page has no `before`. */
function pages(byCursor: Record<string, { items: NotificationItem[]; next_cursor?: string | null }>, fetchedAt = FRESH) {
  listMock.mockImplementation((args: { before?: string }) => {
    const data = byCursor[args.before ?? "first"];
    return { data, isSuccess: true, isError: false, isFetching: false, fulfilledTimeStamp: fetchedAt };
  });
}

let container: HTMLDivElement | null = null;
let root: Root | null = null;
const onClose = vi.fn();

function render() {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => root!.render(<NotificationsPopover id="pop" onClose={onClose} />));
  return container;
}

const buttonByText = (el: Element, text: string) =>
  [...el.querySelectorAll("button")].find((button) => button.textContent === text) as HTMLButtonElement;

beforeEach(() => {
  clearNotifications.mockReturnValue({ unwrap: () => Promise.resolve() });
});

afterEach(() => {
  act(() => root?.unmount());
  container?.remove();
  container = null;
  root = null;
  vi.clearAllMocks();
});

describe("NotificationsPopover", () => {
  it("marks seen up to the newest listed notification on opening", () => {
    pages({ first: { items: [notification("n2"), notification("n1")] } });

    render();

    expect(markSeen).toHaveBeenCalledExactlyOnceWith({ markNotificationsSeenRequest: { up_to: "n2" } });
  });

  it("marks nothing seen from a cached answer older than the opening", () => {
    pages({ first: { items: [notification("n2")] } }, 0);

    render();

    expect(markSeen).not.toHaveBeenCalled();
  });

  it("marks nothing seen when every listed notification already is", () => {
    pages({ first: { items: [notification("n1", { seen_at: "2026-10-20T11:00:00Z" })] } });

    render();

    expect(markSeen).not.toHaveBeenCalled();
  });

  it("marks an unread tile read on click and follows its link", () => {
    pages({ first: { items: [notification("n1")] } });
    const el = render();

    act(() => el.querySelector<HTMLButtonElement>("li button")!.click());

    expect(markRead).toHaveBeenCalledWith({ notificationId: "n1" });
    expect(onClose).toHaveBeenCalledWith(false);
    expect(navigate).toHaveBeenCalledWith("/team/team-1/agents");
  });

  it("does not mark a read tile read again", () => {
    pages({ first: { items: [notification("n1", { read_at: "2026-10-20T11:00:00Z" })] } });
    const el = render();

    act(() => el.querySelector<HTMLButtonElement>("li button")!.click());

    expect(markRead).not.toHaveBeenCalled();
    expect(navigate).toHaveBeenCalledWith("/team/team-1/agents");
  });

  it("deletes one notification", () => {
    pages({ first: { items: [notification("n1")] } });
    const el = render();

    act(() => el.querySelector<HTMLButtonElement>('button[aria-label="rework.notifications.delete"]')!.click());

    expect(deleteNotification).toHaveBeenCalledWith({ notificationId: "n1" });
  });

  it("clears all notifications", async () => {
    pages({ first: { items: [notification("n1")] } });
    const el = render();

    await act(async () => buttonByText(el, "rework.notifications.clearAll").click());

    expect(clearNotifications).toHaveBeenCalledOnce();
  });

  it("shows the empty state, with clear all disabled", () => {
    pages({ first: { items: [] } });
    const el = render();

    expect(el.textContent).toContain("rework.notifications.empty.title");
    expect(buttonByText(el, "rework.notifications.clearAll").disabled).toBe(true);
    expect(markSeen).not.toHaveBeenCalled();
  });

  it("loads the next page from the previous page's cursor", () => {
    pages({
      first: { items: [notification("n2")], next_cursor: "cursor-1" },
      "cursor-1": { items: [notification("n1")], next_cursor: null },
    });
    const el = render();

    act(() => buttonByText(el, "rework.notifications.loadMore").click());

    expect(listMock).toHaveBeenCalledWith({ limit: 50, before: "cursor-1" });
    expect(el.querySelectorAll("li[data-unread]")).toHaveLength(2);
    expect(buttonByText(el, "rework.notifications.loadMore")).toBeUndefined();
  });

  it("puts focus on its title when it opens", () => {
    pages({ first: { items: [] } });
    const el = render();

    expect(document.activeElement).toBe(el.querySelector("h2"));
  });
});
