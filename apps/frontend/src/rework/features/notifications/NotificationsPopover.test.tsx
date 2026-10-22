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

// Pins marking seen on opening, what a click or an action deletes, one call per
// decision, Clear all, the empty state and paging by cursor.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { NotificationItem } from "./notificationTypes";

const listMock = vi.fn();
const markSeen = vi.fn();
const dispatch = vi.fn();
const deleteNotification = vi.fn();
const clearNotifications = vi.fn();
const navigate = vi.fn();
const showError = vi.fn();

vi.mock("../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  enhancedControlPlaneApi: {
    util: { invalidateTags: vi.fn() },
    endpoints: {
      acceptTeamJoinRequestControlPlaneV1TeamsTeamIdJoinRequestsRequestIdAcceptPost: { initiate: vi.fn() },
      refuseTeamJoinRequestControlPlaneV1TeamsTeamIdJoinRequestsRequestIdRefusePost: { initiate: vi.fn() },
      deleteNotificationControlPlaneV1NotificationsNotificationIdDelete: { initiate: vi.fn() },
    },
  },
  useNotificationsQuery: (...args: unknown[]) => listMock(...args),
  useMarkNotificationsSeenMutation: () => [markSeen],
  useDeleteNotificationMutation: () => [deleteNotification],
  useClearNotificationsMutation: () => [clearNotifications, { isLoading: false }],
}));
vi.mock("react-router-dom", () => ({ useNavigate: () => navigate }));
vi.mock("@shared/molecules/Toast/ToastProvider", () => ({ useToast: () => ({ showError }) }));
vi.mock("react-redux", () => ({ useDispatch: () => dispatch }));
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

function joinRequest(id: string): NotificationItem {
  return notification(id, {
    type: "team.join_requested",
    payload: {
      team_id: "team-1",
      team_name: "Ops",
      request_id: "req-1",
      requester_id: "u-2",
      requester_name: "Bob",
    },
  } as Partial<NotificationItem>);
}

const FRESH = Number.MAX_SAFE_INTEGER;

/** One answer per page: the first page has no `before`. */
function pages(
  byCursor: Record<string, { items: NotificationItem[]; next_cursor?: string | null }>,
  fetchedAt = FRESH,
) {
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

  it("deletes a tile on click and follows its link", () => {
    pages({ first: { items: [notification("n1")] } });
    const el = render();

    act(() => el.querySelector<HTMLButtonElement>("li button")!.click());

    expect(deleteNotification).toHaveBeenCalledExactlyOnceWith({ notificationId: "n1" });
    expect(onClose).toHaveBeenCalledWith(false);
    expect(navigate).toHaveBeenCalledWith("/team/team-1/agents?agent=agent-1");
  });

  it("deletes a tile when its navigate action is clicked, and follows it", () => {
    pages({ first: { items: [notification("n1")] } });
    const el = render();

    act(() => buttonByText(el, "rework.notifications.actions.openAgent").click());

    expect(deleteNotification).toHaveBeenCalledExactlyOnceWith({ notificationId: "n1" });
    expect(navigate).toHaveBeenCalledWith("/team/team-1/agents?agent=agent-1");
  });

  it("keeps a tile whose domain action fails, and reports it in a toast", async () => {
    dispatch.mockReturnValue({ unwrap: () => Promise.reject({ status: 500 }) });
    pages({
      first: {
        items: [
          notification("n1", {
            type: "team.join_requested",
            payload: {
              team_id: "team-1",
              team_name: "Ops",
              request_id: "req-1",
              requester_id: "u-2",
              requester_name: "Bob",
            },
          } as Partial<NotificationItem>),
        ],
      },
    });
    const el = render();

    await act(async () => buttonByText(el, "rework.notifications.actions.accept").click());

    expect(deleteNotification).not.toHaveBeenCalled();
    expect(navigate).not.toHaveBeenCalled();
    expect(showError).toHaveBeenCalledWith(expect.objectContaining({ summary: "rework.notifications.actionFailed" }));
  });

  it("sends one decision however often its button is clicked", async () => {
    let settle: (value: unknown) => void = () => {};
    dispatch.mockReturnValue({ unwrap: () => new Promise((resolve) => (settle = resolve)) });
    pages({ first: { items: [joinRequest("n1")] } });
    const el = render();

    act(() => buttonByText(el, "rework.notifications.actions.accept").click());
    act(() => buttonByText(el, "rework.notifications.actions.refuse").click());

    expect(dispatch).toHaveBeenCalledOnce();
    expect(buttonByText(el, "rework.notifications.actions.refuse").disabled).toBe(true);
    await act(async () => settle(undefined));
    expect(buttonByText(el, "rework.notifications.actions.refuse").disabled).toBe(false);
  });

  it("lets a pending decision follow its link without deleting it, and has no close button", () => {
    pages({ first: { items: [joinRequest("n1")] } });
    const el = render();

    expect(el.querySelector('button[aria-label="rework.notifications.dismiss"]')).toBeNull();
    act(() => el.querySelector<HTMLButtonElement>("li button")!.click());

    expect(deleteNotification).not.toHaveBeenCalled();
    expect(navigate).toHaveBeenCalledWith("/team/team-1/settings/members");
  });

  it("disables clear all when only pending decisions are listed", () => {
    pages({ first: { items: [joinRequest("n1")] } });
    const el = render();

    expect(buttonByText(el, "rework.notifications.clearAll").disabled).toBe(true);
  });

  it("deletes one notification through its close button", () => {
    pages({ first: { items: [notification("n1")] } });
    const el = render();

    act(() => el.querySelector<HTMLButtonElement>('button[aria-label="rework.notifications.dismiss"]')!.click());

    expect(deleteNotification).toHaveBeenCalledWith({ notificationId: "n1" });
    expect(navigate).not.toHaveBeenCalled();
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
    expect(el.querySelectorAll("li time")).toHaveLength(2);
    expect(buttonByText(el, "rework.notifications.loadMore")).toBeUndefined();
  });

  it("refetches a later page from the cursor the page above has now", () => {
    pages({
      first: { items: [notification("n3")], next_cursor: "cursor-2" },
      "cursor-2": { items: [notification("n2")], next_cursor: null },
    });
    const el = render();
    act(() => buttonByText(el, "rework.notifications.loadMore").click());

    // A delete above pulled n2 onto the first page: page two now starts after it.
    pages({
      first: { items: [notification("n3"), notification("n2")], next_cursor: "cursor-1" },
      "cursor-1": { items: [notification("n1")], next_cursor: null },
    });
    act(() => root!.render(<NotificationsPopover id="pop" onClose={onClose} />));

    expect(el.querySelectorAll("li time")).toHaveLength(3);
    expect(listMock).toHaveBeenLastCalledWith({ limit: 50, before: "cursor-1" });
  });

  it("puts focus on its title when it opens", () => {
    pages({ first: { items: [] } });
    const el = render();

    expect(document.activeElement).toBe(el.querySelector("h2"));
  });
});
