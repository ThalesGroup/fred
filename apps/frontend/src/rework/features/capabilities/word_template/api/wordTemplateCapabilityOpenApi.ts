import { wordTemplateCapabilityApi as api } from "./wordTemplateCapabilityApi";
const injectedRtkApi = api.injectEndpoints({
  endpoints: (build) => ({
    getWordTemplateSession: build.query<GetWordTemplateSessionApiResponse, GetWordTemplateSessionApiArg>({
      query: (queryArg) => ({ url: `/sessions/${queryArg.sessionId}` }),
    }),
    uploadWordTemplateAttachment: build.mutation<
      UploadWordTemplateAttachmentApiResponse,
      UploadWordTemplateAttachmentApiArg
    >({
      query: (queryArg) => ({
        url: `/sessions/${queryArg.sessionId}/attachments`,
        method: "POST",
        body: queryArg.bodyUploadWordTemplateAttachment,
      }),
    }),
    deleteWordTemplateAttachment: build.mutation<
      DeleteWordTemplateAttachmentApiResponse,
      DeleteWordTemplateAttachmentApiArg
    >({
      query: (queryArg) => ({
        url: `/sessions/${queryArg.sessionId}/attachments/${queryArg.attachmentId}`,
        method: "DELETE",
      }),
    }),
    deleteWordTemplateImage: build.mutation<DeleteWordTemplateImageApiResponse, DeleteWordTemplateImageApiArg>({
      query: (queryArg) => ({ url: `/sessions/${queryArg.sessionId}/images/${queryArg.imageId}`, method: "DELETE" }),
    }),
    getWordTemplateImage: build.query<GetWordTemplateImageApiResponse, GetWordTemplateImageApiArg>({
      query: (queryArg) => ({ url: `/sessions/${queryArg.sessionId}/images/${queryArg.imageId}` }),
    }),
    uploadWordTemplateImage: build.mutation<UploadWordTemplateImageApiResponse, UploadWordTemplateImageApiArg>({
      query: (queryArg) => ({
        url: `/sessions/${queryArg.sessionId}/images`,
        method: "POST",
        body: queryArg.bodyUploadWordTemplateImage,
      }),
    }),
    downloadWordTemplateDocument: build.query<
      DownloadWordTemplateDocumentApiResponse,
      DownloadWordTemplateDocumentApiArg
    >({
      query: (queryArg) => ({ url: `/sessions/${queryArg.sessionId}/document.docx` }),
    }),
    previewWordTemplateDocument: build.query<PreviewWordTemplateDocumentApiResponse, PreviewWordTemplateDocumentApiArg>(
      {
        query: (queryArg) => ({ url: `/sessions/${queryArg.sessionId}/preview.pdf` }),
      },
    ),
    getWordTemplateContent: build.query<GetWordTemplateContentApiResponse, GetWordTemplateContentApiArg>({
      query: (queryArg) => ({ url: `/sessions/${queryArg.sessionId}/content` }),
    }),
    editWordTemplateContent: build.mutation<EditWordTemplateContentApiResponse, EditWordTemplateContentApiArg>({
      query: (queryArg) => ({
        url: `/sessions/${queryArg.sessionId}/edits`,
        method: "POST",
        body: queryArg.wordTemplateEditRequest,
      }),
    }),
    undoWordTemplateEdit: build.mutation<UndoWordTemplateEditApiResponse, UndoWordTemplateEditApiArg>({
      query: (queryArg) => ({ url: `/sessions/${queryArg.sessionId}/undo`, method: "POST", body: queryArg.body }),
    }),
  }),
  overrideExisting: false,
});
export { injectedRtkApi as wordTemplateCapabilityApi };
export type GetWordTemplateSessionApiResponse = /** status 200 Successful Response */ WordTemplateSessionResponse;
export type GetWordTemplateSessionApiArg = {
  sessionId: string;
};
export type UploadWordTemplateAttachmentApiResponse =
  /** status 201 Successful Response */ WordTemplateAttachmentResponse;
