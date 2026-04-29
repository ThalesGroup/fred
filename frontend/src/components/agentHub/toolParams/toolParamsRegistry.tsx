import { KfVectorSearchForm } from "@components/pages/TeamAgentsPage/AgentCreateEditModal/KfVectorSearchForm/KfVectorSearchForm";
import React from "react";
import { KfVectorSearchParams } from "src/slices/agentic/agenticOpenApi";

// Generic prop type — used by each individual form component
export interface ToolParamsProps<T> {
  params: T;
  onParamsChange: (params: T) => void;
  teamId?: string;
}

// Type-erased entry stored in the registry
export interface RegistryEntry {
  provider: string;
  render: (params: unknown, onParamsChange: (p: unknown) => void, teamId?: string) => React.ReactNode;
  defaultParams: unknown;
}

// Factory — the single place where the unsafe cast lives
function makeEntry<T>(provider: string, component: React.FC<ToolParamsProps<T>>, defaultParams: T): RegistryEntry {
  const Component = component;
  return {
    provider,
    defaultParams,
    render(params: unknown, onParamsChange: (p: unknown) => void, teamId?: string) {
      return <Component params={params as T} onParamsChange={onParamsChange as (p: T) => void} teamId={teamId} />;
    },
  };
}

// Keyed by inprocess provider string (matches MCPServerConfiguration.provider and KfVectorSearchParams.provider)
export const TOOL_PARAMS_REGISTRY: Record<string, RegistryEntry> = {
  kf_vector_search: makeEntry<KfVectorSearchParams>("kf_vector_search", KfVectorSearchForm, {
    provider: "kf_vector_search",
    libraries_selection: false,
    search_policy_selection: false,
  }),
};
