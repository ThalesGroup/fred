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
  ChatControlDescriptor,
  EffectiveChatModel,
  SelectableChatModel,
} from "../../../slices/controlPlane/controlPlaneOpenApi";

/** The agent's recommended model among the selectable ones: the row of the resolved model. */
export function recommendedModelRow(effective: EffectiveChatModel | undefined): SelectableChatModel | undefined {
  return effective?.selectable_models?.find((row) => row.capability_id === effective.capability_id);
}

/** The model the next turn runs on: the conversation's choice when still offered, else the recommended one. */
export function currentModelRow(
  effective: EffectiveChatModel | undefined,
  chatProfileId: string | null,
): SelectableChatModel | undefined {
  const chosen = chatProfileId
    ? effective?.selectable_models?.find((row) => row.profile_id === chatProfileId)
    : undefined;
  return chosen ?? recommendedModelRow(effective);
}

/**
 * Whether the composer shows the reasoning row: the platform emitted the
 * control and the current model's reasoning is enabled. Without a row (locked
 * choice, older backend) the resolved model decides; unknown keeps the control.
 */
export function offersReasoning(
  chatControls: readonly ChatControlDescriptor[],
  effective: EffectiveChatModel | undefined,
  chatProfileId: string | null,
): boolean {
  if (!chatControls.some((control) => control.widget === "reasoning_toggle")) return false;
  const row = currentModelRow(effective, chatProfileId);
  if (row) return row.reasoning_enabled ?? false;
  return effective?.reasoning_enabled !== false;
}
