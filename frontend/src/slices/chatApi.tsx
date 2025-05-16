import { createApi } from '@reduxjs/toolkit/query/react';
import { AgenticFlow } from "../pages/Chat";
import { createDynamicBaseQuery } from '../common/dynamicBaseQuery.tsx';
import { ChatMessagePayload, SessionSchema } from './chatApiStructures.ts';

/**
 * 1. API Slice pour le Chat/LLM
 */
export const chatApiSlice = createApi({
  reducerPath: 'chatApi',
  baseQuery: createDynamicBaseQuery({ backend: "api" }),
  endpoints: () => ({}),
});

export const { reducer: chatApiReducer, middleware: chatApiMiddleware } = chatApiSlice;

const extendedChatApi = chatApiSlice.injectEndpoints({
  endpoints: (builder) => ({
    getChatBotMessages: builder.mutation<ChatMessagePayload[], { session_id: string }>({
      query: ({ session_id }) => ({
        url: `/fred/chatbot/session/${session_id}/history`,
        method: 'GET',
      }),
    }),
    getChatBotAgenticFlows: builder.mutation<AgenticFlow[], void>({
      query: () => ({
        url: `/fred/chatbot/agenticflows`,
        method: 'GET',
      }),
    }),
    getChatbotSessions: builder.mutation<SessionSchema[], void>({
      query: () => ({
        url: `/fred/chatbot/sessions`,
        method: 'GET',
      }),
    }),
    deleteChatbotSession: builder.mutation<{ success: boolean }, { session_id: string }>({
      query: ({ session_id }) => ({
        url: `/fred/chatbot/session/${session_id}`,
        method: 'DELETE',
      }),
    }),
    getAgentContexts: builder.mutation({
      query: (agentName) => ({
          url: `/fred/contexts/${agentName}`,
          method: 'GET',
      }),
  }),

  // Créer ou mettre à jour un contexte
  saveAgentContext: builder.mutation({
      query: ({ agentName, context }) => ({
          url: `/fred/contexts/${agentName}`,
          method: 'POST',
          body: context,
      }),
  }),

  // Supprimer un contexte
  deleteAgentContext: builder.mutation({
      query: ({ agentName, contextId }) => ({
          url: `/fred/contexts/${agentName}/${contextId}`,
          method: 'DELETE',
      }),
  }),
    postFeedback: builder.mutation<{ success: boolean }, {
      rating: number,
      reason: string,
      feedbackType: 'up' | 'down',
      messageId?: string // Optional: you can pass an identifier for the message
    }>({
      query: ({ rating, reason, feedbackType, messageId }) => ({
        url: `/fred/chatbot/feedback`,
        method: 'POST',
        body: { rating, reason, feedbackType, messageId },
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
} = extendedChatApi;

