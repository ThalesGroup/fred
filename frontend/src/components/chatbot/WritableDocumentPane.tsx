// Copyright Thales 2025
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

/**
 * WritableDocumentPane
 * --------------------
 * The single right-hand editor pane for collaborative documents. One MDXEditor
 * instance edits the selected document (markdown in/out, always editable). Multiple
 * documents are presented as tabs. Edits autosave (debounced) via the parent hook.
 *
 * Built with the rework design system (CSS modules + shared atoms), not MUI.
 */

import {
  BlockTypeSelect,
  BoldItalicUnderlineToggles,
  CreateLink,
  headingsPlugin,
  linkDialogPlugin,
  linkPlugin,
  listsPlugin,
  ListsToggle,
  markdownShortcutPlugin,
  MDXEditor,
  quotePlugin,
  Separator,
  thematicBreakPlugin,
  toolbarPlugin,
  UndoRedo,
} from "@mdxeditor/editor";
import "@mdxeditor/editor/style.css";
import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import Icon from "@shared/atoms/Icon/Icon.tsx";
import IconButton from "@shared/atoms/IconButton/IconButton.tsx";
import { Tooltip } from "@shared/atoms/Tooltip/Tooltip.tsx";
import { useLazyExportWritableDocumentBlobQuery } from "../../slices/agentic/agenticApi.blob.ts";
import { downloadFile } from "../../utils/downloadUtils.tsx";
import { useToast } from "../ToastProvider.tsx";
import type { UseWritableDocuments } from "./useWritableDocuments.ts";
import styles from "./WritableDocumentPane.module.css";

const sanitizeFilename = (name: string) =>
  name
    .replace(/[^\w\-. ]+/g, "")
    .trim()
    .replace(/\s+/g, "_") || "document";

const isDarkTheme = () =>
  typeof document !== "undefined" && document.documentElement.getAttribute("data-theme") === "dark";

export default function WritableDocumentPane({
  sessionId,
  controller,
}: {
  sessionId: string;
  controller: UseWritableDocuments;
}) {
  const { t } = useTranslation();
  const { showError } = useToast();
  const { documents, selectedId, selectDocument, closePane, onEditDocument, isSaving } = controller;
  const [exportDoc, { isFetching }] = useLazyExportWritableDocumentBlobQuery();

  const selected = useMemo(
    () => documents.find((d) => d.document_id === selectedId) ?? documents[0],
    [documents, selectedId],
  );

  const handleDownload = async () => {
    if (!selected) return;
    try {
      const blob = await exportDoc({ sessionId, documentId: selected.document_id, format: "docx" }).unwrap();
      downloadFile(blob, `${sanitizeFilename(selected.title)}.docx`);
    } catch (err: any) {
      showError({
        summary: t("chat.writableDocument.downloadError", "Download failed"),
        detail: err?.message || String(err),
      });
    }
  };

  if (!selected) return null;

  const untitled = t("chat.writableDocument.untitled", "Document");
  const downloadLabel = t("chat.writableDocument.downloadWord", "Download as Word");
  const closeLabel = t("chat.writableDocument.close", "Close panel");

  return (
    <div className={styles.pane}>
      {/* Header: title + actions */}
      <div className={styles.header}>
        <div className={styles.titleGroup}>
          <Icon category="outlined" type="description" />
          <span className={styles.title}>{selected.title || untitled}</span>
        </div>
        {isSaving && <span className={styles.saving}>{t("chat.writableDocument.saving", "Saving…")}</span>}
        <Tooltip text={downloadLabel}>
          <IconButton
            color="on-surface"
            variant="icon"
            size="small"
            icon={{ category: "outlined", type: "download" }}
            onClick={handleDownload}
            disabled={isFetching}
            aria-label={downloadLabel}
          />
        </Tooltip>
        <Tooltip text={closeLabel}>
          <IconButton
            color="on-surface"
            variant="icon"
            size="small"
            icon={{ category: "outlined", type: "close" }}
            onClick={closePane}
            aria-label={closeLabel}
          />
        </Tooltip>
      </div>

      {/* Tabs (only when more than one document) */}
      {documents.length > 1 && (
        <div className={styles.tabs} role="tablist">
          {documents.map((doc) => (
            <button
              key={doc.document_id}
              role="tab"
              aria-selected={doc.document_id === selected.document_id}
              className={`${styles.tab} ${doc.document_id === selected.document_id ? styles.tabActive : ""}`}
              onClick={() => selectDocument(doc.document_id)}
            >
              {doc.title || untitled}
            </button>
          ))}
        </div>
      )}

      {/* Editor (remounts per document so each tab shows its own content) */}
      <div className={styles.editorArea}>
        <MDXEditor
          key={selected.document_id}
          markdown={selected.content_md ?? ""}
          onChange={(md) => onEditDocument(selected.document_id, md)}
          className={isDarkTheme() ? "dark-theme dark-editor" : undefined}
          contentEditableClassName="fred-writable-document"
          plugins={[
            headingsPlugin(),
            listsPlugin(),
            quotePlugin(),
            linkPlugin(),
            linkDialogPlugin(),
            thematicBreakPlugin(),
            markdownShortcutPlugin(),
            toolbarPlugin({
              toolbarContents: () => (
                <>
                  <UndoRedo />
                  <Separator />
                  <BoldItalicUnderlineToggles />
                  <Separator />
                  <BlockTypeSelect />
                  <Separator />
                  <ListsToggle />
                  <Separator />
                  <CreateLink />
                </>
              ),
            }),
          ]}
        />
      </div>
    </div>
  );
}
