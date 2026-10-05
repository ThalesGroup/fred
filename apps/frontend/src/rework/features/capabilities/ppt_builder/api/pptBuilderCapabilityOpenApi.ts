import { pptBuilderCapabilityApi as api } from "./pptBuilderCapabilityApi";
const injectedRtkApi = api.injectEndpoints({
  endpoints: (build) => ({
    getPptBuilderTheme: build.query<GetPptBuilderThemeApiResponse, GetPptBuilderThemeApiArg>({
      query: () => ({ url: `/theme` }),
    }),
    previewPptBuilderTheme: build.query<PreviewPptBuilderThemeApiResponse, PreviewPptBuilderThemeApiArg>({
      query: () => ({ url: `/theme/preview.pdf` }),
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
    rerunPptBuilderAnalysis: build.mutation<RerunPptBuilderAnalysisApiResponse, RerunPptBuilderAnalysisApiArg>({
      query: (queryArg) => ({ url: `/analysis/${queryArg.instanceId}/rerun`, method: "POST" }),
    }),
  }),
  overrideExisting: false,
});
export { injectedRtkApi as pptBuilderCapabilityApi };
export type GetPptBuilderThemeApiResponse = /** status 200 Successful Response */ AnalyzeResult;
export type GetPptBuilderThemeApiArg = void;
export type PreviewPptBuilderThemeApiResponse = /** status 200 Successful Response */ any;
export type PreviewPptBuilderThemeApiArg = void;
export type GetPptBuilderAnalysisApiResponse = /** status 200 Successful Response */ AnalysisStatusResponse;
export type GetPptBuilderAnalysisApiArg = {
  instanceId: string;
};
export type GetPptBuilderAnalysisPatternsApiResponse = /** status 200 Successful Response */ any;
export type GetPptBuilderAnalysisPatternsApiArg = {
  instanceId: string;
};
export type RerunPptBuilderAnalysisApiResponse = /** status 200 Successful Response */ AnalysisStatusResponse;
export type RerunPptBuilderAnalysisApiArg = {
  instanceId: string;
};
export type Box = {
  x: number;
  y: number;
  w: number;
  h: number;
};
export type Zone = {
  key: string;
  role: "title" | "subtitle" | "heading" | "body" | "caption" | "number" | "label" | "image" | "keep";
  box: Box;
  sample?: string;
  font_pt?: number | null;
  max_chars?: number | null;
  max_lines?: number | null;
  grows?: boolean;
  purpose?: string | null;
};
export type RepeatGroup = {
  key: string;
  count: number;
  item_zones: ("title" | "subtitle" | "heading" | "body" | "caption" | "number" | "label" | "image" | "keep")[];
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
    | "closing"
    | "other";
  zones?: Zone[];
  groups?: RepeatGroup[];
  included?: boolean;
  exclusion_reason?: ("chart" | "table" | "icon_bank" | "no_placeholder" | "unsupported_parts" | "author") | null;
  preferred?: boolean;
  reusable?: boolean;
  labelled_by?: "heuristic" | "vision";
  warnings?: string[];
};
export type TemplateInventory = {
  slide_width: number;
  slide_height: number;
  analysis_version?: number;
  patterns?: Pattern[];
  shared_texts?: string[];
};
export type AnalysisSummary = {
  patterns: number;
  fixed: number;
  excluded: number;
  layouts: number;
  slides: number;
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
export type AnalysisStatusResponse = {
  status: "pending" | "running" | "succeeded" | "failed" | "interrupted";
  template_sha256: string;
  labelling_key: string;
  analysis_version: number;
  current: boolean;
  error?: string | null;
  updated_at: string;
  has_thumbnails?: boolean;
  summary?: AnalysisSummary | null;
  inventory?: TemplateInventory | null;
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
export const {
  useGetPptBuilderThemeQuery,
  useLazyGetPptBuilderThemeQuery,
  usePreviewPptBuilderThemeQuery,
  useLazyPreviewPptBuilderThemeQuery,
  useGetPptBuilderAnalysisQuery,
  useLazyGetPptBuilderAnalysisQuery,
  useGetPptBuilderAnalysisPatternsQuery,
  useLazyGetPptBuilderAnalysisPatternsQuery,
  useRerunPptBuilderAnalysisMutation,
} = injectedRtkApi;
