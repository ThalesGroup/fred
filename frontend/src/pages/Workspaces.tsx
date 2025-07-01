// Copyright Thales 2025
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at:
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

import { useEffect, useState } from "react";
import {
  Box,
  Typography,
  Container,
  TextField,
  Paper,
  InputAdornment,
  Fab,
  Drawer,
  IconButton,
  Grid2,
} from "@mui/material";
import AddIcon from "@mui/icons-material/Add";
import SearchIcon from "@mui/icons-material/Search";
import CloseIcon from "@mui/icons-material/Close";
import { TopBar } from "../common/TopBar";
import { useToast } from "../components/ToastProvider";
import {
  useDeleteKnowledgeContextMutation,
  useUpdateKnowledgeContextMutation,
  useLazyGetKnowledgeContextsQuery,
} from "../slices/knowledgeContextApi";
import { PageBodyWrapper } from "../common/PageBodyWrapper";
import {
  KnowledgeContext,
  KnowledgeContextEditDialog,
  Document,
} from "../components/knowledgeContext/KnowledgeContextEditDialog";
import { KnowledgeContextItem } from "../components/knowledgeContext/KnowledgeContextItem";
import { KnowledgeContextCreateDialog } from "../components/knowledgeContext/KnowledgeContextCreateDialog";
import { useTranslation } from "react-i18next";

export const Workspaces = () => {
  const { t } = useTranslation();
  const [workspaces, setWorkspaces] = useState<KnowledgeContext[]>([]);
  const [search, setSearch] = useState("");
  const [getWorkspaces] = useLazyGetKnowledgeContextsQuery();
  const [deleteWorkspace] = useDeleteKnowledgeContextMutation();
  const [updateWorkspace] = useUpdateKnowledgeContextMutation();
  const [openDescription, setOpenDescription] = useState<KnowledgeContext | null>(null);
  const [openDialog, setOpenDialog] = useState(false);
  const [openEditDialog, setOpenEditDialog] = useState(false);
  const [currentWorkspace, setCurrentWorkspace] = useState<KnowledgeContext>();
  const { showError } = useToast();

  useEffect(() => {
    fetchWorkspaces();
  }, []);

  const fetchWorkspaces = async () => {
    try {
      const response = await getWorkspaces({ tag: "workspace" }).unwrap();
      setWorkspaces(response);
    } catch (e) {
      console.error("Failed to fetch workspaces", e);
    }
  };

  const handleOpenEditDialog = (workspace: KnowledgeContext) => {
    setCurrentWorkspace(workspace);
    setOpenEditDialog(true);
  };

  const handleSaveWorkspace = async ({
    title,
    description,
    files,
    documentsDescription,
  }: {
    title: string;
    description: string;
    files: File[];
    documents: Document[];
    documentsDescription: Record<string, string>;
  }) => {
    try {
      await updateWorkspace({
        knowledgeContext_id: currentWorkspace!.id,
        title,
        description,
        files,
        documentsDescription,
      }).unwrap();

      setOpenEditDialog(false);
      setCurrentWorkspace(undefined);
      await fetchWorkspaces();
    } catch (error: any) {
      showError({
        summary: "Update failed",
        detail: `Could not update workspace: ${error?.data?.detail || error.message}`,
      });
      await handleReloadProfile();
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await deleteWorkspace({ knowledgeContext_id: id }).unwrap();
      setWorkspaces((prev) => prev.filter((p) => p.id !== id));
    } catch (e) {
      showError({
        summary: "Delete failed",
        detail: `Could not delete workspace: ${e?.data?.detail || e.message}`,
      });
    }
  };

  const filteredWorkspaces = workspaces.filter((workspace) =>
    workspace.title.toLowerCase().includes(search.toLowerCase())
  );

  const handleReloadProfile = async () => {
    try {
      const response = await getWorkspaces({ tag: "workspace" }).unwrap();
      setWorkspaces(response);
      if (currentWorkspace) {
        const updated = response.find((p) => p.id === currentWorkspace.id);
        if (updated) {
          setCurrentWorkspace(updated);
        }
      }
    } catch (e) {
      showError({
        summary: "Reload failed",
        detail: `Could not reload workspace: ${e?.data?.detail || e.message}`,
      });
    }
  };

  return (
    <PageBodyWrapper>
      <TopBar title={t("workspaces.title")} description={t("workspaces.description")}>
        <Grid2 sx={{ display: "flex", justifyContent: "flex-end", mt: { xs: 1, md: 0 } }}></Grid2>
      </TopBar>

      <Container maxWidth="xl" sx={{ pb: 10, justifyContent: "center" }}>
        <Box mb={3}>
          <TextField
            fullWidth
            placeholder={t("workspaces.searchPlaceholder")}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            slotProps={{
              input: {
                startAdornment: (
                  <InputAdornment position="start">
                    <SearchIcon color="action" />
                  </InputAdornment>
                ),
              },
            }}
          />
        </Box>

        <Grid2 container spacing={3} alignItems="stretch">
          {filteredWorkspaces.map((w) => (
            <Grid2 size={{ xs: 12 }} key={w.id} display="flex">
              <KnowledgeContextItem
                onEdit={handleOpenEditDialog}
                onDelete={handleDelete}
                onViewDescription={setOpenDescription}
                allowDocuments
                allowDocumentDescription
                id={w.id}
                title={w.title}
                description={w.description}
                documents={w.documents}
              />
            </Grid2>
          ))}
        </Grid2>

        {filteredWorkspaces.length === 0 && (
          <Paper elevation={2} sx={{ p: 4, mt: 3, borderRadius: 2, textAlign: "center" }}>
            <Typography variant="body1">{t("workspaces.noResults")}</Typography>
          </Paper>
        )}

        <Fab
          color="primary"
          aria-label="add"
          sx={{ position: "fixed", bottom: 32, right: 32, zIndex: 10 }}
          onClick={() => setOpenDialog(true)}
        >
          <AddIcon />
        </Fab>

        <KnowledgeContextCreateDialog
          open={openDialog}
          onClose={() => setOpenDialog(false)}
          onCreated={fetchWorkspaces}
          dialogTitle={t("workspaces.createDialogTitle")}
          tag="workspace"
        />

        <KnowledgeContextEditDialog
          open={openEditDialog}
          onClose={() => setOpenEditDialog(false)}
          onSave={handleSaveWorkspace}
          context={currentWorkspace!}
          onReloadContext={handleReloadProfile}
          dialogTitle={t("workspaces.editDialogTitle")}
        />

        <Drawer
          anchor="right"
          open={Boolean(openDescription)}
          onClose={() => setOpenDescription(null)}
          PaperProps={{ sx: { width: { xs: "100%", sm: 500 }, p: 3 } }}
        >
          <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
            <Typography variant="h6">
              {openDescription?.title || t("workspaces.drawerTitle")}
            </Typography>
            <IconButton onClick={() => setOpenDescription(null)}>
              <CloseIcon />
            </IconButton>
          </Box>

          <Box
            sx={{
              fontFamily: "monospace",
              whiteSpace: "pre-wrap",
              lineHeight: 1.6,
              overflowY: "auto",
              color: "text.primary",
            }}
          >
            {openDescription?.description || t("workspaces.noDescription")}
          </Box>
        </Drawer>
      </Container>
    </PageBodyWrapper>
  );
};