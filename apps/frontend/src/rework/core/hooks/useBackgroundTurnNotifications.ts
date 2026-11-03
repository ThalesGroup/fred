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

// Announces a turn that ended while its conversation was not shown. Mounted in
// MainLayout so it runs on every page, including those without the chat list.

import type { ThunkDispatch, UnknownAction } from "@reduxjs/toolkit";
import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { useDispatch } from "react-redux";
import { useNavigate } from "react-router-dom";

import { useToast } from "@shared/molecules/Toast/ToastProvider";
import { controlPlaneApi } from "../../../slices/controlPlane/controlPlaneOpenApi";
import { subscribeBackgroundSettled } from "./backgroundTurns";

type AppDispatch = ThunkDispatch<unknown, unknown, UnknownAction>;

export function conversationHref(teamId: string | undefined, agentInstanceId: string, sessionId: string): string {
  return `/team/${teamId}/managed-chat/${agentInstanceId}?session=${sessionId}`;
}

// Served from the sidebar's cached list when there is one; left out on failure.
async function sessionTitle(dispatch: AppDispatch, teamId: string, sessionId: string): Promise<string | undefined> {
  const { data } = await dispatch(
    controlPlaneApi.endpoints.getTeamSessionsControlPlaneV1TeamsTeamIdSessionsGet.initiate(
      { teamId },
      { subscribe: false },
    ),
  );
  return data?.find((session) => session.session_id === sessionId)?.title || undefined;
}

export function useBackgroundTurnNotifications(): void {
  const { t } = useTranslation();
  const { showInfo } = useToast();
  const navigate = useNavigate();
  const dispatch = useDispatch<AppDispatch>();

  useEffect(
    () =>
      subscribeBackgroundSettled(async (turn) => {
        const title = await sessionTitle(dispatch, turn.teamId, turn.sessionId);
        showInfo({
          summary: t(
            turn.awaitingInput ? "rework.sidebar.chatList.awaitingInput" : "rework.sidebar.chatList.answerReady",
          ),
          detail: title,
          action: {
            label: t("rework.sidebar.chatList.openConversation"),
            onClick: () => navigate(conversationHref(turn.teamId, turn.agentInstanceId, turn.sessionId)),
          },
        });
      }),
    [dispatch, navigate, showInfo, t],
  );
}
