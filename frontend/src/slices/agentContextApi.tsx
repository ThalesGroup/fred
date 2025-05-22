// Copyright Thales 2025
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

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


