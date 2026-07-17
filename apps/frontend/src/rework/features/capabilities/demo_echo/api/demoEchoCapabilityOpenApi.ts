import { demoEchoCapabilityApi as api } from "./demoEchoCapabilityApi";
const injectedRtkApi = api.injectEndpoints({
  endpoints: (build) => ({
    analyzeAnalyzePost: build.mutation<AnalyzeAnalyzePostApiResponse, AnalyzeAnalyzePostApiArg>({
      query: (queryArg) => ({ url: `/analyze`, method: "POST", body: queryArg.demoAnalyzeRequest }),
    }),
  }),
  overrideExisting: false,
});
export { injectedRtkApi as demoEchoCapabilityApi };
export type AnalyzeAnalyzePostApiResponse = /** status 200 Successful Response */ DemoAnalyzeResponse;
export type AnalyzeAnalyzePostApiArg = {
  demoAnalyzeRequest: DemoAnalyzeRequest;
};
export type DemoAnalyzeResponse = {
  original: string;
  transformed: string;
  length: number;
};
export type ValidationError = {
  loc: (string | number)[];
  msg: string;
  type: string;
  input?: any;
  ctx?: object;
};
export type HttpValidationError = {
  detail?: ValidationError[];
};
export type DemoAnalyzeRequest = {
  text: string;
};
export const { useAnalyzeAnalyzePostMutation } = injectedRtkApi;
