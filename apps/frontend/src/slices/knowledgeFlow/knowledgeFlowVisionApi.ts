import { knowledgeFlowApi } from "./knowledgeFlowApi";

export const knowledgeFlowVisionApi = knowledgeFlowApi.injectEndpoints({
  endpoints: (build) => ({
    getVisionAvailability: build.query<{ available: boolean }, void>({
      query: () => ({ url: "/knowledge-flow/v1/vision/availability" }),
    }),
  }),
});

export const { useGetVisionAvailabilityQuery } = knowledgeFlowVisionApi;
