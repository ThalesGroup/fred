import FolderOpenIcon from "@mui/icons-material/FolderOpen";
import UploadIcon from "@mui/icons-material/Upload";
import { Box, Button, CircularProgress, Container, Paper, Stack, Typography } from "@mui/material";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";
import { TopBar } from "../common/TopBar";
import { LibraryInfoCard } from "../components/documents/LibraryInfoCard";
import { EmptyState } from "../components/EmptyState";
import { useToast } from "../components/ToastProvider";
import { KeyCloakService } from "../security/KeycloakService";
import {
  Prompt,
  useCreatePromptKnowledgeFlowV1PromptsPostMutation,
  useGetTagKnowledgeFlowV1TagsTagIdGetQuery,
  useLazyGetPromptKnowledgeFlowV1PromptsPromptIdGetQuery,
  useUpdatePromptKnowledgeFlowV1PromptsPromptIdPutMutation,
  useUpdateTagKnowledgeFlowV1TagsTagIdPutMutation,
} from "../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { PromptTable } from "../components/prompts/PromptTable";
import { EditPromptModal } from "../components/prompts/PromptEditor";

export const PromptLibraryViewPage = () => {
  const { t } = useTranslation();
  const { showError, showSuccess } = useToast();
  const { libraryId } = useParams<{ libraryId: string }>();
  const {
    data: library,
    isLoading: isLoadingLibrary,
    refetch: refetchLibrary,
  } = useGetTagKnowledgeFlowV1TagsTagIdGetQuery({ tagId: libraryId || "" }, { skip: !libraryId });
  const [selectedPrompt, setSelectedPrompt] = useState<Prompt | null>(null);
  const [getPrompt] = useLazyGetPromptKnowledgeFlowV1PromptsPromptIdGetQuery();
  const [updatePrompt] = useUpdatePromptKnowledgeFlowV1PromptsPromptIdPutMutation();
  const [createPrompt] = useCreatePromptKnowledgeFlowV1PromptsPostMutation();
  const [openCreatePrompt, setOpenCreatePrompt] = useState(false);

  const openEditModal = (prompt: Prompt) => {
    setSelectedPrompt(prompt);
  };
  const [updateTag] = useUpdateTagKnowledgeFlowV1TagsTagIdPutMutation();
  const [prompts, setPrompts] = useState<Prompt[]>([]);

  const hasDocumentManagementPermission = () => {
    const userRoles = KeyCloakService.GetUserRoles();
    return userRoles.includes("admin") || userRoles.includes("editor");
  };

  const fetchPrompts = async () => {
    if (!library?.item_ids) return;

    const promptFetches: Promise<Prompt | undefined>[] = library.item_ids.map((id) =>
      getPrompt({ promptId: id })
        .unwrap()
        .catch((err) => {
          console.error(`Failed to load prompt ${id}`, err);
          return undefined;
        }),
    );

    const fetched = (await Promise.all(promptFetches)).filter((p): p is Prompt => !!p);
    setPrompts(fetched); // Replace your old setDocuments(docs)
  };

  const handleRefreshData = async () => {
    await refetchLibrary();
    await fetchPrompts();
  };

  const handleUploadComplete = () => {
    handleRefreshData();
  };

  const handlePromptSave = async (updated: Prompt) => {
    try {
      await updatePrompt({ promptId: updated.id, prompt: updated }).unwrap();
      showSuccess({ summary: "Updated", detail: `"${updated.name}" was saved.` });
      await handleRefreshData();
    } catch (error: any) {
      console.error("Failed to update prompt", error);
      showError({
        summary: "Error",
        detail: error?.data?.detail || "Could not save the prompt",
      });
    }
  };
  const handleRemoveFromLibrary = async (prompts: Prompt[]) => {
    if (!library) return;

    try {
      const promptIdsToRemove = prompts.map((p) => p.id);
      const updatedPromptIds = library.item_ids?.filter((id) => !promptIdsToRemove.includes(id)) || [];

      await updateTag({
        tagId: library.id,
        tagUpdate: {
          name: library.name,
          description: library.description,
          type: library.type,
          item_ids: updatedPromptIds,
        },
      }).unwrap();

      showSuccess({
        summary: t("promptLibrary.removeSuccess"),
        detail: t("promptLibrary.removedDocuments", { count: prompts.length }),
      });
    } catch (error: any) {
      showError({
        summary: t("promptLibrary.removeError"),
        detail: error?.data?.detail || t("promptLibrary.removeErrorGeneric"),
      });
    }
  };

  useEffect(() => {
    if (library) {
      console.log("Fetching prompts for library:", library.name, library.item_ids);
      fetchPrompts();
    }
  }, [library]);

  if (isLoadingLibrary) {
    return (
      <Box display="flex" justifyContent="center" alignItems="center" minHeight="40vh">
        <CircularProgress />
      </Box>
    );
  }

  if (!library) {
    return (
      <>
        <TopBar title="Library not found" description="The requested prompt library does not exist." />
        <Typography color="text.secondary" mt={4}>
          No prompt library found for ID: {libraryId}
        </Typography>
      </>
    );
  }

  return (
    <>
      <TopBar title={library.name} description={library.description || ""} backTo="/knowledge?view=prompts"></TopBar>

      <Container maxWidth="xl" sx={{ mb: 3, display: "flex", flexDirection: "column", gap: 4 }}>
        {/* Library name and description */}
        <LibraryInfoCard
          library={library}
          hasEditPermission={hasDocumentManagementPermission()}
          onLibraryUpdated={handleRefreshData}
        />

        <Stack gap={2}>
          {/* Upload button */}
          {hasDocumentManagementPermission() && (
            <Stack direction="row" spacing={2} justifyContent="flex-end">
              <Button
                variant="contained"
                startIcon={<UploadIcon />}
                onClick={() => setOpenCreatePrompt(true)}
                size="medium"
                sx={{ borderRadius: "8px" }}
              >
                {t("promptLibrary.uploadInLibrary")}
              </Button>
            </Stack>
          )}

          {/* List of documents */}
          <Paper
            sx={{
              p: 2,
              pt: 7, // To make space for DocumentTableSelectionToolbar (used for bulk actions)
              borderRadius: 4,
              position: "relative",
            }}
          >
            {prompts.length === 0 ? (
              <EmptyState
                icon={<FolderOpenIcon />}
                title={t("promptLibrary.emptyLibraryTitle")}
                description={t("promptLibrary.emptyLibraryDescription")}
                actionButton={
                  hasDocumentManagementPermission()
                    ? {
                        label: t("promptLibrary.uploadFirstDocument"),
                        onClick: () => setOpenCreatePrompt(true),
                        startIcon: <UploadIcon />,
                        variant: "outlined",
                      }
                    : undefined
                }
              />
            ) : (
              <PromptTable
                prompts={prompts}
                onEditPrompt={openEditModal}
                onDeletePrompt={(prompt) => handleRemoveFromLibrary([prompt])}
              />
            )}
          </Paper>
        </Stack>
      </Container>

      {hasDocumentManagementPermission() && (
        <EditPromptModal
          isOpen={openCreatePrompt}
          prompt={null}
          onClose={() => setOpenCreatePrompt(false)}
          onSave={async (newPrompt) => {
            await createPrompt({ prompt: { ...newPrompt, tags: [library.id] } }).unwrap();
            showSuccess({ summary: "Prompt created", detail: `"${newPrompt.name}" was added.` });
            await handleRefreshData();
            setOpenCreatePrompt(false);
          }}
          getSuggestion={async () => {
            const res = await fetch("/api/ai/suggest-prompt");
            const json = await res.json();
            return json.suggestion;
          }}
        />
      )}

      <EditPromptModal
        isOpen={!!selectedPrompt}
        prompt={selectedPrompt}
        onClose={() => setSelectedPrompt(null)}
        onSave={handlePromptSave}
      />
    </>
  );
};
