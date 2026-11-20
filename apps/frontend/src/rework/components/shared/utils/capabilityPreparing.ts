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

import type { ManagedAgentInstanceSummary } from "../../../../slices/controlPlane/controlPlaneOpenApi.ts";

// A capability with a readiness hook says what it prepares under
// `capability.<id>.preparing`. The pending capability is not persisted, so the
// text is shown only when exactly one of the agent's capabilities declares one.
export function capabilityPreparingKey(
  instance: Pick<ManagedAgentInstanceSummary, "capability_config" | "selected_capability_ids">,
  exists: (key: string) => boolean,
): string | undefined {
  const selected = instance.selected_capability_ids;
  const keys = Object.keys(instance.capability_config ?? {})
    .filter((id) => !selected || selected.includes(id))
    .map((id) => `capability.${id}.preparing`)
    .filter(exists);
  return keys.length === 1 ? keys[0] : undefined;
}
