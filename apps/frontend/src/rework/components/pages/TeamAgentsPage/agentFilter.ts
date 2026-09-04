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

// Search predicate for the team agents list. Kept out of the page so it can be
// tested without mounting a container full of RTK Query hooks.

import type { ManagedAgentInstanceSummary } from "../../../../slices/controlPlane/controlPlaneOpenApi";

/** Fields the card shows, so the fields a search is expected to reach:
 * the name, the role rendered under it, and the description. */
function haystack(instance: ManagedAgentInstanceSummary): string {
  return [instance.display_name, instance.role, instance.description].filter(Boolean).join("\n").toLowerCase();
}

/**
 * Case-insensitive substring match over name + description. An empty or
 * whitespace-only query matches everything, so the caller can pass the raw
 * input value straight through.
 */
export function filterAgents(instances: ManagedAgentInstanceSummary[], query: string): ManagedAgentInstanceSummary[] {
  const q = query.trim().toLowerCase();
  if (!q) return instances;
  return instances.filter((instance) => haystack(instance).includes(q));
}
