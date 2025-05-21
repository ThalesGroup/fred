import { createApi } from '@reduxjs/toolkit/query/react';
import { createDynamicBaseQuery } from '../common/dynamicBaseQuery.tsx';

/**
 * 1. API Slice pour le Chat/LLM
 */
export const agentContextApiSlice = createApi({
  reducerPath: 'agentContextApi',
  baseQuery: createDynamicBaseQuery({ backend: "api" }),
  endpoints: () => ({}),
});

export const { reducer: chatApiReducer, middleware: chatApiMiddleware } = agentContextApiSlice;

const extendedAgentContextApi = agentContextApiSlice.injectEndpoints({
  endpoints: (builder) => ({
    getAgentContexts: builder.mutation({
      query: (agentName) => ({
        url: `/fred/context/${agentName}`,
        method: 'GET',
      }),
    }),

    saveAgentContext: builder.mutation({
      query: ({ agentName, context }) => ({
        url: `/fred/context/${agentName}`,
        method: 'POST',
        body: context,
      }),
    }),

    deleteAgentContext: builder.mutation({
      query: ({ agentName, contextId }) => ({
        url: `/fred/context/${agentName}/${contextId}`,
        method: 'DELETE',
      }),
    }),
  }),
});

export const {
  useGetAgentContextsMutation,
  useSaveAgentContextMutation,
  useDeleteAgentContextMutation,
} = extendedAgentContextApi


