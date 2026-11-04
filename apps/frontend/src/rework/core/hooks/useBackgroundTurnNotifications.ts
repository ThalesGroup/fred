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

import { useEffect } from "react";
import { useStore } from "react-redux";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import type { AppState } from "../../../common/store";
import { controlPlaneApi } from "../../../slices/controlPlane/controlPlaneOpenApi";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import { subscribeBackgroundSettled } from "./backgroundTurns";

// Mounted by the common layout, including admin pages where ChatList is absent.
export function useBackgroundTurnNotifications() {
  const { showInfo } = useToast();
  const { t } = useTranslation();
  const navigate = useNavigate();
  const store = useStore<AppState>();
  useEffect(
    () =>
      subscribeBackgroundSettled((sessionId, awaitingInput, destination) => {
        const state = store.getState();
        const session = destination
          ? (controlPlaneApi.endpoints.getTeamSessionControlPlaneV1TeamsTeamIdSessionsSessionIdGet.select({
              teamId: destination.teamId,
              sessionId,
            })(state).data ??
            controlPlaneApi.endpoints.getTeamSessionsControlPlaneV1TeamsTeamIdSessionsGet
              .select({ teamId: destination.teamId })(state)
              .data?.find((item) => item.session_id === sessionId))
          : undefined;
        showInfo({
          summary: t(awaitingInput ? "rework.sidebar.chatList.awaitingInput" : "rework.sidebar.chatList.answerReady"),
          detail: session?.title || undefined,
          action: destination
            ? {
                label: t("rework.sidebar.chatList.openConversation"),
                onClick: () =>
                  navigate(
                    `/team/${destination.teamId}/managed-chat/${destination.agentInstanceId}?session=${sessionId}`,
                  ),
              }
            : undefined,
        });
      }),
    [showInfo, t, navigate, store],
  );
}
