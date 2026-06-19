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
 */

import { Download as DownloadIcon } from "@mui/icons-material";
import CloseIcon from "@mui/icons-material/Close";
import { Box, IconButton, Tab, Tabs, Typography } from "@mui/material";
import { useTheme } from "@mui/material/styles";
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
import { SimpleTooltip } from "../../shared/ui/tooltips/Tooltips.tsx";
import { useLazyExportWritableDocumentBlobQuery } from "../../slices/agentic/agenticApi.blob.ts";
import { downloadFile } from "../../utils/downloadUtils.tsx";
import { useToast } from "../ToastProvider.tsx";
import type { UseWritableDocuments } from "./useWritableDocuments.ts";

const sanitizeFilename = (name: string) =>
  name
    .replace(/[^\w\-. ]+/g, "")
    .trim()
    .replace(/\s+/g, "_") || "document";

export default function WritableDocumentPane({
  sessionId,
  controller,
}: {
  sessionId: string;
  controller: UseWritableDocuments;
}) {
  const theme = useTheme();
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

  return (
    <Box
      sx={{
        display: "flex",
        flexDirection: "column",
        height: "100%",
        minHeight: 0,
        borderLeft: `1px solid ${theme.palette.divider}`,
        bgcolor: theme.palette.background.default,
      }}
    >
      {/* Header: title + actions */}
      <Box
        sx={{
          display: "flex",
          alignItems: "center",
          gap: 1,
          px: 1.5,
          py: 1,
          borderBottom: `1px solid ${theme.palette.divider}`,
        }}
      >
        <Typography variant="subtitle2" noWrap sx={{ flex: 1, minWidth: 0 }}>
          {selected.title || t("chat.writableDocument.untitled", "Document")}
        </Typography>
        {isSaving && (
          <Typography variant="caption" color="text.secondary">
            {t("chat.writableDocument.saving", "Saving…")}
          </Typography>
        )}
        <SimpleTooltip title={t("chat.writableDocument.downloadWord", "Download as Word")}>
          <span>
            <IconButton
              size="small"
              onClick={handleDownload}
              disabled={isFetching}
              aria-label={t("chat.writableDocument.downloadWord", "Download as Word")}
            >
              <DownloadIcon fontSize="small" />
            </IconButton>
          </span>
        </SimpleTooltip>
        <SimpleTooltip title={t("chat.writableDocument.close", "Close panel")}>
          <IconButton size="small" onClick={closePane} aria-label={t("chat.writableDocument.close", "Close panel")}>
            <CloseIcon fontSize="small" />
          </IconButton>
        </SimpleTooltip>
      </Box>

      {/* Tabs (only when more than one document) */}
      {documents.length > 1 && (
        <Tabs
          value={selected.document_id}
          onChange={(_e, value) => selectDocument(value)}
          variant="scrollable"
          scrollButtons="auto"
          sx={{ borderBottom: `1px solid ${theme.palette.divider}`, minHeight: 40 }}
        >
          {documents.map((doc) => (
            <Tab
              key={doc.document_id}
              value={doc.document_id}
              label={doc.title || t("chat.writableDocument.untitled", "Document")}
              sx={{ minHeight: 40, textTransform: "none" }}
            />
          ))}
        </Tabs>
      )}

      {/* Editor (remounts per document so each tab shows its own content) */}
      <Box sx={{ flex: 1, minHeight: 0, overflowY: "auto" }}>
        <MDXEditor
          key={selected.document_id}
          markdown={selected.content_md ?? ""}
          onChange={(md) => onEditDocument(selected.document_id, md)}
          className={theme.palette.mode === "dark" ? "dark-theme dark-editor" : undefined}
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
      </Box>
    </Box>
  );
}
