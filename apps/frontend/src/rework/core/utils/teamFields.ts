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
import type { Team } from "../../../slices/controlPlane/controlPlaneOpenApi";

// Mirror the backend bounds (`CreateTeamRequest` / `UpdateTeamRequest`), so a
// form never submits a value the API would refuse on length alone.
export const MAX_TEAM_NAME_LENGTH = 180;
export const TEAM_DESCRIPTION_MIN_LENGTH = 20;
export const TEAM_DESCRIPTION_MAX_LENGTH = 500;

// Counted in code points, as the API and the database do: an emoji is one
// character, not the two UTF-16 units `String.length` reports.
export function isValidTeamDescription(value: string): boolean {
  const length = [...value.trim()].length;
  return length >= TEAM_DESCRIPTION_MIN_LENGTH && length <= TEAM_DESCRIPTION_MAX_LENGTH;
}

/** The description to show: the stored placeholder is French, so it is
 *  replaced by its translation in the user's language. */
export function teamDescriptionText(
  team: Pick<Team, "description" | "description_is_placeholder">,
  t: TFunction,
): string {
  if (team.description_is_placeholder) return t("rework.teamDescription.placeholderDisplay");
  return team.description ?? "";
}
