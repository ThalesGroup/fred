import FolderOpenIcon from "@mui/icons-material/FolderOpen";
import UploadIcon from "@mui/icons-material/Upload";
import { Box, Button, CircularProgress, Container, Paper, Stack, Typography } from "@mui/material";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";
import { TopBar } from "../common/TopBar";
import { LibraryInfoCard } from "../components/documents/LibraryInfoCard";
import { PromptTable } from "../components/prompts/PromptTable";
import { EditPromptModal } from "../components/prompts/PromptEditor";
import { EmptyState } from "../components/EmptyState";
import { useToast } from "../components/ToastProvider";
import { KeyCloakService } from "../security/KeycloakService";
import {
  Prompt,
  useLazyGetPromptKnowledgeFlowV1PromptsPromptIdGetQuery,
  useCreatePromptKnowledgeFlowV1PromptsPostMutation,
  useUpdatePromptKnowledgeFlowV1PromptsPromptIdPutMutation,
  useUpdateTagKnowledgeFlowV1TagsTagIdPutMutation,
  useGetTagKnowledgeFlowV1TagsTagIdGetQuery,
} from "../slices/knowledgeFlow/knowledgeFlowOpenApi";

export const PromptLibraryViewPage = () => {
  const { t } = useTranslation();
  const { showError, showSuccess } = useToast();
  const { libraryId } = useParams<{ libraryId: string }>();

  const {
    data: tagsWithPromptIds,
    isLoading: isLoadingLibrary,
    refetch: refetchLibrary,
  } = useGetTagKnowledgeFlowV1TagsTagIdGetQuery({ tagId: libraryId ?? "" }, { skip: !libraryId });

  const [getPrompt] = useLazyGetPromptKnowledgeFlowV1PromptsPromptIdGetQuery();
  const [updateTag] = useUpdateTagKnowledgeFlowV1TagsTagIdPutMutation();
  const [updatePrompt] = useUpdatePromptKnowledgeFlowV1PromptsPromptIdPutMutation();
  const [createPrompt] = useCreatePromptKnowledgeFlowV1PromptsPostMutation();

  const [prompts, setPrompts] = useState<Prompt[]>([]);
  const [selectedPrompt, setSelectedPrompt] = useState<Prompt | null>(null);
  const [openCreatePrompt, setOpenCreatePrompt] = useState(false);

  const hasEditPermission = () => {
    const roles = KeyCloakService.GetUserRoles();
    return roles.includes("admin") || roles.includes("editor");
  };

  const fetchPrompts = async () => {
    if (!tagsWithPromptIds?.item_ids?.length) return;

    const results = await Promise.all(
      tagsWithPromptIds.item_ids.map((id) =>
        getPrompt({ promptId: id })
          .unwrap()
          .catch((err) => {
            console.error(`Error fetching prompt ${id}`, err);
            return undefined;
          }),
      ),
    );

    setPrompts(results.filter((p): p is Prompt => !!p));
  };

  const handleRefreshData = async () => {
    await refetchLibrary();
    await fetchPrompts();
  };

  const handleRemoveFromLibrary = async (toRemove: Prompt[]) => {
    if (!tagsWithPromptIds) return;

    try {
      const remainingIds = tagsWithPromptIds.item_ids?.filter((id) => !toRemove.some((p) => p.id === id)) || [];

      await updateTag({
        tagId: tagsWithPromptIds.id,
        tagUpdate: {
          name: tagsWithPromptIds.name,
          description: tagsWithPromptIds.description,
          type: tagsWithPromptIds.type,
          item_ids: remainingIds,
        },
      }).unwrap();

      showSuccess({
        summary: t("promptLibrary.removeSuccess"),
        detail: t("promptLibrary.removedDocuments", { count: toRemove.length }),
      });

      await handleRefreshData();
    } catch (error: any) {
      showError({
        summary: t("promptLibrary.removeError"),
        detail: error?.data?.detail || t("promptLibrary.removeErrorGeneric"),
      });
    }
  };

  const handleSavePrompt = async (prompt: Prompt) => {
    try {
      await updatePrompt({ promptId: prompt.id, prompt }).unwrap();
      showSuccess({ summary: "Updated", detail: `"${prompt.name}" was saved.` });
      await handleRefreshData();
    } catch (error: any) {
      showError({
        summary: "Update failed",
        detail: error?.data?.detail || "An error occurred while saving the prompt.",
      });
    }
  };

  const handleCreatePrompt = async (newPrompt: Prompt) => {
    try {
      await createPrompt({ prompt: { ...newPrompt, tags: [tagsWithPromptIds!.id] } }).unwrap();
      showSuccess({ summary: "Prompt created", detail: `"${newPrompt.name}" was added.` });
      await handleRefreshData();
      setOpenCreatePrompt(false);
    } catch (error: any) {
      showError({
        summary: "Creation failed",
        detail: error?.data?.detail || "Could not create prompt.",
      });
    }
  };

  useEffect(() => {
    if (tagsWithPromptIds) {
      fetchPrompts();
    }
  }, [tagsWithPromptIds]);

  if (isLoadingLibrary) {
    return (
      <Box display="flex" justifyContent="center" alignItems="center" minHeight="40vh">
        <CircularProgress />
      </Box>
    );
  }

  if (!tagsWithPromptIds) {
    return (
      <>
        <TopBar title="Library not found" description="The requested prompt library does not exist." />
        <Typography color="text.secondary" mt={4}>
          No prompt library found for ID: {libraryId}
        </Typography>
      </>
    );
  }
  console.log("PromptLibraryViewPage library:", tagsWithPromptIds);
  console.log("PromptLibraryViewPage prompts:", prompts);
  return (
    <>
      <TopBar
        title={tagsWithPromptIds.name}
        description={tagsWithPromptIds.description || ""}
        backTo="/knowledge?view=prompts"
      />

      <Container maxWidth="xl" sx={{ mb: 3, display: "flex", flexDirection: "column", gap: 4 }}>
        <LibraryInfoCard
          library={tagsWithPromptIds}
          hasEditPermission={hasEditPermission()}
          onLibraryUpdated={handleRefreshData}
        />

        <Stack gap={2}>
          {hasEditPermission() && (
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

          <Paper sx={{ p: 2, pt: 7, borderRadius: 4, position: "relative" }}>
            {prompts.length === 0 ? (
              <EmptyState
                icon={<FolderOpenIcon />}
                title={t("promptLibrary.emptyLibraryTitle")}
                description={t("promptLibrary.emptyLibraryDescription")}
                actionButton={
                  hasEditPermission()
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
                onEditPrompt={(p) => setSelectedPrompt(p)}
                onDeletePrompt={(p) => handleRemoveFromLibrary([p])}
              />
            )}
          </Paper>
        </Stack>
      </Container>

      {/* Create prompt modal */}
      {hasEditPermission() && (
        <EditPromptModal
          isOpen={openCreatePrompt}
          prompt={null}
          onClose={() => setOpenCreatePrompt(false)}
          onSave={handleCreatePrompt}
          getSuggestion={async () => {
            const res = await fetch("/api/ai/suggest-prompt");
            return (await res.json()).suggestion;
          }}
        />
      )}

      {/* Edit existing prompt modal */}
      <EditPromptModal
        isOpen={!!selectedPrompt}
        prompt={selectedPrompt}
        onClose={() => setSelectedPrompt(null)}
        onSave={handleSavePrompt}
      />
    </>
  );
};
