// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import type { TFunction } from "i18next";
import type {
  CreateAgentInstanceRequest,
  ManagedAgentInstanceSummary,
  MySpace,
  UpdateAgentInstanceRequest,
} from "../../../../slices/controlPlane/controlPlaneOpenApi";
import type { AgentFormPayload } from "./AgentFormModal/AgentFormModal";

export function resolveAgentSpace(spaces: MySpace[] | undefined, routeId: string | undefined) {
  // Navigation uses canonical ids. Only the established personal alias is resolved by context.
  const space = spaces?.find((item) => (routeId === "personal" ? item.kind === "personal" : item.id === routeId));
  return space && (space.kind === "team" || space.kind === "personal") ? space : undefined;
}

export function agentErrorText(error: unknown, t: TFunction): string {
  const status = (error as { status?: number | string } | null)?.status;
  const key =
    typeof status === "number"
      ? ({ 401: "unauthorized", 403: "forbidden", 404: "notFound", 409: "conflict", 422: "validation" }[status] ??
        (status >= 500 ? "server" : "unexpected"))
      : status === "FETCH_ERROR" || status === "TIMEOUT_ERROR"
        ? "network"
        : "unexpected";
  const detail = (error as { data?: { detail?: unknown } } | null)?.data?.detail;
  return t(`rework.weaverAgents.errors.${key}`) + (status === 422 && typeof detail === "string" ? ` ${detail}` : "");
}

export function createAgentRequest(payload: AgentFormPayload): CreateAgentInstanceRequest {
  return {
    template_id: payload.templateId,
    display_name: payload.displayName,
    role: payload.role || undefined,
    description: payload.description,
    usage_statement: payload.usageStatement,
    tuning_field_values: payload.tuningFieldValues as CreateAgentInstanceRequest["tuning_field_values"],
    capability_ids: payload.selectedCapabilityIds,
    capability_config_values: payload.capabilityConfigValues,
    // Model settings are preserved by omission until the existing control is connected.
  };
}

export function hasTuningChanges(
  values: ManagedAgentInstanceSummary["tuning_field_values"],
  saved: ManagedAgentInstanceSummary["tuning_field_values"],
) {
  return values !== saved && JSON.stringify(values) !== JSON.stringify(saved);
}

export function updateAgentRequest(
  payload: AgentFormPayload,
  saved: ManagedAgentInstanceSummary,
): UpdateAgentInstanceRequest {
  const request: UpdateAgentInstanceRequest = {};
  if (payload.displayName !== saved.display_name) request.display_name = payload.displayName;
  if (payload.role !== saved.role) request.role = payload.role;
  if (payload.description !== (saved.description ?? "")) request.description = payload.description;
  if (payload.usageStatement !== saved.usage_statement) request.usage_statement = payload.usageStatement;
  // The form retains the saved objects until edited. Omission preserves opaque values
  // and settings the current backend cannot yet change.
  if (hasTuningChanges(payload.tuningFieldValues, saved.tuning_field_values)) {
    request.tuning_field_values = payload.tuningFieldValues as UpdateAgentInstanceRequest["tuning_field_values"];
  }
  // As in Swift, a template with an inventory resubmits its selection for pod validation.
  if (payload.templateHasCapabilities) {
    request.capability_ids = payload.selectedCapabilityIds;
    request.capability_config_values = payload.capabilityConfigValues;
  }
  return request;
}
