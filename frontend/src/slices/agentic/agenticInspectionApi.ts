// NOT GENERATED. Safe to edit.

import type { FieldSpec, McpServerRef } from "./agenticOpenApi";
import { agenticApi as api } from "./agenticOpenApi";

export type InspectionExecutionCategory = "graph" | "react" | "proxy";
export type InspectionPreviewKind = "none" | "mermaid" | "dag" | "text";

export type InspectionToolRequirement =
  | {
      kind: "tool_ref";
      required?: boolean;
      description?: string | null;
      tool_ref: string;
    }
  | {
      kind: "capability";
      required?: boolean;
      description?: string | null;
      capability: string;
    };

export type AgentInspection = {
  agent_id: string;
  role: string;
  description: string;
  tags?: string[];
  fields?: FieldSpec[];
  execution_category: InspectionExecutionCategory;
  tool_requirements?: InspectionToolRequirement[];
  default_mcp_servers?: McpServerRef[];
  preview?: {
    kind: InspectionPreviewKind;
    content?: string;
    note?: string | null;
  };
};

export type AgentInspectionApiArg = {
  agentId: string;
};

export const agenticInspectionApi = api.injectEndpoints({
  endpoints: (build) => ({
    getAgentInspection: build.query<AgentInspection, AgentInspectionApiArg>({
      query: ({ agentId }) => ({
        url: `/agentic/v1/agents/${agentId}/inspect`,
      }),
    }),
  }),
  overrideExisting: false,
});

export const { useLazyGetAgentInspectionQuery } = agenticInspectionApi;
