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
 * - `inherited` — the capability is platform default-on and the team has neither
 *   an explicit grant nor an explicit opt-out, so it is on by inheritance.
 * - `off` — an explicit `disabled` opt-out, or no grant and no default-on.
 *
 * Precedence mirrors the FGA schema: an explicit `disabled` opt-out beats both
 * an `enabled` grant and default-on inheritance (see the ReBAC integration test
 * "disable overrides enable"), so it is checked first.
 */
export type TeamCapabilityState = "enabled" | "inherited" | "off";

type EnablementFacts = Pick<CapabilityEnablementItem, "default_on" | "enabled_team_ids" | "disabled_team_ids">;

export function teamCapabilityState(capability: EnablementFacts, teamId: string): TeamCapabilityState {
  if ((capability.disabled_team_ids ?? []).includes(teamId)) {
    return "off";
  }
  if ((capability.enabled_team_ids ?? []).includes(teamId)) {
    return "enabled";
  }
  return capability.default_on ? "inherited" : "off";
}

/** Whether the capability is effectively active for the team (explicit or inherited). */
export function isCapabilityOnForTeam(capability: EnablementFacts, teamId: string): boolean {
  return teamCapabilityState(capability, teamId) !== "off";
}

/**
 * How many teams can actually use this capability (the catalog column).
 *
 * Two regimes, because access is granted two different ways:
 * - **Not default-on** — only explicit grants count, so the answer is exact.
 * - **Default-on** — every team inherits access except those that opted out, so
 *   the answer is `total teams - opted-out teams`. `total_team_count` is the
 *   platform-wide roster from the backend, NOT the caller-scoped `/teams` list.
 *
 * Returns `null` for a default-on capability when the backend could not supply a
 * roster (Keycloak disabled → `total_team_count` is 0): the truthful answer is
 * "unknown", and rendering 0 would read as "nobody has this" — the exact
 * opposite of the truth for a capability that is on for everyone.
 */
export function enabledTeamCount(
  capability: Pick<
    CapabilityEnablementItem,
    "default_on" | "enabled_team_ids" | "disabled_team_ids" | "total_team_count"
  >,
): number | null {
  if (!capability.default_on) {
    return (capability.enabled_team_ids ?? []).length;
  }
  const total = capability.total_team_count ?? 0;
  if (total <= 0) {
    return null;
  }
  // An opt-out only subtracts if it names a team that is actually in the roster;
  // clamp so a stale tuple can never drive the count below zero.
  const optedOut = (capability.disabled_team_ids ?? []).length;
  return Math.max(0, total - optedOut);
}

/**
 * Whether no team can currently use this capability — advertised by a pod, but
 * reaching nobody (not default-on, and no team was ever granted it).
 *
 * Drives the dimmed row treatment: these rows are real and actionable, just
 * inert, so they should recede rather than compete with capabilities in use.
 * Derived from `enabledTeamCount` so the two can never disagree about what
 * "zero teams" means. A default-on capability is never unused — even the
 * unknown-roster case reaches teams; we just cannot say how many.
 */
export function isCapabilityUnused(
  capability: Pick<
    CapabilityEnablementItem,
    "default_on" | "enabled_team_ids" | "disabled_team_ids" | "total_team_count"
  >,
): boolean {
  return enabledTeamCount(capability) === 0;
}

/**
 * Case-insensitive name filter for the team matrix drawer. A blank (or
 * whitespace-only) query means "no filter", not "match nothing" — production
 * rosters run ~100 teams, so the drawer starts from the full list.
 */
export function filterTeamsByName<T extends { name: string }>(teams: T[], query: string): T[] {
  const normalized = query.trim().toLowerCase();
  if (!normalized) {
    return teams;
  }
  return teams.filter((team) => team.name.toLowerCase().includes(normalized));
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
