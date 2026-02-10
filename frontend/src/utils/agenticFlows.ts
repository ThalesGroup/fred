import { AnyAgent } from "../common/agent";
import { ListAgentsAgenticV1AgentsGetApiResponse } from "../slices/agentic/agenticOpenApi";

// Cast API response items to AnyAgent union type
export function normalizeAgenticFlows(flowsData?: ListAgentsAgenticV1AgentsGetApiResponse): AnyAgent[] {
  if (!flowsData) return [];
  return flowsData;
}
