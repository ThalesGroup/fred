import { DocumentCapacityForm } from "@components/pages/TeamAgentsPage/AgentCreateEditModal/DocumentCapacityForm/DocumentCapacityForm";
import React from "react";

export interface ToolParamsProps {
  params: Record<string, unknown>;
  onParamsChange: (params: Record<string, unknown>) => void;
}

export const TOOL_PARAMS_REGISTRY: Record<string, React.FC<ToolParamsProps>> = {
  "mcp-knowledge-flow-mcp-text": DocumentCapacityForm,
};
