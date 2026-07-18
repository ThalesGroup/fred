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
 * The team's *explicit* tri-state position — what the admin actually chose,
 * as opposed to `teamCapabilityState` which is the *effective* access after
 * inheritance. `default` means "no explicit tuple: the platform default
 * applies", whether that default is on or off. Drives the segmented control
 * in the team matrix drawer. Opt-out beats grant, mirroring the FGA schema.
 */
export type TeamCapabilityChoice = "disabled" | "default" | "enabled";

export function teamCapabilityChoice(capability: EnablementFacts, teamId: string): TeamCapabilityChoice {
  if ((capability.disabled_team_ids ?? []).includes(teamId)) {
    return "disabled";
  }
  if ((capability.enabled_team_ids ?? []).includes(teamId)) {
    return "enabled";
  }
  return "default";
}

/**
 * Reserved id for the synthetic "All personal spaces" row (RFC §8.4). It is not
 * a real team id, so it can never collide with one, and it keys the same
 * optimistic `pendingByTeam` spinner machinery as ordinary team rows.
 */
export const PERSONAL_SCOPE_ROW_ID = "__personal_scope__";

/**
 * True for a personal-space team id (`personal-{uid}`). Mirrors fred-core's
 * `is_personal_team_id` prefix check — the admin's own personal team is removed
 * from the ordinary team rows because the synthetic class row governs it.
 */
export function isPersonalTeamId(teamId: string | undefined | null): boolean {
  return typeof teamId === "string" && teamId.startsWith("personal-");
}

/** Drop every personal space from the team roster (RFC §8.4 — the class row
 * governs them, so they must not appear as ordinary per-team rows). */
export function excludePersonalTeams<T extends { id: string }>(teams: T[]): T[] {
  return teams.filter((team) => !isPersonalTeamId(team.id));
}

/**
 * The personal-space class tri-state position, straight from the capability's
 * `personal_scope` (RFC §8.4). Drives the synthetic "All personal spaces" row's
 * segmented control, exactly as `teamCapabilityChoice` drives a team row.
 * Absent (older payloads) reads as `default`.
 */
export function capabilityPersonalScopeChoice(
  capability: Pick<CapabilityEnablementItem, "personal_scope">,
): TeamCapabilityChoice {
  return capability.personal_scope ?? "default";
}

/**
 * Matrix drawer ordering: teams with an explicit position first (enabled,
 * then disabled), the default majority last — on a ~100-team roster the
 * handful of explicit overrides is what the admin came to see. Alphabetical
 * within each group. Returns a new array; the input is not mutated.
 */
const CHOICE_RANK: Record<TeamCapabilityChoice, number> = { enabled: 0, disabled: 1, default: 2 };

export function sortTeamsForMatrix<T extends { id: string; name: string }>(
  teams: T[],
  capability: EnablementFacts,
): T[] {
  return [...teams].sort((a, b) => {
    const rank =
      CHOICE_RANK[teamCapabilityChoice(capability, a.id)] - CHOICE_RANK[teamCapabilityChoice(capability, b.id)];
    return rank !== 0 ? rank : a.name.localeCompare(b.name);
  });
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
  // Explicit tuples can name personal spaces (per-space grants, plus leftovers
  // from the withdrawn personal_defaults seeding). Those are counted by
  // `personalSpaceCount`, and `total_team_count` never includes them — mixing
  // them in here would double-count or drive the subtraction negative.
  const enabled = (capability.enabled_team_ids ?? []).filter((id) => !isPersonalTeamId(id));
  const disabled = (capability.disabled_team_ids ?? []).filter((id) => !isPersonalTeamId(id));
  if (!capability.default_on) {
    return enabled.length;
  }
  const total = capability.total_team_count ?? 0;
  if (total <= 0) {
    return null;
  }
  // An opt-out only subtracts if it names a team that is actually in the roster;
  // clamp so a stale tuple can never drive the count below zero.
  return Math.max(0, total - disabled.length);
}

/**
 * How many personal spaces can actually use this capability — the personal-class
 * companion of `enabledTeamCount`, following the same FGA precedence (RFC §8.4):
 *
 * - **Class access on** (`personal_scope: enabled`, or `default` while the
 *   capability is default-on) — every personal space inherits except explicit
 *   per-space opt-outs: `total_personal_space_count - opted-out`. Returns `null`
 *   ("unknown") when the backend had no user directory (count is 0), mirroring
 *   the team-side unknown case.
 * - **Class access off** — only explicit per-space `enabled` grants count
 *   (they survive both class-off and `personal_disabled`), so the answer is
 *   exact.
 */
export function personalSpaceCount(
  capability: Pick<
    CapabilityEnablementItem,
    "default_on" | "enabled_team_ids" | "disabled_team_ids" | "personal_scope" | "total_personal_space_count"
  >,
): number | null {
  const scope = capabilityPersonalScopeChoice(capability);
  const classOn = scope === "enabled" || (scope === "default" && capability.default_on);
  if (!classOn) {
    return (capability.enabled_team_ids ?? []).filter(isPersonalTeamId).length;
  }
  const total = capability.total_personal_space_count ?? 0;
  if (total <= 0) {
    return null;
  }
  const optedOut = (capability.disabled_team_ids ?? []).filter(isPersonalTeamId).length;
  return Math.max(0, total - optedOut);
}

/**
 * Whether no team can currently use this capability — advertised by a pod, but
 * reaching nobody (not default-on, and no team was ever granted it).
 *
 * Drives the dimmed row treatment: these rows are real and actionable, just
 * inert, so they should recede rather than compete with capabilities in use.
 * Derived from `enabledTeamCount` + `personalSpaceCount` so the three can never
 * disagree about what "reaches nobody" means. A default-on capability is never
 * unused — even the unknown-roster case (`null`) reaches teams or personal
 * spaces; we just cannot say how many.
 */
export function isCapabilityUnused(
  capability: Pick<
    CapabilityEnablementItem,
    | "default_on"
    | "enabled_team_ids"
    | "disabled_team_ids"
    | "total_team_count"
    | "personal_scope"
    | "total_personal_space_count"
  >,
): boolean {
  return enabledTeamCount(capability) === 0 && personalSpaceCount(capability) === 0;
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
 * Which message (if any) the team matrix drawer should show above/instead of
 * the team list — priority order matters: a fetch in flight beats a fetch
 * error beats "the registry has no teams at all" beats "your search matched
 * nothing". Centralized so the component can't accidentally show two of
 * these at once, or collapse a real error into a silent empty list.
 */
export type TeamMatrixStatus = "loading" | "error" | "registryEmpty" | "searchEmpty" | "ready";

export function teamMatrixStatus(params: {
  teamsLoading: boolean;
  teamsError: boolean;
  registryEmpty: boolean;
  hasQuery: boolean;
  visibleCount: number;
}): TeamMatrixStatus {
  if (params.teamsLoading) return "loading";
  if (params.teamsError) return "error";
  if (params.registryEmpty) return "registryEmpty";
  if (params.hasQuery && params.visibleCount === 0) return "searchEmpty";
  return "ready";
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
