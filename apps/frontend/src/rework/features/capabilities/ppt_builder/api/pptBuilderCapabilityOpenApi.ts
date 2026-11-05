import { pptBuilderCapabilityApi as api } from "./pptBuilderCapabilityApi";
const injectedRtkApi = api.injectEndpoints({
  endpoints: (build) => ({
    getPptBuilderBuiltin: build.query<GetPptBuilderBuiltinApiResponse, GetPptBuilderBuiltinApiArg>({
      query: (queryArg) => ({
        url: `/builtin`,
        params: {
          space_id: queryArg.spaceId,
          runtime_id: queryArg.runtimeId,
        },
      }),
    }),
    getPptBuilderBuiltinPatterns: build.query<
      GetPptBuilderBuiltinPatternsApiResponse,
      GetPptBuilderBuiltinPatternsApiArg
    >({
      query: () => ({ url: `/builtin/patterns.pdf` }),
    }),
    getPptBuilderAnalysis: build.query<GetPptBuilderAnalysisApiResponse, GetPptBuilderAnalysisApiArg>({
      query: (queryArg) => ({
        url: `/analysis/${queryArg.instanceId}`,
        params: {
          space_id: queryArg.spaceId,
          agent_instance_id: queryArg.agentInstanceId,
          runtime_id: queryArg.runtimeId,
        },
      }),
    }),
    getPptBuilderAnalysisPatterns: build.query<
      GetPptBuilderAnalysisPatternsApiResponse,
      GetPptBuilderAnalysisPatternsApiArg
    >({
      query: (queryArg) => ({
        url: `/analysis/${queryArg.instanceId}/patterns.pdf`,
        params: {
          space_id: queryArg.spaceId,
          agent_instance_id: queryArg.agentInstanceId,
          runtime_id: queryArg.runtimeId,
        },
      }),
    }),
  }),
  overrideExisting: false,
});
export { injectedRtkApi as pptBuilderCapabilityApi };
export type GetPptBuilderBuiltinApiResponse = /** status 200 Successful Response */ AnalyzeResult;
export type GetPptBuilderBuiltinApiArg = {
  spaceId?: string | null;
  runtimeId?: string | null;
};
export type GetPptBuilderBuiltinPatternsApiResponse = /** status 200 Successful Response */ any;
export type GetPptBuilderBuiltinPatternsApiArg = void;
export type GetPptBuilderAnalysisApiResponse = /** status 200 Successful Response */ AnalysisStatusResponse;
export type GetPptBuilderAnalysisApiArg = {
  instanceId: string;
  spaceId?: string | null;
  agentInstanceId?: string | null;
  runtimeId?: string | null;
};
export type GetPptBuilderAnalysisPatternsApiResponse = /** status 200 Successful Response */ any;
export type GetPptBuilderAnalysisPatternsApiArg = {
  instanceId: string;
  spaceId?: string | null;
  agentInstanceId?: string | null;
  runtimeId?: string | null;
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
    | "keep"
    | "contact_email"
    | "contact_phone";
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
    | "contact_email"
    | "contact_phone"
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
export const {
  useGetPptBuilderBuiltinQuery,
  useLazyGetPptBuilderBuiltinQuery,
  useGetPptBuilderBuiltinPatternsQuery,
  useLazyGetPptBuilderBuiltinPatternsQuery,
  useGetPptBuilderAnalysisQuery,
  useLazyGetPptBuilderAnalysisQuery,
  useGetPptBuilderAnalysisPatternsQuery,
  useLazyGetPptBuilderAnalysisPatternsQuery,
} = injectedRtkApi;
