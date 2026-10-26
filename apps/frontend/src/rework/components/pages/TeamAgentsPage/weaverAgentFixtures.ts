// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import type {
  AgentTemplateSummary,
  ManagedAgentInstanceSummary,
  MySpace,
} from "../../../../slices/controlPlane/controlPlaneOpenApi";

export const SPACE_A = "00000000-0000-0000-0000-000000000001";
export const SPACE_B = "00000000-0000-0000-0000-000000000002";
export const TEMPLATE: AgentTemplateSummary = {
  template_id: "00000000-0000-0000-0000-000000000003",
  source_runtime_id: "pod",
  source_agent_id: "custom",
  display_name: "Custom",
  description: "Template description",
  status: "available",
  category: "assistant",
  tags: [],
  capabilities: [],
  default_capability_ids: [],
  available_capabilities: [],
  supports_capabilities: true,
  team_instantiable: true,
  default_tuning_fields: [
    { key: "temperature", type: "number", title: "Temperature", default: 0.8 },
    { key: "prompt", type: "prompt", title: "Prompt", default: "CATALOG DEFAULT", ui: { group: "Prompts" } },
  ],
};
export const INSTANCE: ManagedAgentInstanceSummary = {
  agent_instance_id: "00000000-0000-0000-0000-000000000004",
  space_id: SPACE_A,
  template_id: TEMPLATE.template_id,
  source_runtime_id: "pod",
  source_agent_id: "custom",
  display_name: "Saved Agent",
  role: "Analyst",
  description: "Saved description",
  usage_statement: "Internal use",
  status: "enabled",
  tuning_field_values: { temperature: 0, prompt: "SAVED PROMPT", hidden: { retained: true } },
  selected_capability_ids: null,
  capability_config: { legacy: { schema_version: 7, config: { preserve: true } } },
  recommended_chat_profile_id: "saved-profile",
  created_at: "2026-10-25T10:00:00Z",
  updated_at: "2026-10-25T10:00:00Z",
  created_by: "author",
};
export const SPACES: MySpace[] = [SPACE_A, SPACE_B].map((id, index) => ({
  id,
  name: index ? "Personal" : "Team",
  kind: index ? "personal" : "team",
  parent_id: null,
  path: [id],
  personal_owner: index ? "reader" : null,
  organization_id: "org",
  roles: ["member"],
  inherited_roles: [],
}));
