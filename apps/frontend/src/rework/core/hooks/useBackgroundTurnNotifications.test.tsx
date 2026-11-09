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

import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, expect, it, vi } from "vitest";

const showInfo = vi.hoisted(() => vi.fn());
const navigate = vi.hoisted(() => vi.fn());
const identity = vi.hoisted(() => ({ current: "alice-session" }));
const selectSessions = vi.hoisted(() => vi.fn());
vi.mock("../../../security/KeycloakService", () => ({
  KeyCloakService: { GetSessionIdentity: () => identity.current },
}));
const sessionList = vi.hoisted(() => ({
  data: [{ session_id: "saved", title: "Quarterly report" }] as unknown,
  error: undefined as { status: number } | undefined,
}));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock("react-redux", () => ({ useStore: () => ({ getState: () => ({}) }) }));
vi.mock("@shared/molecules/Toast/ToastProvider", () => ({ useToast: () => ({ showInfo }) }));
vi.mock("../../../slices/controlPlane/controlPlaneOpenApi", () => ({
  controlPlaneApi: {
    endpoints: {
      listSessions: {
        select: (args: unknown) => {
          selectSessions(args);
          return () => sessionList;
        },
      },
    },
  },
}));

import { abortTurn, registerTurn, settleTurn, type LiveTurn } from "./backgroundTurns";
import { useBackgroundTurnNotifications } from "./useBackgroundTurnNotifications";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

function Notifier() {
  useBackgroundTurnNotifications(navigate);
  return null;
}

function endOutOfSight(awaitingInput: boolean, flags: Partial<LiveTurn> = {}): void {
  const turn: LiveTurn = {
    sessionId: "saved",
    scope: { actor: "alice-session", spaceId: "space-1", agentInstanceId: "agent-1" },
    controller: new AbortController(),
    thoughts: new Map(),
    host: null,
    messages: [],
    detachedCallbacks: {},
    awaitingInput,
    completed: !awaitingInput,
    ...flags,
  };
  registerTurn(turn);
  settleTurn(turn);
}

const root = createRoot(document.createElement("div"));
afterEach(() => {
  act(() => root.render(null));
  abortTurn("saved");
  showInfo.mockClear();
  navigate.mockClear();
  selectSessions.mockClear();
  identity.current = "alice-session";
  sessionList.data = [{ session_id: "saved", title: "Quarterly report" }];
  sessionList.error = undefined;
});

it("announces a turn that ended out of sight on any page, with its title and a way to open it", async () => {
  act(() => root.render(<Notifier />));
  await act(async () => endOutOfSight(false));
  await act(async () => endOutOfSight(true));
  expect(showInfo.mock.calls.map(([toast]) => [toast.summary, toast.detail])).toEqual([
    ["rework.sidebar.chatList.answerReady", "Quarterly report"],
    ["rework.sidebar.chatList.awaitingInput", "Quarterly report"],
  ]);
  showInfo.mock.calls[0][0].action.onClick();
  expect(navigate).toHaveBeenCalledWith("/team/space-1/managed-chat/agent-1?session=saved");
});

it("still announces the turn when its title cannot be read", async () => {
  sessionList.data = undefined;
  act(() => root.render(<Notifier />));
  await act(async () => endOutOfSight(false));
  expect(showInfo).toHaveBeenCalledOnce();
  expect(showInfo.mock.calls[0][0].detail).toBeUndefined();
});

it.each([401, 403, 404])("does not disclose a cached title after session access fails with %s", async (status) => {
  sessionList.error = { status };
  act(() => root.render(<Notifier />));
  await act(async () => endOutOfSight(false));
  expect(showInfo).toHaveBeenCalledOnce();
  expect(showInfo.mock.calls[0][0].detail).toBeUndefined();
});

it.each(["incomplete", "interrupted", "cancelled"])("does not announce a %s background turn", async (outcome) => {
  const controller = new AbortController();
  if (outcome === "cancelled") controller.abort();
  act(() => root.render(<Notifier />));
  await act(async () =>
    endOutOfSight(false, {
      controller,
      completed: outcome !== "incomplete",
      interrupted: outcome === "interrupted",
    }),
  );
  expect(showInfo).not.toHaveBeenCalled();
});

it("does not announce an interrupted question after the stream fails", async () => {
  act(() => root.render(<Notifier />));
  await act(async () => endOutOfSight(true, { interrupted: true }));
  expect(showInfo).not.toHaveBeenCalled();
});

it("uses the admitted space for team, project and personal conversation links", async () => {
  act(() => root.render(<Notifier />));
  for (const spaceId of ["team-space", "project-space", "personal-space"]) {
    await act(async () =>
      endOutOfSight(false, { scope: { actor: identity.current, spaceId, agentInstanceId: "agent-1" } }),
    );
    expect(selectSessions).toHaveBeenLastCalledWith({ spaceId });
    showInfo.mock.calls[showInfo.mock.calls.length - 1][0].action.onClick();
    expect(navigate).toHaveBeenLastCalledWith(`/team/${spaceId}/managed-chat/agent-1?session=saved`);
  }
});

it("does not notify a new browser identity about an old admitted turn", async () => {
  identity.current = "bob-session";
  act(() => root.render(<Notifier />));
  await act(async () => endOutOfSight(false));
  expect(showInfo).not.toHaveBeenCalled();
});

it("does not navigate through an old toast after the browser identity changes", async () => {
  act(() => root.render(<Notifier />));
  await act(async () => endOutOfSight(false));
  identity.current = "bob-session";
  showInfo.mock.calls[0][0].action.onClick();
  expect(navigate).not.toHaveBeenCalled();
});
