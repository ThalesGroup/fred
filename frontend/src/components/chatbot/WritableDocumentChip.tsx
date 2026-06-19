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
 * WritableDocumentChip
 * --------------------
 * Compact, clickable reference to a collaborative document shown inside an assistant
 * message. Clicking the chip opens/focuses the document in the editor pane; the Word
 * button exports it as .docx. The full document content lives in the pane, not here.
 */

import ArticleOutlinedIcon from "@mui/icons-material/ArticleOutlined";
import { Download as DownloadIcon } from "@mui/icons-material";
import { Box, Card, CardActionArea, IconButton, Typography } from "@mui/material";
import { useTheme } from "@mui/material/styles";
import { useTranslation } from "react-i18next";
import { SimpleTooltip } from "../../shared/ui/tooltips/Tooltips.tsx";
import type { WritableDocumentPart } from "../../slices/agentic/agenticOpenApi.ts";
import { useLazyExportWritableDocumentBlobQuery } from "../../slices/agentic/agenticApi.blob.ts";
import { downloadFile } from "../../utils/downloadUtils.tsx";
import { useToast } from "../ToastProvider.tsx";

const sanitizeFilename = (name: string) =>
  name
    .replace(/[^\w\-. ]+/g, "")
    .trim()
    .replace(/\s+/g, "_") || "document";

export default function WritableDocumentChip({
  part,
  sessionId,
  onOpen,
}: {
  part: WritableDocumentPart;
  sessionId: string;
  onOpen?: (documentId: string) => void;
}) {
  const theme = useTheme();
  const { t } = useTranslation();
  const { showError } = useToast();
  const [exportDoc, { isFetching }] = useLazyExportWritableDocumentBlobQuery();

  const handleDownload = async () => {
    try {
      const blob = await exportDoc({
        sessionId,
        documentId: part.document_id,
        format: "docx",
      }).unwrap();
      downloadFile(blob, `${sanitizeFilename(part.title)}.docx`);
    } catch (err: any) {
      showError({
        summary: t("chat.writableDocument.downloadError", "Download failed"),
        detail: err?.message || String(err),
      });
    }
  };

  return (
    <Box px={0} pt={0.5} pb={1}>
      <Card
        variant="outlined"
        sx={{
          display: "flex",
          alignItems: "center",
          maxWidth: 360,
          borderRadius: 2,
          borderColor: theme.palette.divider,
        }}
      >
        <CardActionArea
          onClick={() => onOpen?.(part.document_id)}
          sx={{ display: "flex", alignItems: "center", justifyContent: "flex-start", px: 1.25, py: 1, gap: 1 }}
        >
          <ArticleOutlinedIcon fontSize="small" color="primary" />
          <Box sx={{ minWidth: 0, flex: 1 }}>
            <Typography variant="body2" fontWeight={600} noWrap>
              {part.title || t("chat.writableDocument.untitled", "Document")}
            </Typography>
            <Typography variant="caption" color="text.secondary">
              {t("chat.writableDocument.openHint", "Open in editor")}
            </Typography>
          </Box>
        </CardActionArea>
        <SimpleTooltip title={t("chat.writableDocument.downloadWord", "Download as Word")}>
          <span>
            <IconButton
              size="small"
              onClick={handleDownload}
              disabled={isFetching}
              aria-label={t("chat.writableDocument.downloadWord", "Download as Word")}
              sx={{ mr: 0.5 }}
            >
              <DownloadIcon fontSize="small" />
            </IconButton>
          </span>
        </SimpleTooltip>
      </Card>
    </Box>
  );
}
