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
  ModelOfferKey,
  PreparationModels,
  PreparationModelOffer,
} from "../../../slices/controlPlane/controlPlaneOpenApi";

// A lossless UI key, never a profile or a model name inferred from a label.
export const modelChoiceKey = (key: ModelOfferKey): string => JSON.stringify([key.source_id, key.upstream_model_id]);
export function parseModelChoice(value: string): ModelOfferKey {
  const key: unknown = JSON.parse(value);
  if (!Array.isArray(key) || key.length !== 2 || key.some((part) => typeof part !== "string" || !part)) {
    throw new Error("The saved model choice must be selected again");
  }
  return { source_id: key[0], upstream_model_id: key[1] };
}
export function recommendedModelRow(models: PreparationModels | undefined): PreparationModelOffer | undefined {
  if (models?.requires_reselection && models.legacy_profile_id) return undefined;
  const key = models?.recommendation ?? models?.default;
  return key ? models?.offers.find((row) => modelChoiceKey(row.key) === modelChoiceKey(key)) : undefined;
}
export function currentModelRow(
  models: PreparationModels | undefined,
  choice: string | null,
): PreparationModelOffer | undefined {
  return choice ? models?.offers.find((row) => modelChoiceKey(row.key) === choice) : recommendedModelRow(models);
}
export function offersReasoning(
  controls: readonly ChatControlDescriptor[],
  _models: PreparationModels | undefined,
  _choice: string | null,
): boolean {
  return controls.some((control) => control.widget === "reasoning_toggle");
}
export function offerLabel(offer: PreparationModelOffer): string {
  return `${offer.metadata?.display_name ?? offer.key.upstream_model_id} (${offer.key.source_id})`;
}
