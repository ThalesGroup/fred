import { agenticApi as api } from "./agenticApi";

export type ChatbotRuntimeSummary = {
  sessions_total: number;
  agents_active_total: number;
  attachments_total: number;
  attachments_sessions: number;
  max_attachments_per_session: number;
};

export const runtimeApi = api.injectEndpoints({
  endpoints: (build) => ({
    getRuntimeSummary: build.query<ChatbotRuntimeSummary, void>({
      query: () => ({ url: "/agentic/v1/metrics/chatbot/summary" }),
    }),
  }),
  overrideExisting: false,
});

export const { useGetRuntimeSummaryQuery, useLazyGetRuntimeSummaryQuery } = runtimeApi;

