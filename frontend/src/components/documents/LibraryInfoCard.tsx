import EditIcon from "@mui/icons-material/Edit";
import { Box, Button, Paper, TextField, Typography } from "@mui/material";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import {
  TagUpdate,
  TagWithDocumentsId,
  useUpdateTagKnowledgeFlowV1TagsTagIdPutMutation,
} from "../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { useToast } from "../ToastProvider";

interface LibraryInfoCardProps {
  library: TagWithDocumentsId;
  hasEditPermission: boolean;
  onLibraryUpdated: () => void;
}

export const LibraryInfoCard = ({ library, hasEditPermission, onLibraryUpdated }: LibraryInfoCardProps) => {
  const { t } = useTranslation();
  const { showError } = useToast();
  const [updateTag] = useUpdateTagKnowledgeFlowV1TagsTagIdPutMutation();

  const [isEditing, setIsEditing] = useState(false);
  const [editForm, setEditForm] = useState({ name: "", description: "" });

  const handleEditClick = () => {
    setEditForm({ name: library.name, description: library.description || "" });
    setIsEditing(true);
  };

  const handleCancelEdit = () => {
    setIsEditing(false);
    setEditForm({ name: "", description: "" });
  };

  const handleSaveEdit = async () => {
    try {
      const tagUpdate: TagUpdate = {
        name: editForm.name,
        description: editForm.description || null,
        type: library.type,
        document_ids: library.document_ids,
      };

      await updateTag({ tagId: library.id, tagUpdate }).unwrap();
      setIsEditing(false);
      onLibraryUpdated();
    } catch (error) {
      console.error("Error updating library:", error);
      showError({
        summary: t("libraryEdit.updateFailed"),
        detail: t("libraryEdit.updateFailedDetail"),
      });
    }
  };

  return (
    <Paper sx={{ p: 3, borderRadius: 4, mt: 2 }}>
      {isEditing ? (
        <Box>
          <TextField
            fullWidth
            variant="outlined"
            label={t("dialogs.edit.name")}
            value={editForm.name}
            onChange={(e) => setEditForm({ ...editForm, name: e.target.value })}
            sx={{ mb: 2 }}
          />
          <TextField
            fullWidth
            variant="outlined"
            label={t("dialogs.edit.description")}
            value={editForm.description}
            onChange={(e) => setEditForm({ ...editForm, description: e.target.value })}
            multiline
            rows={3}
            sx={{ mb: 2 }}
          />
          <Box sx={{ display: "flex", gap: 1 }}>
            <Button variant="outlined" onClick={handleCancelEdit}>
              {t("libraryEdit.cancel")}
            </Button>
            <Button variant="contained" onClick={handleSaveEdit}>
              {t("libraryEdit.save")}
            </Button>
          </Box>
        </Box>
      ) : (
        <Box>
          <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", mb: 1 }}>
            <Typography variant="h4" gutterBottom sx={{ mb: 0 }}>
              {library.name}
            </Typography>
            {hasEditPermission && (
              <Button variant="outlined" startIcon={<EditIcon />} onClick={handleEditClick} size="small">
                {t("libraryEdit.edit")}
              </Button>
            )}
          </Box>
          <Typography variant="body2" color="text.secondary">
            {library.description || "No description available."}
          </Typography>
        </Box>
      )}
    </Paper>
  );
};
