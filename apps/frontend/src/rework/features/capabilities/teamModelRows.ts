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

import type { AvailableModelProfile } from "../../../slices/controlPlane/controlPlaneOpenApi";
import { modelLabel } from "./ReasoningChip";

export interface TeamModelRow {
  capabilityId: string;
  /** The profile that stands for the model: a preferred one when it belongs to it, else its first. */
  profileId: string;
  label: string;
  reasoningAvailable: boolean;
}

/**
 * One row per model of the team's `available-models` list, which has one entry per chat profile.
 * A row is keyed by the first of `preferredProfileIds` that belongs to its model, else by its first profile.
 */
export function teamModelRows(
  profiles: readonly AvailableModelProfile[],
  preferredProfileIds: readonly (string | null | undefined)[] = [],
): TeamModelRow[] {
  const rank = (profileId: string) => {
    const index = preferredProfileIds.indexOf(profileId);
    return index === -1 ? preferredProfileIds.length : index;
  };
  const rows = new Map<string, TeamModelRow>();
  for (const profile of profiles) {
    const existing = rows.get(profile.capability_id);
    if (existing && rank(existing.profileId) <= rank(profile.profile_id)) continue;
    rows.set(profile.capability_id, {
      capabilityId: profile.capability_id,
      profileId: profile.profile_id,
      label: modelLabel(profile.display_name, profile.name, profile.capability_id) ?? profile.profile_id,
      reasoningAvailable: profile.reasoning_available ?? false,
    });
  }
  return [...rows.values()];
}

/** The row of the model `profileId` belongs to, whichever of its profiles keys the row. */
export function rowForProfile(
  rows: readonly TeamModelRow[],
  profiles: readonly AvailableModelProfile[],
  profileId: string | null | undefined,
): TeamModelRow | undefined {
  if (!profileId) return undefined;
  const capabilityId = profiles.find((profile) => profile.profile_id === profileId)?.capability_id;
  return rows.find((row) => row.capabilityId === capabilityId);
}
