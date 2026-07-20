import { pptFillerCapabilityApi as api } from "./pptFillerCapabilityApi";
const injectedRtkApi = api.injectEndpoints({
  endpoints: (build) => ({
    analyzeAnalyzePost: build.mutation<AnalyzeAnalyzePostApiResponse, AnalyzeAnalyzePostApiArg>({
      query: (queryArg) => ({ url: `/analyze`, method: "POST", body: queryArg.bodyAnalyzeAnalyzePost }),
    }),
  }),
  overrideExisting: false,
});
export { injectedRtkApi as pptFillerCapabilityApi };
export type AnalyzeAnalyzePostApiResponse = /** status 200 Successful Response */ ParseResult;
export type AnalyzeAnalyzePostApiArg = {
  bodyAnalyzeAnalyzePost: BodyAnalyzeAnalyzePost;
};
export type KeyField = {
  key: string;
  description?: string;
  type?: "text" | "image";
  folder?: string | null;
  folder_tag_id?: string | null;
};
export type SlideSchema = {
  slide: number;
  keys?: KeyField[];
};
export type TemplateError = {
  slide: number;
  key: string;
  code: string;
  message: string;
};
export type ParseResult = {
  schema?: SlideSchema[];
  errors?: TemplateError[];
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
export type BodyAnalyzeAnalyzePost = {
  file: string;
};
export const { useAnalyzeAnalyzePostMutation } = injectedRtkApi;
