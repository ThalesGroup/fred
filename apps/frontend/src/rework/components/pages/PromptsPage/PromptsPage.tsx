// Copyright Thales 2026
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

import Button from "@shared/atoms/Button/Button.tsx";
import IconButton from "@shared/atoms/IconButton/IconButton.tsx";
import TextArea from "@shared/atoms/TextArea/TextArea.tsx";
import TextInput from "@shared/atoms/TextInput/TextInput.tsx";
import ServiceNotice from "@shared/molecules/ServiceNotice/ServiceNotice.tsx";
import { FullPageModal } from "@shared/molecules/FullPageModal/FullPageModal.tsx";
import PromptCard from "@shared/organisms/PromptCard/PromptCard.tsx";
import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { useConfirmationDialog } from "../../../../components/ConfirmationDialogProvider";
import { useToast } from "../../../../components/ToastProvider";
import {
  type PromptSummary,
  useDeleteTeamPromptControlPlaneV1TeamsTeamIdPromptsPromptIdDeleteMutation,
  useGetTeamPromptControlPlaneV1TeamsTeamIdPromptsPromptIdGetQuery,
  useGetTeamPromptsControlPlaneV1TeamsTeamIdPromptsGetQuery,
  usePostTeamPromptControlPlaneV1TeamsTeamIdPromptsPostMutation,
  usePutTeamPromptControlPlaneV1TeamsTeamIdPromptsPromptIdPutMutation,
} from "../../../../slices/controlPlane/controlPlaneOpenApi";
import styles from "./PromptsPage.module.scss";

type FormState = { name: string; description: string; text: string };
const emptyForm: FormState = { name: "", description: "", text: "" };

