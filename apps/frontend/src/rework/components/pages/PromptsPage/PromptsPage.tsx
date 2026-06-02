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
import PageEmptyState from "@shared/molecules/PageEmptyState/PageEmptyState.tsx";
import ServiceNotice from "@shared/molecules/ServiceNotice/ServiceNotice.tsx";
import { FullPageModal } from "@shared/molecules/FullPageModal/FullPageModal.tsx";
import PromptCard from "@shared/organisms/PromptCard/PromptCard.tsx";
import { CategoryPicker } from "@shared/molecules/CategoryPicker/CategoryPicker.tsx";
import Icon from "@shared/atoms/Icon/Icon.tsx";
import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";
import { getQueryUiState } from "@core/utils/queryUiState.ts";
import { useConfirmationDialog } from "../../../../components/ConfirmationDialogProvider";
import { useToast } from "../../../../components/ToastProvider";
import {
  type PromptCategory,
  type PromptSummary,
  useDeleteTeamPromptControlPlaneV1TeamsTeamIdPromptsPromptIdDeleteMutation,
  useGetTeamPromptControlPlaneV1TeamsTeamIdPromptsPromptIdGetQuery,
  useGetTeamPromptsControlPlaneV1TeamsTeamIdPromptsGetQuery,
  usePostTeamPromptControlPlaneV1TeamsTeamIdPromptsPostMutation,
  usePutTeamPromptControlPlaneV1TeamsTeamIdPromptsPromptIdPutMutation,
} from "../../../../slices/controlPlane/controlPlaneOpenApi";
import { PROMPT_CATEGORIES } from "../../../config/promptCategories.ts";
import styles from "./PromptsPage.module.scss";

type FormState = {
  name: string;
  description: string;
  category: PromptCategory;
  tags: string[];
  text: string;
};
const emptyForm: FormState = { name: "", description: "", category: "other", tags: [], text: "" };

