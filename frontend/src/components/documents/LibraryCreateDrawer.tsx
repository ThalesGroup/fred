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

import React, { useState } from "react";
import { Box, Typography, TextField, Button, Drawer } from "@mui/material";
import SaveIcon from "@mui/icons-material/Save";
import { useTranslation } from "react-i18next";
import { useToast } from "../ToastProvider";
import { useCreateTagKnowledgeFlowV1TagsPostMutation } from "../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { useNavigate } from "react-router-dom";

interface LibraryCreateDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  onLibraryCreated?: () => void;
}

export const LibraryCreateDrawer: React.FC<LibraryCreateDrawerProps> = ({
  isOpen,
  onClose,
  onLibraryCreated,
}) => {
  const { t } = useTranslation();
  const { showError, showSuccess } = useToast();
  const navigate = useNavigate();
  const [createTag, { isLoading }] = useCreateTagKnowledgeFlowV1TagsPostMutation();

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");

  const handleClose = () => {
    setName("");
    setDescription("");
    onClose();
  };

  const handleCreate = async () => {
    if (!name.trim()) {
      showError({
        summary: t("libraryCreateDrawer.validationError"),
        detail: t("libraryCreateDrawer.nameRequired"),
      });
      return;
    }

    try {
      const result = await createTag({
        tagCreate: {
          name: name.trim(),
          description: description.trim() || null,
          type: "library",
          document_ids: [],
        },
      }).unwrap();

      showSuccess({
        summary: t("libraryCreateDrawer.libraryCreated"),
        detail: t("libraryCreateDrawer.libraryCreatedDetail", { name }),
      });

      onLibraryCreated?.();
      handleClose();
      navigate(`/documentLibrary/${result.id}`);
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

      <Box sx={{ mt: 3 }}>
        <TextField
          fullWidth
          label={t("libraryCreateDrawer.libraryName")}
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
          sx={{ mb: 2 }}
        />

        <TextField
          fullWidth
          label={t("libraryCreateDrawer.libraryDescription")}
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          multiline
          rows={3}
          sx={{ mb: 3 }}
        />
      </Box>

      <Box sx={{ mt: 3, display: "flex", justifyContent: "space-between" }}>
        <Button variant="outlined" onClick={handleClose} sx={{ borderRadius: "8px" }}>
          {t("libraryCreateDrawer.cancel")}
        </Button>

        <Button
          variant="contained"
          color="success"
          startIcon={<SaveIcon />}
          onClick={handleCreate}
          disabled={isLoading || !name.trim()}
          sx={{ borderRadius: "8px" }}
        >
          {isLoading ? t("libraryCreateDrawer.saving") : t("libraryCreateDrawer.save")}
        </Button>
      </Box>
    </Drawer>
  );
};