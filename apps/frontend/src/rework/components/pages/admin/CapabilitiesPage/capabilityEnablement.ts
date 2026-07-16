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

// Pure enablement logic for the admin Capabilities dashboard (CAPAB-01 / #1981,
// RFC §8.5). Kept framework-free so the tri-state derivation and settings-form
// seeding are unit-testable without rendering.

import type { CapabilityEnablementItem, FieldSpec } from "../../../../../slices/controlPlane/controlPlaneOpenApi";

/**
 * Per-team enablement state for one capability (RFC §8.5 tri-state).
 *
 * - `enabled` — the team carries an explicit `enabled` grant.
 * - `inherited` — the capability is platform default-on and the team has no
 *   explicit grant, so it is on by inheritance.
 * - `off` — neither an explicit grant nor a default-on inheritance.
 *
 * Note: the aggregate list carries `enabled_team_ids` + `default_on` but not the
 * per-team `disabled` opt-out tuples, so an explicit opt-out of a default-on
 * capability is not distinguishable from `inherited` here (backend seam, #1980).
 */
export type TeamCapabilityState = "enabled" | "inherited" | "off";

export function teamCapabilityState(
  capability: Pick<CapabilityEnablementItem, "default_on" | "enabled_team_ids">,
  teamId: string,
): TeamCapabilityState {
  if ((capability.enabled_team_ids ?? []).includes(teamId)) {
    return "enabled";
  }
  return capability.default_on ? "inherited" : "off";
}

/** Whether the capability is effectively active for the team (explicit or inherited). */
export function isCapabilityOnForTeam(
  capability: Pick<CapabilityEnablementItem, "default_on" | "enabled_team_ids">,
  teamId: string,
): boolean {
  return teamCapabilityState(capability, teamId) !== "off";
}

/** Count of teams carrying an explicit `enabled` grant (the catalog column). */
export function enabledTeamCount(capability: Pick<CapabilityEnablementItem, "enabled_team_ids">): number {
  return (capability.enabled_team_ids ?? []).length;
}

/**
 * Seed the enable-with-settings form values from the field specs' declared
 * defaults. Existing settings (rare on the admin surface) override the defaults.
 */
export function seedSettingsFromFields(
  fields: FieldSpec[] | undefined,
  existing?: Record<string, unknown>,
): Record<string, unknown> {
  const seeded: Record<string, unknown> = {};
  for (const field of fields ?? []) {
    if (existing && field.key in existing) {
      seeded[field.key] = existing[field.key];
    } else if (field.default !== undefined && field.default !== null) {
      seeded[field.key] = field.default;
    }
  }
  return seeded;
}
