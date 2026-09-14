import { pptBuilderCapabilityApi as api } from "./pptBuilderCapabilityApi";
const injectedRtkApi = api.injectEndpoints({
  endpoints: (build) => ({
    analyzePptBuilderTemplate: build.mutation<AnalyzePptBuilderTemplateApiResponse, AnalyzePptBuilderTemplateApiArg>({
      query: (queryArg) => ({ url: `/analyze`, method: "POST", body: queryArg.bodyAnalyzePptBuilderTemplate }),
    }),
    previewPptBuilderPatterns: build.mutation<PreviewPptBuilderPatternsApiResponse, PreviewPptBuilderPatternsApiArg>({
      query: (queryArg) => ({ url: `/preview`, method: "POST", body: queryArg.bodyPreviewPptBuilderPatterns }),
    }),
    getPptBuilderTheme: build.query<GetPptBuilderThemeApiResponse, GetPptBuilderThemeApiArg>({
      query: () => ({ url: `/theme` }),
    }),
    previewPptBuilderTheme: build.query<PreviewPptBuilderThemeApiResponse, PreviewPptBuilderThemeApiArg>({
      query: () => ({ url: `/theme/preview.pdf` }),
    }),
  }),
  overrideExisting: false,
});
export { injectedRtkApi as pptBuilderCapabilityApi };
export type AnalyzePptBuilderTemplateApiResponse = /** status 200 Successful Response */ AnalyzeResult;
export type AnalyzePptBuilderTemplateApiArg = {
  bodyAnalyzePptBuilderTemplate: BodyAnalyzePptBuilderTemplate;
};
export type PreviewPptBuilderPatternsApiResponse = /** status 200 Successful Response */ any;
export type PreviewPptBuilderPatternsApiArg = {
  bodyPreviewPptBuilderPatterns: BodyPreviewPptBuilderPatterns;
};
export type GetPptBuilderThemeApiResponse = /** status 200 Successful Response */ AnalyzeResult;
export type GetPptBuilderThemeApiArg = void;
export type PreviewPptBuilderThemeApiResponse = /** status 200 Successful Response */ any;
export type PreviewPptBuilderThemeApiArg = void;
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
  intent:
    | "title"
    | "section"
    | "agenda"
    | "content"
    | "two_columns"
    | "comparison"
    | "image_text"
    | "cards"
    | "steps"
    | "statement"
    | "contact"
    | "fixed";
  zones?: Zone[];
  groups?: RepeatGroup[];
  included?: boolean;
  exclusion_reason?: ("chart" | "table" | "icon_bank" | "no_placeholder" | "unsupported_parts" | "author") | null;
  preferred?: boolean;
  warnings?: string[];
};
export type TemplateInventory = {
  slide_width: number;
  slide_height: number;
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
export type BodyAnalyzePptBuilderTemplate = {
  file: string;
};
export type BodyPreviewPptBuilderPatterns = {
  file: string;
};
export const {
  useAnalyzePptBuilderTemplateMutation,
  usePreviewPptBuilderPatternsMutation,
  useGetPptBuilderThemeQuery,
  useLazyGetPptBuilderThemeQuery,
  usePreviewPptBuilderThemeQuery,
  useLazyPreviewPptBuilderThemeQuery,
} = injectedRtkApi;
