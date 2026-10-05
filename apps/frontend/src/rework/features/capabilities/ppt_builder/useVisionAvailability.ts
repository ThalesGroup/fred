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

// Whether slides can be labelled by a vision model for this agent: its
// resolved chat model or any profile the team may pick must declare vision.

import {
  useAvailableModelProfilesQuery,
  useEffectiveChatModelQuery,
} from "../../../../slices/controlPlane/controlPlaneApiEnhancements";
import type { AvailableModelProfile, EffectiveChatModel } from "../../../../slices/controlPlane/controlPlaneOpenApi";

export interface VisionAvailability {
  /** `null` while the answer is unknown: the toggle is then left as stored. */
  available: boolean | null;
  /** The profiles the labelling-model selector may offer. */
  visionProfiles: AvailableModelProfile[];
}

export function visionAvailability(
  profiles: AvailableModelProfile[] | undefined,
  effective: EffectiveChatModel | undefined,
  effectiveKnown: boolean,
): VisionAvailability {
  const visionProfiles = (profiles ?? []).filter((p) => p.supports_vision);
  if (visionProfiles.length > 0 || effective?.supports_vision) return { available: true, visionProfiles };
  // Without both answers a missing vision flag proves nothing yet.
  if (profiles === undefined || !effectiveKnown) return { available: null, visionProfiles };
  return { available: false, visionProfiles };
}

export function useVisionAvailability(teamId?: string, agentInstanceId?: string): VisionAvailability {
  const profilesQuery = useAvailableModelProfilesQuery({ teamId: teamId ?? "" }, { skip: !teamId });
  const effectiveQuery = useEffectiveChatModelQuery(
    { teamId: teamId ?? "", agentInstanceId: agentInstanceId ?? "" },
    { skip: !teamId || !agentInstanceId },
  );
  // A new agent has no resolved model yet: the team's profiles decide alone.
  const effectiveKnown = !agentInstanceId || effectiveQuery.isSuccess || effectiveQuery.isError;
  const profiles = profilesQuery.isSuccess
    ? (profilesQuery.data.profiles ?? [])
    : profilesQuery.isError
      ? []
      : undefined;
  return visionAvailability(profiles, effectiveQuery.data, effectiveKnown);
}
