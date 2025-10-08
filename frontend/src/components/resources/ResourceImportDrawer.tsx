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

import SaveIcon from "@mui/icons-material/Save";
import UploadIcon from "@mui/icons-material/Upload";
import { Box, Button, Drawer, Paper, Stack, Typography, useTheme } from "@mui/material";
import React, { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { ResourceKind } from "../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { useToast } from "../ToastProvider";
import { useResourceCommands } from "./useResourceCommands";

type Props = {
  isOpen: boolean;
  onClose: () => void;
  onImportComplete?: () => void;
  libraryTagId: string | null;
  kind: ResourceKind; // "prompt" | "template" — trusted
};

const regexName = /^\s*name\s*:\s*(.+)\s*$/im;
const deriveName = (text: string, filename: string) => {
  const m = text.match(regexName);
  if (m) return m[1].replace(/^['"]|['"]$/g, "");
  return filename.replace(/\.(yaml|yml|md|txt)$/i, "");
};

export const ResourceImportDrawer: React.FC<Props> = ({ isOpen, onClose, onImportComplete, libraryTagId, kind }) => {
  const { t } = useTranslation();
  const theme = useTheme();
  const { showSuccess, showError, showInfo } = useToast();

  const inputRef = useRef<HTMLInputElement | null>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [isImporting, setIsImporting] = useState(false);
  const [isHighlighted, setIsHighlighted] = useState(false);

  const { createResource } = useResourceCommands(kind);

  const reset = () => {
    setFiles([]);
    setIsImporting(false);
    setIsHighlighted(false);
    if (inputRef.current) inputRef.current.value = "";
  };

  const handleClose = () => {
    reset();
    onClose();
  };

  const handleChooseFiles = () => inputRef.current?.click();

  const handleFileChange: React.ChangeEventHandler<HTMLInputElement> = (e) => {
    const list = e.target.files ? Array.from(e.target.files) : [];
    setFiles(list);
  };

  const handleDrop: React.DragEventHandler<HTMLDivElement> = (e) => {
    e.preventDefault();
    setIsHighlighted(false);
    const dropped = e.dataTransfer.files ? Array.from(e.dataTransfer.files) : [];
    if (dropped.length) setFiles((prev) => [...prev, ...dropped]);
  };

  const handleImport = async () => {
    if (!libraryTagId) {
      showInfo?.({ summary: t("validation.info") || "Info", detail: "Select a target library first." });
      return;
    }
    if (!files.length) return;

    setIsImporting(true);
    let ok = 0;
    let fail = 0;

    for (const file of files) {
      try {
        const text = await file.text();

        // Trust the tab's kind; do NOT parse/validate kind from YAML.
        await createResource(
          {
            name: deriveName(text, file.name),
            content: text,
          } as any,
          libraryTagId,
        );
        ok++;
      } catch (e: any) {
        fail++;
        showError?.({
          summary: t("resourceLibrary.importFailed") || "Import failed",
          detail: e?.data?.detail || e?.message || String(e),
        });
      }
    }

    setIsImporting(false);
    if (ok) {
      showSuccess?.({
        summary: t("resourceLibrary.importSuccess") || "Imported",
        detail: t("resourceLibrary.importSummary", { ok, fail }) || `Imported ${ok}, failed ${fail}`,
      });
    } else {
      showError?.({
        summary: t("resourceLibrary.importFailed") || "Import failed",
        detail: t("resourceLibrary.importSummary", { ok, fail }) || `Imported ${ok}, failed ${fail}`,
      });
    }

    onImportComplete?.();
    handleClose();
  };

  return (
    <Drawer
      anchor="right"
      open={isOpen}
      onClose={handleClose}
      PaperProps={{
        sx: {
          width: { xs: "100%", sm: 450 },
          p: 3,
        },
      }}
    >
      <Typography variant="h5" fontWeight="bold" gutterBottom>
        {t("resourceLibrary.importDrawerTitle", { typeOne: kind }) || `Import ${kind}`}
      </Typography>

      {/* Hidden file input */}
      <input
        ref={inputRef}
        type="file"
        accept=".yaml,.yml,.md,.txt"
        multiple
        style={{ display: "none" }}
        onChange={handleFileChange}
      />

      {/* Drop zone / picker */}
      <Paper
        sx={{
          mt: 2,
          p: 3,
          border: "1px dashed",
          borderColor: "divider",
          borderRadius: "12px",
          cursor: "pointer",
          minHeight: 160,
          backgroundColor: isHighlighted ? theme.palette.action.hover : theme.palette.background.paper,
          transition: "background-color 0.2s",
        }}
        onClick={handleChooseFiles}
        onDragOver={(e) => {
          e.preventDefault();
          setIsHighlighted(true);
        }}
        onDragLeave={() => setIsHighlighted(false)}
        onDrop={handleDrop}
      >
        <Box display="flex" flexDirection="column" alignItems="center" justifyContent="center" height="100%" gap={1}>
          <UploadIcon sx={{ fontSize: 40, color: "text.secondary" }} />
          <Typography variant="body1" color="text.secondary">
            {t("resourceLibrary.dropFiles", { typePlural: kind }) || "Drop files here or click to choose"}
          </Typography>
          <Typography variant="caption" color="text.secondary">
            .yaml, .yml, .md, .txt
          </Typography>
        </Box>
      </Paper>

      {/* Selected files */}
      <Stack spacing={0.5} sx={{ mt: 2, maxHeight: 220, overflowY: "auto" }}>
        {files.length ? (
          files.map((f, i) => (
            <Typography key={i} variant="body2" noWrap title={f.name}>
              • {f.name}
            </Typography>
          ))
        ) : (
          <Typography variant="body2" color="text.secondary">
            {t("resourceLibrary.noFiles", { typeOne: kind }) || "No files selected"}
          </Typography>
        )}
      </Stack>

      {/* Actions */}
      <Box sx={{ mt: 3, display: "flex", justifyContent: "space-between" }}>
        <Button variant="outlined" onClick={handleClose} sx={{ borderRadius: "8px" }}>
          {t("dialogs.cancel") || "Cancel"}
        </Button>
        <Button
          variant="contained"
          color="success"
          startIcon={<SaveIcon />}
          onClick={handleImport}
          disabled={!files.length || !libraryTagId || isImporting}
          sx={{ borderRadius: "8px" }}
        >
          {isImporting ? t("resourceLibrary.importing") || "Importing…" : t("resourceLibrary.import") || "Import"}
        </Button>
      </Box>
    </Drawer>
  );
};
