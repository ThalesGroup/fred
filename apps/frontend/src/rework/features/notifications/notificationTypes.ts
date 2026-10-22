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
import type { ColorTheme, IconType } from "@shared/utils/Type.ts";
import { enhancedControlPlaneApi } from "../../../slices/controlPlane/controlPlaneApiEnhancements";
import type { NotificationPage } from "../../../slices/controlPlane/controlPlaneOpenApi";
import { teamAgentsPath } from "../../components/pages/TeamAgentsPage/agentDeepLink.ts";

export type NotificationItem = NotificationPage["items"][number];
type NotificationOfType<K extends NotificationItem["type"]> = Extract<NotificationItem, { type: K }>;

export type NotificationDispatch = ThunkDispatch<unknown, unknown, UnknownAction>;

/** A tile button: either a route, or a call to the domain endpoint that owns the
 *  action (which keeps its own authorization and resolves the group). */
export type NotificationAction = { id: string; label: string; primary?: boolean; color?: ColorTheme } & (
  | { kind: "navigate"; to: string }
  | { kind: "call"; call: (dispatch: NotificationDispatch) => Promise<unknown> }
);

interface NotificationTypeDefinition<N> {
  /** Its subtree under `rework.notifications.types`, which holds its `name` and `description` too. */
  key: string;
  icon: IconType;
  category: NotificationCategory;
  title: (notification: N, t: TFunction) => string;
  body: (notification: N, t: TFunction) => string;
  /** Where a click on the tile leads, if anywhere. */
  link: (notification: N) => string | null;
  actions: (notification: N, t: TFunction) => NotificationAction[];
  /** Overrides the generic "Handled by" line, e.g. to name the outcome. */
  handled?: (notification: N, t: TFunction) => string | undefined;
  /** Asks for a decision: no close button and kept by "Clear all" until handled. */
  decision?: boolean;
}

const openAgent = (teamId: string, agentInstanceId: string, t: TFunction): NotificationAction => ({
  id: "open-agent",
  label: t("rework.notifications.actions.openAgent"),
  primary: true,
  kind: "navigate",
  to: teamAgentsPath(teamId, agentInstanceId),
});

const teamMembersPath = (teamId: string) => `/team/${teamId}/settings/members`;

/** A join request decision, through the route that owns it. */
function decideJoinRequest(
  notification: NotificationOfType<"team.join_requested">,
  decision: "accept" | "refuse",
): (dispatch: NotificationDispatch) => Promise<unknown> {
  const { endpoints } = enhancedControlPlaneApi;
  const args = { teamId: notification.payload.team_id, requestId: notification.payload.request_id };
  return (dispatch) =>
    dispatch(
      decision === "accept"
        ? endpoints.acceptTeamJoinRequestControlPlaneV1TeamsTeamIdJoinRequestsRequestIdAcceptPost.initiate(args)
        : endpoints.refuseTeamJoinRequestControlPlaneV1TeamsTeamIdJoinRequestsRequestIdRefusePost.initiate(args),
    ).unwrap();
}

