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
import { Box, Button, Drawer, TextField, Typography } from "@mui/material";
import React, { useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import {
  useCreateTagKnowledgeFlowV1TagsPostMutation,
  useCreatePromptKnowledgeFlowV1PromptsPostMutation,
} from "../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { useToast } from "../ToastProvider";

interface LibraryCreateDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  onLibraryCreated?: () => void;
   mode: "documents" | "prompts";
}

export const LibraryCreateDrawer: React.FC<LibraryCreateDrawerProps> = ({ isOpen, onClose, onLibraryCreated, mode }) => {
  const { t } = useTranslation();
  const { showError, showSuccess } = useToast();
  const navigate = useNavigate();
  const [createTag, { isLoading }] = useCreateTagKnowledgeFlowV1TagsPostMutation();
  const [createPrompt, { isLoading: isPromptLoading }] = useCreatePromptKnowledgeFlowV1PromptsPostMutation();

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");

  const handleClose = () => {
    setName("");
    setDescription("");
    onClose();
  };

  const handleCreate = async (e?: React.FormEvent) => {
  e?.preventDefault();

  if (!name.trim()) {
    showError({
      summary: t("libraryCreateDrawer.validationError"),
      detail: t("libraryCreateDrawer.nameRequired"),
    });
    return;
  }

  try {
    let result;

    if (mode === "documents") {
      result = await createTag({
        tagCreate: {
          name: name.trim(),
          description: description.trim() || null,
          type: "library",
          item_ids: [],
        },
      }).unwrap();
    } else {
      result = await createTag({
        tagCreate: {
          name: name.trim(),
          description: description.trim() || null,
          type: "prompt",
          item_ids: [],
        },
      }).unwrap();
    }

    showSuccess({
      summary: t("libraryCreateDrawer.libraryCreated"),
      detail: t("libraryCreateDrawer.libraryCreatedDetail", { name }),
    });

    onLibraryCreated?.();
    handleClose();

    if (mode === "documents") {
      navigate(`/documentLibrary/${result.id}`);
    } else {
      navigate(`/promptLibrary/${result.id}`); 
    }
  } catch (error) {
    console.error("Error creating library:", error);
    showError({
      summary: t("libraryCreateDrawer.creationFailed"),
      detail: t("libraryCreateDrawer.creationFailedDetail", { error: error.message || error }),
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

      <Box component="form" onSubmit={handleCreate} sx={{ display: "flex", flexDirection: "column", gap: 3 }}>
        <TextField
          fullWidth
          label={t("libraryCreateDrawer.libraryName")}
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
          autoFocus
        />

        <TextField
          fullWidth
          label={t("libraryCreateDrawer.libraryDescription")}
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          multiline
          rows={3}
        />

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
