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

import type {
  CreationAssistantModelOption,
  CreationAssistantSettings,
} from "../../../../../slices/controlPlane/controlPlaneOpenApi";

export type ReasoningEffort = NonNullable<CreationAssistantSettings["reasoning_effort"]>;
type ReasoningLevel = Exclude<ReasoningEffort, "off">;

const LEVELS: ReasoningLevel[] = ["low", "medium", "high"];
/** What an on/off model stores for "on"; the pod sends the profile's own level. */
export const REASONING_ON: ReasoningLevel = "medium";

export type ReasoningControl =
  | { kind: "levels"; levels: ReasoningLevel[] }
  | { kind: "switch" }
  // Shown as a switch; the stored level is kept since the pod clamps it.
  | { kind: "unknown" }
  | { kind: "unsupported" };

/** The reasoning control a model offers; an unknown model gets a switch and the pod decides. */
export function reasoningControl(option: CreationAssistantModelOption | undefined): ReasoningControl {
  if (!option) return { kind: "unknown" };
  if (option.supports_reasoning === false) return { kind: "unsupported" };
  const levels = option.reasoning_efforts ?? [];
  return levels.length >= 2 ? { kind: "levels", levels } : { kind: "switch" };
}

/** `value` made valid for `control`: same rule as the pod's clamp (nearest level, ties go up). */
export function normalizeReasoningEffort(value: ReasoningEffort, control: ReasoningControl): ReasoningEffort {
  if (value === "off" || control.kind === "unsupported" || control.kind === "unknown") return value;
  if (control.kind === "switch") return REASONING_ON;
  if (control.levels.includes(value)) return value;
  const wanted = LEVELS.indexOf(value);
  const distance = (level: ReasoningLevel) => Math.abs(LEVELS.indexOf(level) - wanted);
  return control.levels.reduce((best, level) =>
    distance(level) < distance(best) ||
    (distance(level) === distance(best) && LEVELS.indexOf(level) > LEVELS.indexOf(best))
      ? level
      : best,
  );
}
