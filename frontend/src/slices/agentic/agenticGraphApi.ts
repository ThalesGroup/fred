// NOT GENERATED. Safe to edit.

import { agenticApi as api } from "./agenticOpenApi";

export type AgentGraphApiArg = {
  agentId: string;
};

export const agenticGraphApi = api.injectEndpoints({
  endpoints: (build) => ({
    getAgentGraphText: build.query<string, AgentGraphApiArg>({
      query: ({ agentId }) => ({
        url: `/agentic/v1/agents/${agentId}/graph`,
        responseHandler: (response) => response.text(),
      }),
    }),
  }),
  overrideExisting: false,
});

export const { useLazyGetAgentGraphTextQuery } = agenticGraphApi;
