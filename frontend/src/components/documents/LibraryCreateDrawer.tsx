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
import { Alert, Box, Button, Drawer, TextField, Typography } from "@mui/material";
import React, { useState } from "react";
import { useTranslation } from "react-i18next";
import {
  useCreateTagKnowledgeFlowV1TagsPostMutation,
  TagType,
} from "../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { useToast } from "../ToastProvider";

interface LibraryCreateDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  onLibraryCreated?: () => void;
  mode: "documents" | "prompts";
  currentPath?: string;
}

/**
 * This module create a library of prompts or documents
 */
export const LibraryCreateDrawer: React.FC<LibraryCreateDrawerProps> = ({
  isOpen,
  onClose,
  onLibraryCreated,
  mode,
  currentPath,
}) => {
  const { t } = useTranslation();
  const { showError, showSuccess } = useToast();
  const [createTag, { isLoading, error }] = useCreateTagKnowledgeFlowV1TagsPostMutation();

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");

  const handleClose = () => {
    setName("");
    setDescription("");
    onClose();
  };

  const handleCreate = async (e?: React.FormEvent) => {
    e?.preventDefault();

    const trimmed = name.trim();
    if (!trimmed) {
      showError({
        summary: t("libraryCreateDrawer.validationError"),
        detail: t("libraryCreateDrawer.nameRequired"),
      });
      return;
    }

    // Option C guard: keep 'name' as a leaf (no '/')
    if (mode === "documents" && trimmed.includes("/")) {
      showError({
        summary: t("libraryCreateDrawer.validationError"),
        detail: t("libraryCreateDrawer.nameNoSlash") || "Name cannot contain '/'. Use the folder picker to change location.",
      });
      return;
    }

    try {
      const payload =
        mode === "documents"
          ? {
              name: trimmed,
              path: currentPath ?? null, // <- key line: put it under the current folder
              description: description.trim() || null,
              type: "document" as TagType,
              item_ids: [],
            }
          : {
              name: trimmed,
              description: description.trim() || null,
              type: "prompt" as TagType,
              item_ids: [],
            };

      await createTag({ tagCreate: payload }).unwrap();
      showSuccess({
        summary: t("libraryCreateDrawer.libraryCreated"),
        detail: t("libraryCreateDrawer.libraryCreatedDetail", { name: trimmed }),
      });

      onLibraryCreated?.();
      handleClose();

    } catch (err: any) {
      console.error("Error creating library:", err);
      const detail = err?.data?.detail || err?.message || String(err);
      showError({
        summary: t("libraryCreateDrawer.creationFailed"),
        detail,
      });
    }
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
          borderTopLeftRadius: 16,
          borderBottomLeftRadius: 16,
        },
      }}
    >
      <Typography variant="h5" fontWeight="bold" gutterBottom>
        {t("libraryCreateDrawer.title")}
      </Typography>

      {/* Small hint about where it will be created */}
      {mode === "documents" && (
        <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
          {t("libraryCreateDrawer.createUnder") || "Will be created under:"}{" "}
          <strong>{currentPath || "/"}</strong>
        </Typography>
      )}

      <Box component="form" onSubmit={handleCreate} sx={{ display: "flex", flexDirection: "column", gap: 3 }}>
        <TextField
          fullWidth
          label={t("libraryCreateDrawer.libraryName")}
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
          autoFocus
          inputProps={mode === "documents" ? { pattern: "^[^/]+$", title: "Name cannot contain '/'" } : undefined}
        />

        <TextField
          fullWidth
          label={t("libraryCreateDrawer.libraryDescription")}
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          multiline
          rows={3}
        />

        {error && (
          <Alert severity="error">
            {(error as any)?.data?.detail || t("libraryCreateDrawer.creationFailed")}
          </Alert>
        )}

        <Box sx={{ display: "flex", justifyContent: "space-between" }}>
          <Button variant="outlined" onClick={handleClose} sx={{ borderRadius: "8px" }}>
            {t("libraryCreateDrawer.cancel")}
          </Button>

          <Button
            variant="contained"
            color="success"
            startIcon={<SaveIcon />}
            type="submit"
            disabled={isLoading || !name.trim()}
            sx={{ borderRadius: "8px" }}
          >
            {isLoading ? t("libraryCreateDrawer.saving") : t("libraryCreateDrawer.save")}
          </Button>
        </Box>
      </Box>
    </Drawer>
  );
};
