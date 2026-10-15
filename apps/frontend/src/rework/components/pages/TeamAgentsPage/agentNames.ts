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

import type { ManagedAgentInstanceSummary } from "../../../../slices/controlPlane/controlPlaneOpenApi";

/** Code of the server's 409 when another agent of the team has the name. */
export const AGENT_NAME_CONFLICT = "agent_name_conflict";

/** Names are unique per team ignoring case and surrounding spaces, as on the server. */
export function normalizeAgentName(name: string): string {
  return name.trim().toLowerCase();
}

/** The team's names, normalised, without the agent being edited. */
export function takenAgentNames(
  instances: ManagedAgentInstanceSummary[],
  excludeAgentInstanceId?: string,
): Set<string> {
  return new Set(
    instances
      .filter((instance) => instance.agent_instance_id !== excludeAgentInstanceId)
      .map((instance) => normalizeAgentName(instance.display_name)),
  );
}

export function isAgentNameTaken(name: string, taken: ReadonlySet<string>): boolean {
  const normalized = normalizeAgentName(name);
  return normalized !== "" && taken.has(normalized);
}

/** `name` when free, else the first free `name (<word> n)` from 1 — the duplicate's starting
 *  name, in the same form as the server's copies ("copie" / "copy" from the UI language). */
export function freeAgentName(name: string, taken: ReadonlySet<string>, word: string): string {
  const base = name.trim();
  if (!isAgentNameTaken(base, taken)) return base;
  let n = 1;
  while (isAgentNameTaken(`${base} (${word} ${n})`, taken)) n += 1;
  return `${base} (${word} ${n})`;
}

/** True for the server's name conflict, on a create or rename error body. */
export function isAgentNameConflict(error: unknown): boolean {
  const detail = (error as { data?: { detail?: unknown } } | null)?.data?.detail;
  return (detail as { code?: unknown } | null)?.code === AGENT_NAME_CONFLICT;
}
