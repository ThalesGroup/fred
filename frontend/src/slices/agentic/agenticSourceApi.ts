// src/slices/agentic/agenticSourceApi.ts
// NOT GENERATED. Safe to edit.

import { agenticApi as api } from "./agenticOpenApi";

// Define the arguments for the query (which is just the 'key')
export type RuntimeSourceApiArg = {
  key: string;
};

export const agenticSourceApi = api.injectEndpoints({
  endpoints: (build) => ({
    // Define a new query that is identical to the generated one,
    // but explicitly forces the response to be read as plain text.
    getRuntimeSourceText: build.query<string, RuntimeSourceApiArg>({
      query: ({ key }) => ({
        url: `/agentic/v1/agents/source/by-object`,
        params: { key: key },

        // 🌟 CRITICAL FIX: Force the response handler to read as text 🌟
        responseHandler: (response) => response.text(),
      }),
    }),
  }),
  overrideExisting: false,
});

// Export the lazy hook for use in AgentHub.tsx
export const { useLazyGetRuntimeSourceTextQuery } = agenticSourceApi;
