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

// Announces a turn that ended while its conversation was not shown.

import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { useStore } from "react-redux";

import { useToast } from "@shared/molecules/Toast/ToastProvider";
import { KeyCloakService } from "../../../security/KeycloakService";
import { enhancedControlPlaneApi } from "../../../slices/controlPlane/controlPlaneApiEnhancements";
import type { AppState } from "../../../common/store";
import { subscribeBackgroundSettled } from "./backgroundTurns";

export function conversationHref(teamId: string | undefined, agentInstanceId: string, sessionId: string): string {
  return `/team/${encodeURIComponent(teamId ?? "")}/managed-chat/${encodeURIComponent(agentInstanceId)}?session=${encodeURIComponent(sessionId)}`;
}

// Read the list already cached by the sidebar without delaying the toast on a network request.
function sessionTitle(state: AppState, spaceId: string, sessionId: string): string | undefined {
  const { data } = enhancedControlPlaneApi.endpoints.listSessions.select({ spaceId })(state);
  return data?.find((session) => session.session_id === sessionId)?.title || undefined;
}

export function useBackgroundTurnNotifications(navigate: (href: string) => void): void {
  const { t } = useTranslation();
  const { showInfo } = useToast();
  const store = useStore<AppState>();

  useEffect(
    () =>
      subscribeBackgroundSettled((turn) => {
        const actor = KeyCloakService.GetSessionIdentity();
        if (!actor || actor !== turn.scope.actor) return;
        const title = sessionTitle(store.getState(), turn.scope.spaceId, turn.sessionId);
        showInfo({
          summary: t(
            turn.awaitingInput ? "rework.sidebar.chatList.awaitingInput" : "rework.sidebar.chatList.answerReady",
          ),
          detail: title,
          action: {
            label: t("rework.sidebar.chatList.openConversation"),
            onClick: () => navigate(conversationHref(turn.teamId, turn.scope.agentInstanceId, turn.sessionId)),
          },
        });
      }),
    [store, navigate, showInfo, t],
  );
}
