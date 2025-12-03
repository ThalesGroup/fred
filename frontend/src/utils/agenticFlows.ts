import { AnyAgent } from "../common/agent";
import {
  GetAgenticFlowsAgenticV1ChatbotAgenticflowsGetApiResponse,
  McpServerRef,
} from "../slices/agentic/agenticOpenApi";

// Normalize flows returned by the API so the UI always works with McpServerRef (name-based)
export function normalizeAgenticFlows(
  flowsData?: GetAgenticFlowsAgenticV1ChatbotAgenticflowsGetApiResponse,
): AnyAgent[] {
  if (!flowsData) return [];

  const normalizeRefs = (refs?: { id: string; require_tools?: string[] }[]): McpServerRef[] | undefined =>
    refs?.map(({ id, require_tools }) => ({
      // The API returns an id; the UI expects the McpServerRef.name field. We keep the id value here.
      name: id,
      require_tools,
    }));

  return flowsData.map((flow) => {
    const tuning = flow.tuning
      ? {
          ...flow.tuning,
          mcp_servers: normalizeRefs(flow.tuning.mcp_servers),
        }
      : flow.tuning;

    return {
      ...flow,
      tuning,
    } as AnyAgent;
  });
}
