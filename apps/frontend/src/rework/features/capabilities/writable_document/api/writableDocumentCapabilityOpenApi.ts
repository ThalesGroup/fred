import { writableDocumentCapabilityApi as api } from "./writableDocumentCapabilityApi";
const injectedRtkApi = api.injectEndpoints({
  endpoints: (build) => ({
    listWritableDocuments: build.query<ListWritableDocumentsApiResponse, ListWritableDocumentsApiArg>({
      query: (queryArg) => ({ url: `/sessions/${queryArg.sessionId}/documents` }),
    }),
    getWritableDocument: build.query<GetWritableDocumentApiResponse, GetWritableDocumentApiArg>({
      query: (queryArg) => ({ url: `/sessions/${queryArg.sessionId}/documents/${queryArg.documentId}` }),
    }),
    updateWritableDocument: build.mutation<UpdateWritableDocumentApiResponse, UpdateWritableDocumentApiArg>({
      query: (queryArg) => ({
        url: `/sessions/${queryArg.sessionId}/documents/${queryArg.documentId}`,
        method: "PUT",
        body: queryArg.writableDocumentUpdate,
      }),
    }),
    exportWritableDocument: build.query<ExportWritableDocumentApiResponse, ExportWritableDocumentApiArg>({
      query: (queryArg) => ({
        url: `/sessions/${queryArg.sessionId}/documents/${queryArg.documentId}/export`,
        params: {
          format: queryArg.format,
        },
      }),
    }),
  }),
  overrideExisting: false,
});
export { injectedRtkApi as writableDocumentCapabilityApi };
export type ListWritableDocumentsApiResponse = /** status 200 Successful Response */ WritableDocumentResponse[];
export type ListWritableDocumentsApiArg = {
  sessionId: string;
};
export type GetWritableDocumentApiResponse = /** status 200 Successful Response */ WritableDocumentResponse;
export type GetWritableDocumentApiArg = {
  sessionId: string;
  documentId: string;
};
export type UpdateWritableDocumentApiResponse = /** status 200 Successful Response */ WritableDocumentResponse;
export type UpdateWritableDocumentApiArg = {
  sessionId: string;
  documentId: string;
  writableDocumentUpdate: WritableDocumentUpdate;
};
export type ExportWritableDocumentApiResponse = /** status 200 Successful Response */ any;
export type ExportWritableDocumentApiArg = {
  sessionId: string;
  documentId: string;
  format?: WritableDocumentExportFormat;
};
export type WritableDocumentResponse = {
  session_id: string;
  document_id: string;
  title: string;
  content_md: string;
  updated_by: "agent" | "user";
  created_at?: string | null;
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
export type WritableDocumentUpdate = {
  content_md: string;
  title?: string | null;
};
export type WritableDocumentExportFormat = "docx" | "md";
export const {
  useListWritableDocumentsQuery,
  useLazyListWritableDocumentsQuery,
  useGetWritableDocumentQuery,
  useLazyGetWritableDocumentQuery,
  useUpdateWritableDocumentMutation,
  useExportWritableDocumentQuery,
  useLazyExportWritableDocumentQuery,
} = injectedRtkApi;