export default function PromptsPage() {
  const { teamId } = useParams<{ teamId: string }>();
  const { t, i18n } = useTranslation();
  const { showError, showSuccess } = useToast();
  const { showConfirmationDialog } = useConfirmationDialog();

  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [editingPrompt, setEditingPrompt] = useState<PromptSummary | null>(null);
  const [viewingDefault, setViewingDefault] = useState<PromptSummary | null>(null);
  const [form, setForm] = useState<FormState>(emptyForm);
  const [search, setSearch] = useState("");
  const [activeCategory, setActiveCategory] = useState<PromptCategory | null>(null);
  const [filtersExpanded, setFiltersExpanded] = useState(false);
  const searchRef = useRef<HTMLInputElement>(null);
  const FILTER_VISIBLE = 4;

  const lang = i18n.language.split("-")[0];

  const {
    data: prompts = [],
    isLoading,
    isFetching,
    isUninitialized,
    isError,
    refetch,
  } = useGetTeamPromptsControlPlaneV1TeamsTeamIdPromptsGetQuery({ teamId: teamId || "", lang }, { skip: !teamId });

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
        category: (editDetail.category as PromptCategory) ?? "other",
        tags: editDetail.tags ?? [],
        text: editDetail.text,
      });
    }
  }, [editDetail]);

  // Collect categories actually used in the current prompt list
  const usedCategories = useMemo(() => {
    const ids = new Set(prompts.map((p) => p.category).filter(Boolean) as PromptCategory[]);
    return PROMPT_CATEGORIES.filter((c) => ids.has(c.id));
  }, [prompts]);

  // Client-side filter: search text + active category + active tag
  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return prompts.filter((p) => {
      const matchSearch = !q || p.name.toLowerCase().includes(q) || (p.description ?? "").toLowerCase().includes(q);
      const matchCategory = !activeCategory || p.category === activeCategory;
      return matchSearch && matchCategory;
    });
  }, [prompts, search, activeCategory]);

  const isSubmitting = isCreating || isUpdating;

  const openCreate = () => {
    setForm(emptyForm);
    setIsCreateOpen(true);
  };

  const openPrompt = (prompt: PromptSummary) => {
    if (prompt.is_default) {
      setViewingDefault(prompt);
    } else {
      setForm({ ...emptyForm, category: (prompt.category as PromptCategory) ?? "other" });
      setEditingPrompt(prompt);
    }
  };

  const closeModal = () => {
    setIsCreateOpen(false);
    setEditingPrompt(null);
    setViewingDefault(null);
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
            category: form.category,
            tags: form.tags,
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
            category: form.category,
            tags: form.tags,
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

  const hasPrompts = true; // defaults are always injected by the backend
  const promptsQueryState = getQueryUiState({ isLoading, isFetching, isUninitialized, isError });

  if (!teamId) {
    return <div className={styles.pageError}>Missing team id in route.</div>;
  }

  if (promptsQueryState === "loading") {
    return <div className={styles.loadingState}>{t("rework.teams.prompts.loading")}</div>;
  }

  if (promptsQueryState === "error") {
    return (
      <ServiceNotice
        icon="cloud_off"
        title={t("rework.serviceNotice.controlPlane.title")}
        description={t("rework.serviceNotice.controlPlane.description")}
        centered
      />
    );
  }

  return (
    <div className={styles.pageContainer}>
      {hasPrompts && (
        <>
          {/* ── Toolbar: title + create button ── */}
          <div className={styles.pageTitle}>
            <span>{t("rework.teams.prompts.title")}</span>
            <Button
              color="primary"
              variant="filled"
              size="medium"
              icon={{ category: "outlined", type: "add" }}
              onClick={openCreate}
            >
              {t("rework.teams.prompts.create")}
            </Button>
          </div>

          {/* ── Search + category filters ── */}
          <div className={styles.filterBar}>
            <div className={styles.searchWrapper}>
              <span className={styles.searchIcon}>
                <Icon category="outlined" type="search" />
              </span>
              <input
                ref={searchRef}
                className={styles.searchInput}
                placeholder="Rechercher un prompt…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
              {search && (
                <button className={styles.searchClear} onClick={() => setSearch("")}>
                  ✕
                </button>
              )}
            </div>

            {usedCategories.length > 0 && (
              <div className={styles.tagChips}>
                <button
                  className={styles.tagChip}
                  data-active={activeCategory === null}
                  onClick={() => setActiveCategory(null)}
                >
                  {t("rework.teams.agents.podFilter.all")}
                </button>
                {(filtersExpanded ? usedCategories : usedCategories.slice(0, FILTER_VISIBLE)).map((cat) => (
                  <button
                    key={cat.id}
                    className={styles.tagChip}
                    data-active={activeCategory === cat.id}
                    onClick={() => setActiveCategory(activeCategory === cat.id ? null : cat.id)}
                  >
                    {t(cat.labelKey)}
                  </button>
                ))}
                {usedCategories.length > FILTER_VISIBLE && (
                  <button className={styles.tagChipMore} onClick={() => setFiltersExpanded((e) => !e)}>
                    {filtersExpanded ? "−" : `+${usedCategories.length - FILTER_VISIBLE}`}
                  </button>
                )}
              </div>
            )}
          </div>
        </>
      )}

      {!hasPrompts ? (
        <PageEmptyState
          icon="edit_note"
          message={t("rework.teams.prompts.noPrompt")}
          action={{ label: t("rework.teams.prompts.firstCreate"), onClick: openCreate }}
        />
      ) : filtered.length === 0 ? (
        <div className={styles.emptyState}>Aucun prompt ne correspond à cette recherche.</div>
      ) : (
        <div className={styles.promptList}>
          {filtered.map((prompt) => (
            <PromptCard
              key={prompt.id}
              prompt={prompt}
              canManage={!prompt.is_default}
              onEdit={() => openPrompt(prompt)}
            />
          ))}
        </div>
      )}

      {/* ── Read-only modal for default prompts ── */}
      <FullPageModal isOpen={!!viewingDefault} onClose={closeModal} id="prompt-default-modal">
        {viewingDefault && (
          <div className={styles.modalCard}>
            <div className={styles.modalHeader}>
              <span className={styles.modalTitle}>{viewingDefault.name}</span>
              <IconButton
                size="small"
                color="on-surface"
                variant="icon"
                icon={{ category: "outlined", type: "close" }}
                onClick={closeModal}
              />
            </div>
            {viewingDefault.description && (
              <p style={{ margin: 0, color: "var(--on-surface-variant)", font: "var(--font-body-medium)" }}>
                {viewingDefault.description}
              </p>
            )}
            <TextArea
              label="Prompt text"
              value={viewingDefault.text_preview ?? ""}
              rows={12}
              onChange={() => {}}
              disabled
            />
            <div className={styles.modalFooter}>
              <div className={styles.modalFooterActions}>
                <Button color="on-surface" variant="text" size="medium" onClick={closeModal}>
                  {t("rework.teams.prompts.close")}
                </Button>
              </div>
            </div>
          </div>
        )}
      </FullPageModal>

      {/* ── Create / Edit modal ── */}
      <FullPageModal isOpen={isCreateOpen || !!editingPrompt} onClose={closeModal} id="prompt-form-modal">
        <div className={styles.modalCard}>
          <div className={styles.modalHeader}>
            <span className={styles.modalTitle}>
              {editingPrompt ? t("rework.teams.prompts.modalEdit") : t("rework.teams.prompts.modalCreate")}
            </span>
            <IconButton
              size="small"
              color="on-surface"
              variant="icon"
              icon={{ category: "outlined", type: "close" }}
              onClick={closeModal}
            />
          </div>

          <div className={styles.modalContent}>
            {/* ── Emoji + Name row ── */}
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

            <CategoryPicker value={form.category} onChange={(cat) => setForm((f) => ({ ...f, category: cat }))} />

            <TextArea
              label="Prompt text"
              required
              value={form.text}
              rows={8}
              onChange={(e) => setForm((f) => ({ ...f, text: e.target.value }))}
            />
          </div>

          <div className={styles.modalFooter}>
            {editingPrompt && (
              <Button color="error" variant="text" size="medium" onClick={() => handleDelete(editingPrompt)}>
                Delete
              </Button>
            )}
            <div className={styles.modalFooterActions}>
              <Button color="on-surface" variant="text" size="medium" onClick={closeModal}>
                Cancel
              </Button>
              <Button
                color="primary"
                variant="filled"
                size="medium"
                onClick={handleSubmit}
                disabled={isSubmitting || !form.name.trim() || !form.text.trim()}
              >
                {editingPrompt ? "Save" : "Create"}
              </Button>
            </div>
          </div>
        </div>
      </FullPageModal>
    </div>
  );
}
