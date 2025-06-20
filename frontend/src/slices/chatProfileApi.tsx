import { createApi } from "@reduxjs/toolkit/query/react";
import { createDynamicBaseQuery } from "../common/dynamicBaseQuery";
import { ChatProfile } from "../components/profile/ChatProfileEditDialog";

export const chatProfileApiSlice = createApi({
  reducerPath: "chatProfileApi",
  baseQuery: createDynamicBaseQuery({ backend: "knowledge" }),
  endpoints: () => ({}),
});

export const { reducer: chatApiReducer, middleware: chatApiMiddleware } = chatProfileApiSlice;

const chatProfileApiEndpoints = chatProfileApiSlice.injectEndpoints({
  endpoints: (builder) => ({
    getChatProfiles: builder.mutation<ChatProfile[], void>({
      query: () => ({
        url: `/knowledge/v1/chatProfiles`,
        method: "GET",
      }),
    }),

    createChatProfile: builder.mutation<ChatProfile, {
      title: string;
      description: string;
      files: File[];
    }>({
      query: ({ title, description, files }) => {
        const formData = new FormData();
        formData.append("title", title);
        formData.append("description", description);
        files.forEach(file => {
          formData.append("files", file);
        });

        return {
          url: `/knowledge/v1/chatProfiles`,
          method: "POST",
          body: formData,
        };
      },
    }),

    updateChatProfile: builder.mutation<ChatProfile, { chatProfile_id: string; title: string; description: string; files?: File[] }>({
      query: ({ chatProfile_id, title, description, files }) => {
        const formData = new FormData();
        formData.append("title", title);
        formData.append("description", description);

        files?.forEach(file => {
          formData.append("files", file);
        });

        console.log(formData)
        return {
          url: `/knowledge/v1/chatProfiles/${chatProfile_id}`,
          method: "PUT",
          body: formData,
        };
      },
    }),

    deleteChatProfile: builder.mutation<{ success: boolean }, { chatProfile_id: string }>({
      query: ({ chatProfile_id }) => ({
        url: `/knowledge/v1/chatProfiles/${chatProfile_id}`,
        method: "DELETE",
      }),
    }),

    deleteChatProfileDocument: builder.mutation<{ success: boolean }, { chatProfile_id: string; document_id: string }>({
      query: ({ chatProfile_id, document_id }) => ({
        url: `/knowledge/v1/chatProfiles/${chatProfile_id}/documents/${document_id}`,
        method: "DELETE",
      }),
    }),
    getChatProfileMaxTokens: builder.query<{ max_tokens: number }, void>({
      query: () => ({
        url: `/knowledge/v1/chatProfiles/maxTokens`,
        method: "GET",
      }),
    }),
  }),
});

export const {
  useGetChatProfilesMutation,
  useCreateChatProfileMutation,
  useUpdateChatProfileMutation,
  useDeleteChatProfileMutation,
  useDeleteChatProfileDocumentMutation,
  useGetChatProfileMaxTokensQuery
} = chatProfileApiEndpoints;