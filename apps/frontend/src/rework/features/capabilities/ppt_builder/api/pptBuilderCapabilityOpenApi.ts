import { pptBuilderCapabilityApi as api } from "./pptBuilderCapabilityApi";
const injectedRtkApi = api.injectEndpoints({
  endpoints: (build) => ({
    getPptBuilderPlatform: build.query<GetPptBuilderPlatformApiResponse, GetPptBuilderPlatformApiArg>({
      query: () => ({ url: `/platform` }),
    }),
    getPptBuilderPlatformPatterns: build.query<
      GetPptBuilderPlatformPatternsApiResponse,
      GetPptBuilderPlatformPatternsApiArg
    >({
      query: () => ({ url: `/platform/patterns.pdf` }),
    }),
    putPptBuilderPlatformTemplate: build.mutation<
      PutPptBuilderPlatformTemplateApiResponse,
      PutPptBuilderPlatformTemplateApiArg
    >({
      query: (queryArg) => ({
        url: `/platform/template`,
        method: "PUT",
        body: queryArg.bodyPutPptBuilderPlatformTemplate,
      }),
    }),
    deletePptBuilderPlatformTemplate: build.mutation<
      DeletePptBuilderPlatformTemplateApiResponse,
      DeletePptBuilderPlatformTemplateApiArg
    >({
      query: () => ({ url: `/platform/template`, method: "DELETE" }),
    }),
    rerunPptBuilderPlatformAnalysis: build.mutation<
      RerunPptBuilderPlatformAnalysisApiResponse,
      RerunPptBuilderPlatformAnalysisApiArg
    >({
      query: (queryArg) => ({ url: `/platform/analysis`, method: "POST", body: queryArg.platformAnalysisRequest }),
    }),
    getPptBuilderBuiltin: build.query<GetPptBuilderBuiltinApiResponse, GetPptBuilderBuiltinApiArg>({
      query: () => ({ url: `/builtin` }),
    }),
    getPptBuilderBuiltinPatterns: build.query<
      GetPptBuilderBuiltinPatternsApiResponse,
      GetPptBuilderBuiltinPatternsApiArg
    >({
      query: () => ({ url: `/builtin/patterns.pdf` }),
    }),
    getPptBuilderAnalysis: build.query<GetPptBuilderAnalysisApiResponse, GetPptBuilderAnalysisApiArg>({
      query: (queryArg) => ({ url: `/analysis/${queryArg.instanceId}` }),
    }),
    getPptBuilderAnalysisPatterns: build.query<
      GetPptBuilderAnalysisPatternsApiResponse,
      GetPptBuilderAnalysisPatternsApiArg
    >({
      query: (queryArg) => ({ url: `/analysis/${queryArg.instanceId}/patterns.pdf` }),
    }),
  }),
  overrideExisting: false,
});
export { injectedRtkApi as pptBuilderCapabilityApi };
export type GetPptBuilderPlatformApiResponse = /** status 200 Successful Response */ PlatformTemplateResponse;
export type GetPptBuilderPlatformApiArg = void;
export type GetPptBuilderPlatformPatternsApiResponse = /** status 200 Successful Response */ any;
export type GetPptBuilderPlatformPatternsApiArg = void;
export type PutPptBuilderPlatformTemplateApiResponse = /** status 200 Successful Response */ PlatformTemplateResponse;
export type PutPptBuilderPlatformTemplateApiArg = {
  bodyPutPptBuilderPlatformTemplate: BodyPutPptBuilderPlatformTemplate;
};
export type DeletePptBuilderPlatformTemplateApiResponse =
  /** status 200 Successful Response */ PlatformTemplateResponse;
