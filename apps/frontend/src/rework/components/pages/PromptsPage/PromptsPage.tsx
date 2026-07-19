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
import SearchField from "@shared/molecules/SearchField/SearchField.tsx";
import FilterChips from "@shared/molecules/FilterChips/FilterChips.tsx";
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";
import { getQueryUiState } from "@core/utils/queryUiState.ts";
import { useConfirmationDialog } from "@shared/molecules/ConfirmationDialog/ConfirmationDialogProvider";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
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
  // Which prompt id `form` is currently fully seeded for. RTK Query's
  // `editDetail` can keep the same object reference across a close/reopen
  // of the same card (skipping a query doesn't clear its last result), so
  // a `useEffect` keyed on `[editDetail]` alone would never re-fire on
  // reopen. Comparing against this id (a primitive, reset on close) makes
  // reseeding reliable regardless of `editDetail`'s identity.
  const [seededForId, setSeededForId] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [activeCategory, setActiveCategory] = useState<PromptCategory | null>(null);
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
    // `editingPrompt` must also be checked: `editDetail` is RTK Query's
    // *last* successful result for this endpoint, which lingers even after
    // the query is skipped (editingPrompt set back to null on close) — so
    // without this guard, resetting `seededForId` in `closeModal` would
    // immediately re-mark it "seeded" against that lingering `editDetail`
    // before the card is ever reopened.
    // `editDetail.id === editingPrompt.id` is required too: if the user
    // closes prompt A and opens prompt B before B's query resolves,
    // `editDetail` can still be A's lingering result while `editingPrompt`
    // is already B — without this check the form would seed from A's
    // content under B's id (PR review, chatgpt-codex-connector).
    if (editingPrompt && editDetail && editDetail.id === editingPrompt.id && seededForId !== editDetail.id) {
      setForm({
        name: editDetail.name,
        description: editDetail.description ?? "",
        category: (editDetail.category as PromptCategory) ?? "other",
        tags: editDetail.tags ?? [],
        text: editDetail.text,
      });
      setSeededForId(editDetail.id);
    }
  }, [editingPrompt, editDetail, seededForId]);

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
    setSeededForId(null);
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
            <SearchField
              value={search}
              onChange={setSearch}
              placeholder={t("rework.teams.prompts.searchPlaceholder")}
              clearAriaLabel={t("rework.teams.prompts.clearSearch")}
            />

            {usedCategories.length > 0 && (
              <FilterChips
                options={usedCategories.map((cat) => ({ id: cat.id, label: t(cat.labelKey) }))}
                value={activeCategory}
                onChange={(v) => setActiveCategory(v)}
                allLabel={t("rework.teams.agents.podFilter.all")}
                maxVisible={FILTER_VISIBLE}
                showMoreLabel={(count) => `+${count}`}
                showLessLabel="−"
              />
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
        <div className={styles.emptyState}>{t("rework.teams.prompts.emptySearch")}</div>
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
              <p style={{ margin: 0, color: "var(--on-surface-retreat)", font: "var(--font-body-medium)" }}>
                {viewingDefault.description}
              </p>
            )}
            <TextArea
              label={t("rework.teams.prompts.form.text")}
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
              label={t("rework.teams.prompts.form.name")}
              required
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              maxLength={120}
            />

            <TextInput
              label={t("rework.teams.prompts.form.description")}
              value={form.description}
              onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
              maxLength={300}
            />

            <CategoryPicker value={form.category} onChange={(cat) => setForm((f) => ({ ...f, category: cat }))} />

            <TextArea
              label={t("rework.teams.prompts.form.text")}
              required
              value={form.text}
              rows={8}
              onChange={(e) => setForm((f) => ({ ...f, text: e.target.value }))}
            />
          </div>

          <div className={styles.modalFooter}>
            {editingPrompt && (
              <Button color="error" variant="text" size="medium" onClick={() => handleDelete(editingPrompt)}>
                {t("rework.delete")}
              </Button>
            )}
            <div className={styles.modalFooterActions}>
              <Button color="on-surface" variant="text" size="medium" onClick={closeModal}>
                {t("rework.cancel")}
              </Button>
              <Button
                color="primary"
                variant="filled"
                size="medium"
                onClick={handleSubmit}
                disabled={isSubmitting || !form.name.trim() || !form.text.trim()}
              >
                {editingPrompt ? t("rework.save") : t("rework.create")}
              </Button>
            </div>
          </div>
        </div>
      </FullPageModal>
    </div>
  );
}
