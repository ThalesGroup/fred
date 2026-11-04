// @vitest-environment happy-dom
// Copyright Thales 2026
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
// Unless required by applicable law or agreed to in writing, software distributed
// under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR
// CONDITIONS OF ANY KIND, either express or implied.

import { act } from "react";
import { createRoot } from "react-dom/client";
import { expect, it, vi } from "vitest";
import { abortTurn, registerTurn, settleTurn, type LiveTurn } from "./backgroundTurns";
import { useBackgroundTurnNotifications } from "./useBackgroundTurnNotifications";

const { showInfo, navigate, selectSession, selectSessions, store } = vi.hoisted(() => ({
  showInfo: vi.fn(),
  navigate: vi.fn(),
  selectSession: vi.fn(() => () => ({ data: undefined })),
  selectSessions: vi.fn(() => () => ({ data: [{ session_id: "saved", title: "Preserved conversation" }] })),
  store: { getState: () => ({}) },
}));
vi.mock("react-redux", () => ({ useStore: () => store }));
vi.mock("react-router-dom", () => ({ useNavigate: () => navigate }));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock("@shared/molecules/Toast/ToastProvider", () => ({ useToast: () => ({ showInfo }) }));
vi.mock("../../../slices/controlPlane/controlPlaneOpenApi", () => ({
  controlPlaneApi: {
    endpoints: {
      getTeamSessionControlPlaneV1TeamsTeamIdSessionsSessionIdGet: { select: selectSession },
      getTeamSessionsControlPlaneV1TeamsTeamIdSessionsGet: { select: selectSessions },
    },
  },
}));
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

function AdminPage() {
  useBackgroundTurnNotifications();
  return <div>Administration</div>;
}

it("announces HITL and completed answers outside ChatList with the original destination", () => {
  const root = createRoot(document.createElement("div"));
  try {
    act(() => root.render(<AdminPage />));
    for (const awaitingInput of [true, false]) {
      const turn: LiveTurn = {
        sessionId: "saved",
        destination: { teamId: "original-team", agentInstanceId: "agent-1" },
        controller: new AbortController(),
        steeringTurnId: "steer",
        thoughts: new Map(),
        host: null,
        messages: [],
        detachedCallbacks: {},
        awaitingInput,
        completed: !awaitingInput,
      };
      act(() => {
        registerTurn(turn);
        settleTurn(turn);
      });
    }
    expect(showInfo.mock.calls.map(([toast]) => [toast.summary, toast.detail])).toEqual([
      ["rework.sidebar.chatList.awaitingInput", "Preserved conversation"],
      ["rework.sidebar.chatList.answerReady", "Preserved conversation"],
    ]);
    showInfo.mock.calls[0][0].action.onClick();
    expect(navigate).toHaveBeenCalledWith("/team/original-team/managed-chat/agent-1?session=saved");
    expect(selectSessions).toHaveBeenCalledWith({ teamId: "original-team" });
    act(() => root.unmount());
    const turn: LiveTurn = {
      sessionId: "saved",
      controller: new AbortController(),
      steeringTurnId: "steer",
      thoughts: new Map(),
      host: null,
      messages: [],
      detachedCallbacks: {},
      awaitingInput: true,
    };
    act(() => {
      registerTurn(turn);
      settleTurn(turn);
    });
    expect(showInfo).toHaveBeenCalledTimes(2);
  } finally {
    abortTurn("saved");
  }
});