export type DeletePptBuilderPlatformTemplateApiArg = void;
export type RerunPptBuilderPlatformAnalysisApiResponse = /** status 200 Successful Response */ PlatformTemplateResponse;
export type RerunPptBuilderPlatformAnalysisApiArg = {
  platformAnalysisRequest: PlatformAnalysisRequest;
};
export type GetPptBuilderBuiltinApiResponse = /** status 200 Successful Response */ AnalyzeResult;
export type GetPptBuilderBuiltinApiArg = void;
export type GetPptBuilderBuiltinPatternsApiResponse = /** status 200 Successful Response */ any;
export type GetPptBuilderBuiltinPatternsApiArg = void;
export type GetPptBuilderAnalysisApiResponse = /** status 200 Successful Response */ AnalysisStatusResponse;
export type GetPptBuilderAnalysisApiArg = {
  instanceId: string;
};
export type GetPptBuilderAnalysisPatternsApiResponse = /** status 200 Successful Response */ any;
export type GetPptBuilderAnalysisPatternsApiArg = {
  instanceId: string;
};
export type AnalysisSummary = {
  patterns: number;
  fixed: number;
  excluded: number;
  layouts: number;
  slides: number;
};
export type Box = {
  x: number;
  y: number;
  w: number;
  h: number;
};
export type TableSpec = {
  header: boolean;
  columns: number[];
  widths: number[];
  margin: number;
  line_pt: number;
  pad_pt: number;
  row_pt: number;
  height_pt: number;
};
export type Zone = {
  key: string;
  role:
    | "title"
    | "subtitle"
    | "heading"
    | "body"
    | "caption"
    | "number"
    | "label"
    | "image"
    | "table"
    | "chart"
    | "keep";
  box: Box;
  sample?: string;
  font_pt?: number | null;
  chars_per_line?: number | null;
  max_lines?: number | null;
  grows?: boolean;
  purpose?: string | null;
  table?: TableSpec | null;
  framed?: boolean;
  chart_capable?: boolean;
  chart_type?: string | null;
  takeaway?: boolean;
};
export type RepeatGroup = {
  key: string;
  count: number;
  item_zones: (
    | "title"
    | "subtitle"
    | "heading"
    | "body"
    | "caption"
    | "number"
    | "label"
    | "image"
    | "table"
    | "chart"
    | "keep"
  )[];
  items: Zone[][];
  item_keys: string[];
};
export type Pattern = {
  id: string;
  source: "layout" | "slide";
  source_index: number;
  name: string;
  label: string;
  kind:
    | "cover"
    | "agenda"
    | "section"
    | "bullets"
    | "two_columns"
    | "comparison"
    | "cards"
    | "figures"
    | "process"
    | "timeline"
    | "team"
    | "quote"
    | "image_text"
    | "table"
    | "chart"
    | "closing"
    | "other";
  zones?: Zone[];
  groups?: RepeatGroup[];
  included?: boolean;
  exclusion_reason?:
    | ("chart" | "table" | "library" | "icon_bank" | "no_placeholder" | "unsupported_parts" | "author")
    | null;
  reusable?: boolean;
  labelled_by?: "heuristic" | "vision";
  warnings?: string[];
  design?: string;
};
export type TemplateInventory = {
  slide_width: number;
  slide_height: number;
  analysis_version?: number;
  patterns?: Pattern[];
  shared_texts?: string[];
};
export type AnalysisStatusResponse = {
  status: "pending" | "running" | "succeeded" | "failed" | "interrupted";
  template_sha256: string;
  labelling_key: string;
  analysis_version: number;
  current: boolean;
  refreshing?: boolean;
  error?: string | null;
  updated_at: string;
  has_thumbnails?: boolean;
  summary?: AnalysisSummary | null;
  inventory?: TemplateInventory | null;
};
export type PlatformTemplateResponse = {
  analysis?: AnalysisStatusResponse | null;
  template_filename?: string | null;
  use_vision?: boolean;
  vision_profile_id?: string | null;
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
export type BodyPutPptBuilderPlatformTemplate = {
  file: string;
  use_vision?: boolean;
  vision_profile_id?: string | null;
};
export type PlatformAnalysisRequest = {
  use_vision?: boolean;
  vision_profile_id?: string | null;
};
export type AnalysisError = {
  code: string;
  message: string;
};
export type AnalyzeResult = {
  inventory?: TemplateInventory | null;
  summary?: AnalysisSummary | null;
  errors?: AnalysisError[];
  dropped_overrides?: string[];
};
export const {
  useGetPptBuilderPlatformQuery,
  useLazyGetPptBuilderPlatformQuery,
  useGetPptBuilderPlatformPatternsQuery,
  useLazyGetPptBuilderPlatformPatternsQuery,
  usePutPptBuilderPlatformTemplateMutation,
  useDeletePptBuilderPlatformTemplateMutation,
  useRerunPptBuilderPlatformAnalysisMutation,
  useGetPptBuilderBuiltinQuery,
  useLazyGetPptBuilderBuiltinQuery,
  useGetPptBuilderBuiltinPatternsQuery,
  useLazyGetPptBuilderBuiltinPatternsQuery,
  useGetPptBuilderAnalysisQuery,
  useLazyGetPptBuilderAnalysisQuery,
  useGetPptBuilderAnalysisPatternsQuery,
  useLazyGetPptBuilderAnalysisPatternsQuery,
} = injectedRtkApi;
