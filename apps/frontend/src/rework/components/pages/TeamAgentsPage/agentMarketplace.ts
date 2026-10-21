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

import type { TFunction } from "i18next";
import type {
  AgentTemplateSummary,
  ManagedAgentInstanceSummary,
  TeamWithPermissions,
} from "../../../../slices/legacyControlPlane/legacyControlPlaneOpenApi";

export type PublishBlockedReason = "templateNotPublic" | "teamPrivate" | "quotaReached";

export interface PublishAvailability {
  kind: "publish" | "republish";
  blockedReason?: PublishBlockedReason;
}

export const isPublished = (instance: ManagedAgentInstanceSummary): boolean =>
  instance.marketplace?.state === "published";

/** True once the team has used its whole quota of published agents. */
export function isQuotaReached(team: TeamWithPermissions | null | undefined): boolean {
  const marketplace = team?.marketplace;
  return !!marketplace && marketplace.published_count >= marketplace.agents_publish_quota;
}

/** Switch on and public team: marketplace actions and visible states are available. */
export function teamCanPublish(team: TeamWithPermissions | null | undefined, isPersonalTeam: boolean): boolean {
  return !isPersonalTeam && !!team?.marketplace?.agents_publishing_enabled && team.visibility === "public";
}

/** A card's Publish/Republish item, or null when hidden (not an editor, personal
 * space, switch off). Republishing ignores the quota; publishing after a removal
 * counts against it. */
export function publishAvailability({
  instance,
  team,
  canPublish,
  isPersonalTeam,
  templates,
}: {
  instance: ManagedAgentInstanceSummary;
  team: TeamWithPermissions | null | undefined;
  canPublish: boolean;
  isPersonalTeam: boolean;
  /** Public agent types of the team; undefined while unknown (never greys). */
  templates: AgentTemplateSummary[] | undefined;
}): PublishAvailability | null {
  if (!canPublish || isPersonalTeam || !team?.marketplace?.agents_publishing_enabled) return null;
  const kind = isPublished(instance) ? "republish" : "publish";
  if (templates && templates.length > 0 && !templates.some((tpl) => tpl.template_id === instance.template_id)) {
    return { kind, blockedReason: "templateNotPublic" };
  }
  if ((team.visibility ?? "private") !== "public") return { kind, blockedReason: "teamPrivate" };
  if (kind === "publish" && isQuotaReached(team)) return { kind, blockedReason: "quotaReached" };
  return { kind };
}

export function publishBlockedText(reason: PublishBlockedReason, t: TFunction): string {
  return t(`rework.agentMarketplace.blocked.${reason}`);
}

/** Files an importer receives: one entry per selected capability that declares file slots. */
export function agentFileCapabilities(
  instance: ManagedAgentInstanceSummary,
  templates: AgentTemplateSummary[] | undefined,
  t: TFunction,
): string[] {
  const template = templates?.find((tpl) => tpl.template_id === instance.template_id);
  const selected = new Set(instance.selected_capability_ids ?? template?.default_capability_ids ?? []);
  return (template?.available_capabilities ?? [])
    .filter((capability) => selected.has(capability.id) && (capability.assets?.length ?? 0) > 0)
    .map((capability) => t(capability.name, { defaultValue: capability.id }));
}

const MARKETPLACE_CODES = [
  "marketplace_version_conflict",
  "marketplace_quota_reached",
  "marketplace_team_private",
  "marketplace_switch_off",
  "marketplace_template_not_public",
  "marketplace_agent_inactive",
  "marketplace_personal_space",
  "marketplace_forbidden",
  "marketplace_agent_not_found",
  "marketplace_entry_not_found",
  "marketplace_runtime_unavailable",
  "marketplace_capability_not_exportable",
];

export interface MarketplaceErrorView {
  /** Stale card: the caller refetches the list. */
  stale: boolean;
  message: string;
}

/** Localized message for a refused publish, removal or Hide (`detail.code`). */
export function marketplaceErrorView(
  error: unknown,
  t: TFunction,
  capabilityName: (capabilityId: string) => string,
): MarketplaceErrorView {
  const data = (error as { data?: { detail?: unknown } } | null)?.data;
  const detail = data?.detail as { code?: string; capability_id?: string } | undefined;
  const code = typeof detail === "object" && detail ? detail.code : undefined;
  if (code && MARKETPLACE_CODES.includes(code)) {
    return {
      stale: code === "marketplace_version_conflict",
      message: t(`rework.agentMarketplace.errors.${code}`, {
        capability: detail?.capability_id ? capabilityName(detail.capability_id) : "",
      }),
    };
  }
  return { stale: false, message: t("rework.agentCard.unexpectedError") };
}
