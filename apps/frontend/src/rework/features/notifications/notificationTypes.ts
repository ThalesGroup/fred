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

// The frontend half of the notification type registry: a notification stores
// only its type and a payload snapshot, and everything shown is derived here,
// in the viewer's locale. Category and buttons are never stored.

import type { ThunkDispatch, UnknownAction } from "@reduxjs/toolkit";
import type { TFunction } from "i18next";
import type { NotificationCategory } from "@shared/molecules/NotificationTile/NotificationTile.tsx";
import type { IconType } from "@shared/utils/Type.ts";
import type { NotificationPage } from "../../../slices/controlPlane/controlPlaneOpenApi";

export type NotificationItem = NotificationPage["items"][number];
type NotificationOfType<K extends NotificationItem["type"]> = Extract<NotificationItem, { type: K }>;

export type NotificationDispatch = ThunkDispatch<unknown, unknown, UnknownAction>;

/** A tile button: either a route, or a call to the domain endpoint that owns the
 *  action (which keeps its own authorization and resolves the group). */
export type NotificationAction = { id: string; label: string; primary?: boolean } & (
  | { kind: "navigate"; to: string }
  | { kind: "call"; call: (dispatch: NotificationDispatch) => Promise<unknown> }
);

interface NotificationTypeDefinition<N> {
  icon: IconType;
  category: NotificationCategory;
  title: (notification: N, t: TFunction) => string;
  body: (notification: N, t: TFunction) => string;
  /** Where a click on the tile leads, if anywhere. */
  link: (notification: N) => string | null;
  actions: (notification: N, t: TFunction) => NotificationAction[];
}

const teamAgentsPath = (teamId: string) => `/team/${teamId}/agents`;

const openAgent = (teamId: string, t: TFunction): NotificationAction => ({
  id: "open-agent",
  label: t("rework.notifications.actions.openAgent"),
  primary: true,
  kind: "navigate",
  to: teamAgentsPath(teamId),
});

const NOTIFICATION_TYPES: {
  [K in NotificationItem["type"]]: NotificationTypeDefinition<NotificationOfType<K>>;
} = {
  "agent.republish_needed": {
    icon: "sync_problem",
    category: "action_required",
    title: (_n, t) => t("rework.notifications.types.republishNeeded.title"),
    body: ({ payload }, t) =>
      payload.team_name
        ? t("rework.notifications.types.republishNeeded.body", {
            editor: payload.editor_name,
            agent: payload.agent_name,
            team: payload.team_name,
          })
        : t("rework.notifications.types.republishNeeded.bodyNoTeam", {
            editor: payload.editor_name,
            agent: payload.agent_name,
          }),
    link: ({ payload }) => teamAgentsPath(payload.team_id),
    actions: ({ payload }, t) => [openAgent(payload.team_id, t)],
  },
  "agent.marketplace_removed": {
    icon: "unpublished",
    category: "information",
    title: (_n, t) => t("rework.notifications.types.marketplaceRemoved.title"),
    body: ({ payload }, t) => {
      // The reason labels are the agent card's own, so both read the same.
      const reason = t(`rework.agentMarketplace.removed.reasons.${payload.reason}`, {
        defaultValue: t("rework.agentMarketplace.removed.reasons.unknown"),
      });
      const subject = payload.team_name
        ? t("rework.notifications.types.marketplaceRemoved.body", {
            agent: payload.agent_name,
            team: payload.team_name,
            reason,
          })
        : t("rework.notifications.types.marketplaceRemoved.bodyNoTeam", { agent: payload.agent_name, reason });
      return payload.message
        ? `${subject} ${t("rework.agentMarketplace.removed.message", { message: payload.message })}`
        : subject;
    },
    link: ({ payload }) => teamAgentsPath(payload.team_id),
    actions: ({ payload }, t) => [openAgent(payload.team_id, t)],
  },
};

export interface RenderedNotification {
  icon: IconType;
  category: NotificationCategory;
  title: string;
  body: string;
  link: string | null;
  /** Empty once the notification is handled. */
  actions: NotificationAction[];
  handledLabel?: string;
}

function handledLabel(notification: NotificationItem, t: TFunction): string | undefined {
  if (!notification.handled_at) return undefined;
  if (notification.handled_by_name) {
    return t("rework.notifications.handledBy", { name: notification.handled_by_name });
  }
  return notification.handled_outcome === "removed"
    ? t("rework.notifications.handledRemoved")
    : t("rework.notifications.handled");
}

/** Everything a tile shows. A type this version does not know renders as a
 *  generic tile without link or buttons. */
export function renderNotification(notification: NotificationItem, t: TFunction): RenderedNotification {
  const definition = (NOTIFICATION_TYPES as Record<string, NotificationTypeDefinition<NotificationItem> | undefined>)[
    notification.type
  ];
  const handled = handledLabel(notification, t);
  if (!definition) {
    return {
      icon: "notifications",
      category: "information",
      title: t("rework.notifications.types.unknown.title"),
      body: "",
      link: null,
      actions: [],
      handledLabel: handled,
    };
  }
  return {
    icon: definition.icon,
    category: definition.category,
    title: definition.title(notification, t),
    body: definition.body(notification, t),
    link: definition.link(notification),
    actions: handled ? [] : definition.actions(notification, t),
    handledLabel: handled,
  };
}