const NOTIFICATION_TYPES: {
  [K in NotificationItem["type"]]: NotificationTypeDefinition<NotificationOfType<K>>;
} = {
  "agent.republish_needed": {
    key: "republishNeeded",
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
    link: ({ payload }) => teamAgentsPath(payload.team_id, payload.agent_instance_id),
    actions: ({ payload }, t) => [openAgent(payload.team_id, payload.agent_instance_id, t)],
    // Leaving the marketplace resolves the request, often with no one to name.
    handled: ({ handled_by_name: name, handled_outcome: outcome }, t) =>
      !name && outcome === "removed" ? t("rework.notifications.types.republishNeeded.handledRemoved") : undefined,
  },
  "agent.marketplace_removed": {
    key: "marketplaceRemoved",
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
    link: ({ payload }) => teamAgentsPath(payload.team_id, payload.agent_instance_id),
    actions: ({ payload }, t) => [openAgent(payload.team_id, payload.agent_instance_id, t)],
  },
  "team.join_requested": {
    key: "joinRequested",
    icon: "person_add",
    category: "action_required",
    decision: true,
    title: ({ payload }, t) =>
      t("rework.notifications.types.joinRequested.title", { name: payload.requester_name, team: payload.team_name }),
    // The requester's message, in full: it is what the admin decides on.
    body: ({ payload }) => payload.message ?? "",
    link: ({ payload }) => teamMembersPath(payload.team_id),
    // Refuse left, Accept right: the same order as the Members tab.
    actions: (notification, t) => [
      {
        id: "refuse",
        label: t("rework.notifications.actions.refuse"),
        primary: true,
        color: "error",
        kind: "call",
        call: decideJoinRequest(notification, "refuse"),
      },
      {
        id: "accept",
        label: t("rework.notifications.actions.accept"),
        primary: true,
        color: "success",
        kind: "call",
        call: decideJoinRequest(notification, "accept"),
      },
    ],
    handled: ({ handled_by_name: name, handled_outcome: outcome }, t) => {
      if (!name || (outcome !== "accepted" && outcome !== "refused")) return undefined;
      return t(`rework.notifications.types.joinRequested.${outcome}By`, { name });
    },
  },
  "team.join_request_answered": {
    key: "joinRequestAnswered",
    icon: "groups",
    category: "information",
    title: ({ payload }, t) =>
      t(`rework.notifications.types.joinRequestAnswered.${payload.outcome}Title`, { team: payload.team_name }),
    body: ({ payload }, t) => t(`rework.notifications.types.joinRequestAnswered.${payload.outcome}Body`),
    link: ({ payload }) => (payload.outcome === "accepted" ? teamAgentsPath(payload.team_id) : null),
    actions: ({ payload }, t) =>
      payload.outcome === "accepted"
        ? [
            {
              id: "open-team",
              label: t("rework.notifications.actions.openTeam"),
              primary: true,
              kind: "navigate",
              to: teamAgentsPath(payload.team_id),
            },
          ]
        : [],
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
  /** See `isPendingDecision`. */
  pendingDecision: boolean;
}

function handledLabel(notification: NotificationItem, t: TFunction): string {
  return notification.handled_by_name
    ? t("rework.notifications.handledBy", { name: notification.handled_by_name })
    : t("rework.notifications.handled");
}

/** A type this version does not know: a generic tile without link or buttons. */
const UNKNOWN_TYPE: NotificationTypeDefinition<NotificationItem> = {
  key: "unknown",
  icon: "notifications",
  category: "information",
  title: (_n, t) => t("rework.notifications.types.unknown.title"),
  body: () => "",
  link: () => null,
  actions: () => [],
};

const knownDefinition = (type: string) =>
  (NOTIFICATION_TYPES as Record<string, NotificationTypeDefinition<NotificationItem> | undefined>)[type];

const definitionOf = (notification: NotificationItem) => knownDefinition(notification.type) ?? UNKNOWN_TYPE;

/** A type's name and description for the platform settings; one this version
 *  does not know shows under its raw value. */
export function describeNotificationType(type: string, t: TFunction): { name: string; description: string } {
  const definition = knownDefinition(type);
  if (!definition) return { name: type, description: "" };
  return {
    name: t(`rework.notifications.types.${definition.key}.name`),
    description: t(`rework.notifications.types.${definition.key}.description`),
  };
}

/** Waiting for the recipient's decision: no close button, kept by "Clear all". */
export function isPendingDecision(notification: NotificationItem): boolean {
  return Boolean(definitionOf(notification).decision && !notification.handled_at);
}

/** Everything a tile shows. */
export function renderNotification(notification: NotificationItem, t: TFunction): RenderedNotification {
  const definition = definitionOf(notification);
  const handled = notification.handled_at
    ? (definition.handled?.(notification, t) ?? handledLabel(notification, t))
    : undefined;
  return {
    icon: definition.icon,
    category: definition.category,
    title: definition.title(notification, t),
    body: definition.body(notification, t),
    link: definition.link(notification),
    actions: handled ? [] : definition.actions(notification, t),
    handledLabel: handled,
    pendingDecision: isPendingDecision(notification),
  };
}