export default function PromptsPage() {
  const { teamId } = useParams<{ teamId: string }>();
  const { showError, showSuccess } = useToast();
  const { showConfirmationDialog } = useConfirmationDialog();

  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [editingPrompt, setEditingPrompt] = useState<PromptSummary | null>(null);
  const [form, setForm] = useState<FormState>(emptyForm);

  const {
    data: prompts = [],
    isLoading,
    isError,
    refetch,
  } = useGetTeamPromptsControlPlaneV1TeamsTeamIdPromptsGetQuery({ teamId: teamId || "" }, { skip: !teamId });

  const { data: editDetail } = useGetTeamPromptControlPlaneV1TeamsTeamIdPromptsPromptIdGetQuery(
    { teamId: teamId || "", promptId: editingPrompt?.id || "" },
    { skip: !editingPrompt },
  );

  const [createPrompt, { isLoading: isCreating }] = usePostTeamPromptControlPlaneV1TeamsTeamIdPromptsPostMutation();
  const [updatePrompt, { isLoading: isUpdating }] =
    usePutTeamPromptControlPlaneV1TeamsTeamIdPromptsPromptIdPutMutation();
  const [deletePrompt] = useDeleteTeamPromptControlPlaneV1TeamsTeamIdPromptsPromptIdDeleteMutation();

  useEffect(() => {
    if (editDetail) {
      setForm({
        name: editDetail.name,
        description: editDetail.description ?? "",
        text: editDetail.text,
      });
    }
  }, [editDetail]);

  const isModalOpen = isCreateOpen || editingPrompt !== null;
  const isSubmitting = isCreating || isUpdating;

  const openCreate = () => {
    setForm(emptyForm);
    setIsCreateOpen(true);
  };

  const openEdit = (prompt: PromptSummary) => {
    setForm(emptyForm);
    setEditingPrompt(prompt);
  };

  const closeModal = () => {
    setIsCreateOpen(false);
    setEditingPrompt(null);
    setForm(emptyForm);
  };

  const handleSubmit = async () => {
    if (!teamId || !form.name.trim() || !form.text.trim()) return;
    try {
      if (editingPrompt) {
        await updatePrompt({
          teamId,
          promptId: editingPrompt.id,
          updatePromptRequest: {
            name: form.name,
            description: form.description || undefined,
            text: form.text,
          },
        }).unwrap();
        showSuccess({ summary: "Prompt updated" });
      } else {
        await createPrompt({
          teamId,
          createPromptRequest: {
            name: form.name,
            description: form.description || undefined,
            text: form.text,
          },
        }).unwrap();
        showSuccess({ summary: "Prompt created" });
      }
      closeModal();
      await refetch();
    } catch (error: unknown) {
      const err = error as { data?: { detail?: string }; message?: string };
      showError({
        summary: "Failed to save prompt",
        detail: err?.data?.detail || err?.message || String(error),
      });
    }
  };

  const handleDelete = (prompt: PromptSummary) => {
    if (!teamId) return;
    showConfirmationDialog({
      criticalAction: true,
      title: "Delete prompt?",
      message: `Remove "${prompt.name}"? This cannot be undone.`,
      onConfirm: async () => {
        try {
          await deletePrompt({ teamId, promptId: prompt.id }).unwrap();
          showSuccess({ summary: "Prompt deleted" });
          closeModal();
          await refetch();
        } catch (error: unknown) {
          const err = error as { data?: { detail?: string }; message?: string };
          showError({
            summary: "Failed to delete prompt",
            detail: err?.data?.detail || err?.message || String(error),
          });
        }
      },
    });
  };

  if (!teamId) {
    return <div className={styles.pageError}>Missing team id in route.</div>;
  }

  return (
    <div className={styles.pageContainer}>
      <div className={styles.pageTitle}>
        <span>Prompts</span>
        <Button
          color="primary"
          variant="filled"
          size="medium"
          icon={{ category: "outlined", type: "add" }}
          onClick={openCreate}
        >
          New prompt
        </Button>
      </div>

      {isError && (
        <ServiceNotice
          icon="cloud_off"
          title="Could not load prompts"
          description="Check your connection and try again."
        />
      )}

      {isLoading ? (
        <div className={styles.loadingState}>Loading prompts…</div>
      ) : prompts.length === 0 && !isError ? (
        <div className={styles.emptyState}>No prompts yet. Create your first one!</div>
      ) : (
        <div className={styles.promptList}>
          {prompts.map((prompt) => (
            <PromptCard key={prompt.id} prompt={prompt} canManage={true} onEdit={() => openEdit(prompt)} />
          ))}
        </div>
      )}

      <FullPageModal isOpen={isModalOpen} onClose={closeModal} id="prompt-form-modal">
        <div className={styles.modalCard}>
          <div className={styles.modalHeader}>
            <span className={styles.modalTitle}>{editingPrompt ? "Edit prompt" : "New prompt"}</span>
            <IconButton
              size="small"
              color="on-surface"
              variant="icon"
              icon={{ category: "outlined", type: "close" }}
              onClick={closeModal}
            />
          </div>

          <div className={styles.modalContent}>
            <TextInput
              label="Name"
              required
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              maxLength={120}
            />
            <TextInput
              label="Description"
              value={form.description}
              onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
              maxLength={300}
            />
            <TextArea
              label="Prompt text"
              required
              value={form.text}
              onChange={(e) => setForm((f) => ({ ...f, text: e.target.value }))}
              rows={10}
            />
          </div>

          <div className={styles.modalFooter}>
            {editingPrompt && (
              <Button color="error" variant="outlined" size="medium" onClick={() => handleDelete(editingPrompt)}>
                Delete
              </Button>
            )}
            <div className={styles.modalFooterActions}>
              <Button color="on-surface" variant="outlined" size="medium" onClick={closeModal}>
                Cancel
              </Button>
              <Button
                color="primary"
                variant="filled"
                size="medium"
                onClick={handleSubmit}
                disabled={isSubmitting || !form.name.trim() || !form.text.trim()}
              >
                {isSubmitting ? "Saving…" : editingPrompt ? "Save" : "Create"}
              </Button>
            </div>
          </div>
        </div>
      </FullPageModal>
    </div>
  );
}
