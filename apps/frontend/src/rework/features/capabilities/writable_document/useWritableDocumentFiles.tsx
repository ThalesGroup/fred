// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { useDispatch, useStore } from "react-redux";
import {
  useLazyGetWritableDocumentQuery,
  useDeleteWritableDocumentMutation,
} from "./api/writableDocumentCapabilityOpenApi";
import { selectDocumentSaves, documentDeleted } from "./writableDocumentSlice";
import { sha256 } from "../../teamWiki/wikiFileShare";
import { writableFilename, writableExportFormat } from "./writableDocumentUtils";
import { useTranslation } from "react-i18next";
import IconButton from "@shared/atoms/IconButton/IconButton";
import type { CapabilityConversationFiles } from "../types";
import { requestSidePanelOpen } from "../sidePanelOpenRequestSlice";
import { selectWritableDocument } from "./writableDocumentSlice";
import { useWritableDocumentList } from "./useWritableDocuments";
import { CAPABILITY_ID } from "./api/writableDocumentCapabilityApi";
import WritableDocumentDownloadButton from "./WritableDocumentDownloadButton";

export function useWritableDocumentFiles(sessionId: string): CapabilityConversationFiles {
  const { t } = useTranslation();
  const dispatch = useDispatch();
  const store = useStore();
  const [read] = useLazyGetWritableDocumentQuery();
  const [deleteDocument] = useDeleteWritableDocumentMutation();
  const { documents, loading, error, unavailable, refetch } = useWritableDocumentList(sessionId);
  return {
    title: t("capability.writable_document.files.title"),
    loading,
    error: unavailable || error,
    errorLabel: t(`capability.writable_document.files.${unavailable ? "unavailable" : "error"}`),
    emptyLabel: t("capability.writable_document.empty"),
    retry: !unavailable && sessionId ? refetch : undefined,
    items: documents.map((doc) => {
      const title = doc.title || t("capability.writable_document.untitled");
      return {
        id: doc.document_id,
        name: writableFilename(title),
        modified: doc.updated_at,
        remove: async () => {
          const save = selectDocumentSaves(store.getState() as Parameters<typeof selectDocumentSaves>[0])?.[
            `${sessionId}/${doc.document_id}`
          ];
          if (save?.status === "saving") throw new Error("Save in progress");
          await deleteDocument({ sessionId, documentId: doc.document_id }).unwrap();
          dispatch(documentDeleted({ sessionId, documentId: doc.document_id }));
        },
        mime:
          writableExportFormat(title) === "docx"
            ? "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            : "text/markdown",
        prepareWikiShare: async () => {
          const checkSaved = () => {
            const save = selectDocumentSaves(store.getState() as Parameters<typeof selectDocumentSaves>[0])?.[
              `${sessionId}/${doc.document_id}`
            ];
            if (save) throw { data: { code: save.status === "failed" ? "save_failed" : "save_pending" } };
          };
          checkSaved();
          const saved = await read({ sessionId, documentId: doc.document_id }, false).unwrap();
          const digest = await sha256(new TextEncoder().encode(saved.content_md));
          checkSaved();
          return {
            title: writableFilename(saved.title),
            writable_document: {
              document_id: doc.document_id,
              sha256: digest,
              format: writableExportFormat(saved.title),
            },
          };
        },
        actions: (
          <>
            <IconButton
              size="small"
              variant="icon"
              color="on-surface-retreat"
              icon={{ category: "outlined", type: "edit_document" }}
              title={t("capability.writable_document.card.open")}
              onClick={() => {
                dispatch(selectWritableDocument(doc.document_id));
                dispatch(requestSidePanelOpen({ capabilityId: CAPABILITY_ID, widget: "writable_document_pane" }));
              }}
            />
            <WritableDocumentDownloadButton sessionId={sessionId} documentId={doc.document_id} title={title} />
          </>
        ),
      };
    }),
  };
}
