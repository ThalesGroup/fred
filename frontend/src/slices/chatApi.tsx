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

import { createApi } from "@reduxjs/toolkit/query/react";
import { AgenticFlow } from "../pages/Chat";
import { createDynamicBaseQuery } from "../common/dynamicBaseQuery.tsx";
import { ChatMessagePayload, CreateAgentRequest, CreateAgentResponse, SessionSchema } from "./chatApiStructures.ts";


export const chatApiSlice = createApi({
  reducerPath: "chatApi",
  baseQuery: createDynamicBaseQuery({ backend: "api" }),
  endpoints: () => ({}),
});

export const { reducer: chatApiReducer, middleware: chatApiMiddleware } = chatApiSlice;

const extendedChatApi = chatApiSlice.injectEndpoints({
  endpoints: (builder) => ({
    getChatBotMessages: builder.mutation<ChatMessagePayload[], { session_id: string }>({
      query: ({ session_id }) => ({
        url: `/agentic/v1/chatbot/session/${session_id}/history`,
        method: "GET",
      }),
    }),
    createAgent: builder.mutation<CreateAgentResponse, CreateAgentRequest>({
      query: (body) => ({
        url: `/agentic/v1/agents/create`,
        method: "POST",
        body,
      }),
    }),

    getChatBotAgenticFlows: builder.mutation<AgenticFlow[], void>({
      query: () => ({
        url: `/agentic/v1/chatbot/agenticflows`,
        method: "GET",
      }),
    }),
    getChatbotSessions: builder.mutation<SessionSchema[], void>({
      query: () => ({
        url: `/agentic/v1/chatbot/sessions`,
        method: "GET",
      }),
    }),
    deleteChatbotSession: builder.mutation<{ success: boolean }, { session_id: string }>({
      query: ({ session_id }) => ({
        url: `/agentic/v1/chatbot/session/${session_id}`,
        method: "DELETE",
      }),
    }),
    getAgentContexts: builder.mutation({
      query: (agentName) => ({
        url: `/agentic/v1/contexts/${agentName}`,
        method: "GET",
      }),
    }),
    // Créer ou mettre à jour un contexte
    saveAgentContext: builder.mutation({
      query: ({ agentName, context }) => ({
        url: `/agentic/v1/contexts/${agentName}`,
        method: "POST",
        body: context,
      }),
    }),

    // Supprimer un contexte
    deleteAgentContext: builder.mutation({
      query: ({ agentName, contextId }) => ({
        url: `/agentic/v1/contexts/${agentName}/${contextId}`,
        method: "DELETE",
      }),
    }),
    postFeedback: builder.mutation<
      { success: boolean },
      {
        rating: number;
        comment?: string;
        messageId: string;
        sessionId: string;
        agentName: string;
      }
    >({
      query: ({ rating, comment, messageId, sessionId, agentName }) => ({
        url: `/agentic/v1/chatbot/feedback`,
        method: "POST",
        body: { rating, comment, messageId, sessionId, agentName },
      }),
    }),
  }),
});

export const {
  useGetChatBotMessagesMutation,
  useGetChatBotAgenticFlowsMutation,
  useGetChatbotSessionsMutation,
  useDeleteChatbotSessionMutation,
  usePostFeedbackMutation,
  useGetAgentContextsMutation,
  useSaveAgentContextMutation,
  useDeleteAgentContextMutation,
  useCreateAgentMutation,
} = extendedChatApi;
