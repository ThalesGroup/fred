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

import type { TeamMarketplaceSettings } from "../../../../../slices/legacyControlPlane/legacyControlPlaneOpenApi";

/** A team's position on the publication switch: its own override, or Default. */
export type PublishingChoice = "disabled" | "default" | "enabled";

export const PUBLISHING_CHOICES: PublishingChoice[] = ["disabled", "default", "enabled"];

/** The default row has no Default position of its own. */
export const DEFAULT_CHOICES: Exclude<PublishingChoice, "default">[] = ["disabled", "enabled"];

/** Selected Enabled reads as success, Disabled as error; Default keeps the group colour. */
export function choiceColor(choice: PublishingChoice): "success" | "error" | undefined {
  if (choice === "default") return undefined;
  return choice === "enabled" ? "success" : "error";
}

export function publishingChoice(team: TeamMarketplaceSettings): PublishingChoice {
  const override = team.agents_publishing_enabled_override;
  if (override === null || override === undefined) return "default";
  return override ? "enabled" : "disabled";
}

export function overrideForChoice(choice: PublishingChoice): boolean | null {
  return choice === "default" ? null : choice === "enabled";
}

/** True when moving the team to `choice` turns its effective switch from on to off. */
export function turnsTeamOff(
  team: TeamMarketplaceSettings,
  choice: PublishingChoice,
  defaultEnabled: boolean,
): boolean {
  const after = choice === "default" ? defaultEnabled : choice === "enabled";
  return team.agents_publishing_enabled && !after;
}

/** A quota is a whole number of at least 1; anything else is refused. */
export function parseQuota(text: string): number | null {
  const trimmed = text.trim();
  if (!/^\d+$/.test(trimmed)) return null;
  const value = Number(trimmed);
  return value >= 1 ? value : null;
}
