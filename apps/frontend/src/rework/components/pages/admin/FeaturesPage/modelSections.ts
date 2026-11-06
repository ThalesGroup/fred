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
  CapabilityEnablementItem,
  DiscoverySourceStatus,
} from "../../../../../slices/controlPlane/controlPlaneOpenApi";

export function splitModelSections(models: CapabilityEnablementItem[]) {
  return {
    manual: models.filter((model) => !model.model_discovery_source_id),
    discovered: models.filter((model) => Boolean(model.model_discovery_source_id)),
  };
}

export function partitionDiscoveredModels(models: CapabilityEnablementItem[], sources: DiscoverySourceStatus[]) {
  const sourceById = new Map(sources.map((source) => [source.source_id, source]));
  const isUnavailable = (model: CapabilityEnablementItem) => {
    const source = sourceById.get(model.model_discovery_source_id ?? "");
    if (!source) return false;
    if (source.last_success_at) return !(source.available_models ?? []).some((item) => item.id === model.id);
    return (source.removed_models ?? []).some((item) => item.id === model.id);
  };
  const available = models.filter((model) => !isUnavailable(model));
  const unavailableIds = new Set(models.filter(isUnavailable).map((model) => model.id));
  const removedById = new Map(
    sources.flatMap((source) =>
      (source.removed_models ?? []).map((model) => [model.id, { sourceId: source.source_id, model }] as const),
    ),
  );
  const advertisedUnavailable = models.filter((model) => unavailableIds.has(model.id) && removedById.has(model.id));
  const knownIds = new Set(models.map((model) => model.id));
  const historicalUnavailable: CapabilityEnablementItem[] = [...removedById.entries()]
    .filter(([id]) => !knownIds.has(id))
    .map(([id, { sourceId, model }]) => ({
      id,
      name: model.name,
      version: "1",
      icon: "model",
      team_scope: "admin_gated",
      default_on: false,
      kind: "model",
      model_discovery_source_id: sourceId,
      model_display_name: model.name,
      model_context_window_tokens: model.context_window_tokens,
      model_max_input_tokens: model.max_input_tokens,
      model_max_output_tokens: model.max_output_tokens,
    }));
  historicalUnavailable.forEach((model) => unavailableIds.add(model.id));
  return {
    available,
    listed: [...available, ...advertisedUnavailable, ...historicalUnavailable],
    unavailableIds,
  };
}