export type UploadWordTemplateAttachmentApiArg = {
  sessionId: string;
  bodyUploadWordTemplateAttachment: BodyUploadWordTemplateAttachment;
};
export type DeleteWordTemplateAttachmentApiResponse = unknown;
export type DeleteWordTemplateAttachmentApiArg = {
  sessionId: string;
  attachmentId: string;
};
export type DeleteWordTemplateImageApiResponse = unknown;
export type DeleteWordTemplateImageApiArg = {
  sessionId: string;
  imageId: string;
};
export type GetWordTemplateImageApiResponse = /** status 200 Successful Response */ Blob;
export type GetWordTemplateImageApiArg = {
  sessionId: string;
  imageId: string;
};
export type UploadWordTemplateImageApiResponse = /** status 201 Successful Response */ WordTemplateImageResponse;
export type UploadWordTemplateImageApiArg = {
  sessionId: string;
  bodyUploadWordTemplateImage: BodyUploadWordTemplateImage;
};
export type DownloadWordTemplateDocumentApiResponse = /** status 200 Successful Response */ any;
export type DownloadWordTemplateDocumentApiArg = {
  sessionId: string;
};
export type PreviewWordTemplateDocumentApiResponse = /** status 200 Successful Response */ any;
export type PreviewWordTemplateDocumentApiArg = {
  sessionId: string;
};
export type GetWordTemplateContentApiResponse = /** status 200 Successful Response */ WordTemplateContentResponse;
export type GetWordTemplateContentApiArg = {
  sessionId: string;
};
export type EditWordTemplateContentApiResponse = /** status 200 Successful Response */ WordTemplateContentResponse;
export type EditWordTemplateContentApiArg = {
  sessionId: string;
  wordTemplateEditRequest: WordTemplateEditRequest;
};
export type UndoWordTemplateEditApiResponse = /** status 200 Successful Response */ WordTemplateContentResponse;
export type UndoWordTemplateEditApiArg = {
  sessionId: string;
  body: WordTemplateUndoRequest | null;
};
export type WordTemplateSessionResponse = {
  session_id: string;
  template_key?: string | null;
  base_kind?: ("template" | "attachment") | null;
  base_ref?: string | null;
  base_filename?: string | null;
  pinned?: boolean;
  edit_count?: number;
  updated_at?: string | null;
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
export type WordTemplateAttachmentResponse = {
  attachment_id: string;
  filename: string;
};
export type BodyUploadWordTemplateAttachment = {
  file: string;
};
export type WordTemplateImageResponse = {
  image_id: string;
  filename: string;
  content_type: string;
  size: number;
  context_text?: string | null;
};
export type BodyUploadWordTemplateImage = {
  file: string;
};
export type WordTemplateContentBase = {
  kind: "template" | "attachment";
  ref: string;
  filename?: string | null;
};
export type TextPiece = {
  text: string;
  field?: boolean;
};
export type Place = {
  address: string;
  text?: string;
  edit?: ("set_text" | "replace_text" | "write") | null;
  markdown?: string | null;
  pieces?: TextPiece[] | null;
};
export type FieldsBlock = {
  kind?: "fields";
  address: string;
  label: string;
  fields?: Place[];
};
export type ParagraphBlock = {
  address: string;
  text?: string;
  edit?: ("set_text" | "replace_text" | "write") | null;
  markdown?: string | null;
  pieces?: TextPiece[] | null;
  kind?: "paragraph";
  style?: string | null;
};
export type CellView = {
  address: string;
  text?: string;
  edit?: ("set_text" | "replace_text" | "write") | null;
  markdown?: string | null;
  pieces?: TextPiece[] | null;
  /** 1-based first grid column */
  col: number;
  col_span?: number;
  row_span?: number;
};
export type ContentOperation = {
  /** set_text | replace_text | write | insert_after | repeat | remove */
  op: string;
  address?: string | null;
  from?: string | null;
  to?: string | null;
  count?: number | null;
  text?: string | null;
  find?: string | null;
  replace?: string | null;
  markdown?: string | null;
};
export type RowView = {
  address: string;
  cells?: CellView[];
  duplicate?: ContentOperation | null;
  remove?: ContentOperation | null;
};
export type RowGroup = {
  from: string;
  to: string;
  label: string;
  duplicate: ContentOperation;
  remove: ContentOperation;
};
export type TableBlock = {
  kind?: "table";
  address: string;
  n_rows: number;
  n_cols: number;
  style?: string | null;
  /** what one copy stands for, when repeatable */
  repeat_label?: string | null;
  rows?: RowView[];
  row_groups?: RowGroup[];
  duplicable?: boolean;
  duplicate?: ContentOperation | null;
  removable?: boolean;
  remove?: ContentOperation | null;
};
export type BlockGroup = {
  kind?: "block_group";
  from: string;
  to: string;
  label: string;
  blocks?: (
    | ({
        kind: "fields";
      } & FieldsBlock)
    | ({
        kind: "paragraph";
      } & ParagraphBlock)
    | ({
        kind: "table";
      } & TableBlock)
  )[];
  duplicable?: boolean;
  duplicate: ContentOperation;
  removable?: boolean;
  remove: ContentOperation;
};
export type Heading = {
  address: string;
  text?: string;
  edit?: ("set_text" | "replace_text" | "write") | null;
  markdown?: string | null;
  pieces?: TextPiece[] | null;
  level: number;
};
export type TextSegment = {
  kind?: "text";
  from?: string | null;
  to?: string | null;
  markdown?: string;
  edit: ContentOperation;
};
export type ChapterBlock = {
  kind?: "chapter";
  level: number;
  heading: Heading;
  body?: (
    | ({
        kind: "fields";
      } & FieldsBlock)
    | ({
        kind: "paragraph";
      } & ParagraphBlock)
    | ({
        kind: "table";
      } & TableBlock)
    | ({
        kind: "text";
      } & TextSegment)
  )[];
  from: string;
  to: string;
  removable?: boolean;
  remove: ContentOperation;
};
export type ContentPart = {
  id: string;
  title: string;
  blocks?: (
    | ({
        kind: "block_group";
      } & BlockGroup)
    | ({
        kind: "chapter";
      } & ChapterBlock)
    | ({
        kind: "fields";
      } & FieldsBlock)
    | ({
        kind: "paragraph";
      } & ParagraphBlock)
    | ({
        kind: "table";
      } & TableBlock)
  )[];
};
export type WordTemplateContentResponse = {
  session_id: string;
  seq: number;
  base: WordTemplateContentBase;
  parts?: ContentPart[];
};
export type WordTemplateEditRequest = {
  base_seq: number;
  operations: ContentOperation[];
};
export type WordTemplateUndoRequest = {
  base_seq?: number | null;
};
export const {
  useGetWordTemplateSessionQuery,
  useLazyGetWordTemplateSessionQuery,
  useUploadWordTemplateAttachmentMutation,
  useDeleteWordTemplateAttachmentMutation,
  useDeleteWordTemplateImageMutation,
  useGetWordTemplateImageQuery,
  useLazyGetWordTemplateImageQuery,
  useUploadWordTemplateImageMutation,
  useDownloadWordTemplateDocumentQuery,
  useLazyDownloadWordTemplateDocumentQuery,
  usePreviewWordTemplateDocumentQuery,
  useLazyPreviewWordTemplateDocumentQuery,
  useGetWordTemplateContentQuery,
  useLazyGetWordTemplateContentQuery,
  useEditWordTemplateContentMutation,
  useUndoWordTemplateEditMutation,
} = injectedRtkApi;
