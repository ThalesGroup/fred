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

/**
 * Canonical personal-space identity check for the frontend.
 *
 * Mirrors the backend convention (`fred_core.common.team_id.is_personal_team_id`
 * plus the bare-`"personal"` alias the backend also accepts, see
 * `teams/system.py`): a personal team id is shaped `personal-<uuid>`, but before
 * the bootstrap query resolves the UI routes through the literal `"personal"`
 * placeholder (`activeTeam?.id ?? "personal"` in the marketplace redirect and the
 * team nav). Both must read as personal so the banner picks its brand violet on
 * the very first render instead of falling through to the name-hashed colour.
 */
export function isPersonalTeamId(teamId: string | null | undefined): boolean {
  return teamId === "personal" || Boolean(teamId && teamId.startsWith("personal-"));
}

/**
 * Canonical personal-space team id for one user.
 *
 * Mirrors `fred_core.common.team_id.personal_team_id` (`personal-<uid>`). The UI
 * routes through the bare `"personal"` alias before bootstrap resolves, but the
 * `/fs` backend checks ReBAC against this canonical id — so any filesystem path
 * built from a personal route must canonicalize the alias first.
 */
export function personalTeamId(userUid: string): string {
  return `personal-${userUid}`;
}
