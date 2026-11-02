import { runtimeApi } from "./runtimeOpenApi";
import { runtimeExecuteStreamPath } from "../../rework/core/utils/runtimeExecutionUrl";

// Route the generated contracts to the prepared pod. Direct overrides remain
// stable across hot reloads; wrapping an already enhanced query would stack.
export const runtimeQueueApi = runtimeApi.enhanceEndpoints({
  endpoints: {
    getPendingMessages(endpoint) {
      endpoint.query = (args) => {
        const { executeStreamUrl } = args as typeof args & { executeStreamUrl: string };
        return {
          url: runtimeExecuteStreamPath(executeStreamUrl).replace(
            /\/execute\/stream$/,
            `/sessions/${encodeURIComponent(args.sessionId)}/pending`,
          ),
          params: { agent_instance_id: args.agentInstanceId, team_id: args.teamId },
        };
      };
    },
    updatePendingMessage(endpoint) {
      endpoint.query = (args) => {
        const { executeStreamUrl } = args as typeof args & { executeStreamUrl: string };
        return {
          url: runtimeExecuteStreamPath(executeStreamUrl).replace(
            /\/execute\/stream$/,
            `/sessions/${encodeURIComponent(args.sessionId)}/pending/${encodeURIComponent(args.messageId)}`,
          ),
          method: "PUT",
          body: args.pendingMessageUpdate,
        };
      };
    },
  },
});

export const { useLazyGetPendingMessagesQuery, useUpdatePendingMessageMutation } = runtimeQueueApi;
