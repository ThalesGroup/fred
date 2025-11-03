// Copyright Thales 2025
import SaveIcon from "@mui/icons-material/Save";
import { Alert, Box, Button, Drawer, TextField, Typography } from "@mui/material";
import React, { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useToast } from "../components/ToastProvider";
import { TagType, useCreateTagKnowledgeFlowV1TagsPostMutation } from "../slices/knowledgeFlow/knowledgeFlowOpenApi";

interface LibraryCreateDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  onLibraryCreated?: () => void;
  mode: TagType;
  /** Parent folder as a path like "thales/six" or "/" or undefined */
  currentPath?: string;
}

/** ---- Helpers ---- */
const normalizePathForApi = (p?: string | null): string | null => {
  if (!p) return null;
  const normalized = p.split("/").filter(Boolean).join("/");
  return normalized.length ? normalized : null; // API expects null at root
};

const validateLeafName = (s: string) => !s.includes("/"); // name is a single segment

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

  // Normalize once per render; safe for passing to API
  const parentPath = useMemo(() => normalizePathForApi(currentPath), [currentPath]);

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

    // Enforce leaf-only for BOTH modes (backend assumes name is the leaf)
    if (!validateLeafName(trimmed)) {
      showError({
        summary: t("libraryCreateDrawer.validationError"),
        detail:
          t("libraryCreateDrawer.nameNoSlash") || "Name cannot contain '/'. Use the folder picker to set the location.",
      });
      return;
    }

    try {
      const payload = {
        name: trimmed,
        path: parentPath, // ✅ always normalized (null at root)
        description: description.trim() || null,
        type: mode,
        item_ids: [] as string[],
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
      showError({ summary: t("libraryCreateDrawer.creationFailed"), detail });
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
        },
      }}
    >
      <Typography variant="h5" fontWeight="bold" gutterBottom>
        {t("libraryCreateDrawer.title")}
      </Typography>

      {/* Always show target location so users understand hierarchy */}
      <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
        {t("libraryCreateDrawer.createUnder") || "Will be created under:"} <strong>{parentPath || "/"}</strong>
      </Typography>

      <Box component="form" onSubmit={handleCreate} sx={{ display: "flex", flexDirection: "column", gap: 3 }}>
        <TextField
          fullWidth
          label={t("libraryCreateDrawer.libraryName")}
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
          autoFocus
          inputProps={{ pattern: "^[^/]+$", title: "Name cannot contain '/'" }}
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
          <Alert severity="error">{(error as any)?.data?.detail || t("libraryCreateDrawer.creationFailed")}</Alert>
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
