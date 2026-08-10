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
import { Spinner } from "@shared/atoms/Spinner/Spinner.tsx";
import { Tooltip } from "@shared/atoms/Tooltip/Tooltip.tsx";
import TextArea from "@shared/atoms/TextArea/TextArea.tsx";
import TextInput from "@shared/atoms/TextInput/TextInput.tsx";
import PageEmptyState from "@shared/molecules/PageEmptyState/PageEmptyState.tsx";
import ServiceNotice from "@shared/molecules/ServiceNotice/ServiceNotice.tsx";
import { FullPageModal } from "@shared/molecules/FullPageModal/FullPageModal.tsx";
import PromptCard from "@shared/organisms/PromptCard/PromptCard.tsx";
import { CategoryPicker } from "@shared/molecules/CategoryPicker/CategoryPicker.tsx";
import SearchInput from "@shared/molecules/SearchInput/SearchInput.tsx";
import FilterChips from "@shared/molecules/FilterChips/FilterChips.tsx";
import ManageCategoriesDialog from "./ManageCategoriesDialog/ManageCategoriesDialog.tsx";
import PromptViewDialog from "./PromptViewDialog/PromptViewDialog.tsx";
import DuplicatePromptDialog from "./DuplicatePromptDialog/DuplicatePromptDialog.tsx";
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { getQueryUiState } from "@core/utils/queryUiState.ts";
import { useConfirmationDialog } from "@shared/molecules/ConfirmationDialog/ConfirmationDialogProvider";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import { useSelectedTeam } from "../../../../hooks/useSelectedTeam.ts";
import { useTeamCapabilities } from "@hooks/useTeamCapabilities.ts";
import {
  type PromptSummary,
  useDeleteTeamPromptControlPlaneV1TeamsTeamIdPromptsPromptIdDeleteMutation,
  useGetTeamPromptControlPlaneV1TeamsTeamIdPromptsPromptIdGetQuery,
  useGetTeamPromptCategoriesControlPlaneV1TeamsTeamIdPromptCategoriesGetQuery,
  useGetTeamPromptsControlPlaneV1TeamsTeamIdPromptsGetQuery,
  usePostTeamPromptControlPlaneV1TeamsTeamIdPromptsPostMutation,
  usePostRecordPromptUseControlPlaneV1TeamsTeamIdPromptsPromptIdUsePostMutation,
  usePostPublishPromptControlPlaneV1TeamsTeamIdPromptsPromptIdPublishPostMutation,
  usePostUnpublishPromptControlPlaneV1TeamsTeamIdPromptsPromptIdUnpublishPostMutation,
  usePutTeamPromptControlPlaneV1TeamsTeamIdPromptsPromptIdPutMutation,
} from "../../../../slices/controlPlane/controlPlaneOpenApi";
import styles from "./PromptsPage.module.scss";

type FormState = {
  name: string;
  description: string;
  category_id: string | null;
  tags: string[];
  text: string;
};
const emptyForm: FormState = { name: "", description: "", category_id: null, tags: [], text: "" };

// Sentinel filter value for "prompts with no category" — distinct from `null`,
// which means "no filter active" (the "Tous" chip).
const NO_CATEGORY_FILTER_ID = "__no_category__";

export default function PromptsPage() {
  const { teamId, selectedTeam } = useSelectedTeam();
  const { canUpdateResources: canManage } = useTeamCapabilities(selectedTeam);
  const { t } = useTranslation();
  const { showError, showSuccess } = useToast();
  const { showConfirmationDialog } = useConfirmationDialog();

  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [editingPrompt, setEditingPrompt] = useState<PromptSummary | null>(null);
  const [viewingPrompt, setViewingPrompt] = useState<PromptSummary | null>(null);
  const [duplicatingPrompt, setDuplicatingPrompt] = useState<PromptSummary | null>(null);
  const [isManageCategoriesOpen, setIsManageCategoriesOpen] = useState(false);
  const [form, setForm] = useState<FormState>(emptyForm);
  // Which prompt id `form` is currently fully seeded for. RTK Query's
  // `editDetail` can keep the same object reference across a close/reopen
  // of the same card (skipping a query doesn't clear its last result), so
  // a `useEffect` keyed on `[editDetail]` alone would never re-fire on
  // reopen. Comparing against this id (a primitive, reset on close) makes
  // reseeding reliable regardless of `editDetail`'s identity.
  const [seededForId, setSeededForId] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [activeCategory, setActiveCategory] = useState<string | null>(null);
  const FILTER_VISIBLE = 4;

  const {
    data: prompts = [],
    isLoading,
    isFetching,
    isUninitialized,
    isError,
  } = useGetTeamPromptsControlPlaneV1TeamsTeamIdPromptsGetQuery({ teamId: teamId || "" }, { skip: !teamId });

  const { data: categories = [], refetch: refetchCategories } =
    useGetTeamPromptCategoriesControlPlaneV1TeamsTeamIdPromptCategoriesGetQuery(
      { teamId: teamId || "" },
      { skip: !teamId },
    );

  const { data: editDetail } = useGetTeamPromptControlPlaneV1TeamsTeamIdPromptsPromptIdGetQuery(
    { teamId: teamId || "", promptId: editingPrompt?.id || "" },
    { skip: !editingPrompt },
  );

  // Duplicating needs the source's full text (the list projection only carries
  // a preview), so fetch the detail for the prompt being duplicated.
  const { data: duplicateDetail } = useGetTeamPromptControlPlaneV1TeamsTeamIdPromptsPromptIdGetQuery(
    { teamId: teamId || "", promptId: duplicatingPrompt?.id || "" },
    { skip: !duplicatingPrompt },
  );

  const [createPrompt, { isLoading: isCreating }] = usePostTeamPromptControlPlaneV1TeamsTeamIdPromptsPostMutation();
  const [updatePrompt, { isLoading: isUpdating }] =
    usePutTeamPromptControlPlaneV1TeamsTeamIdPromptsPromptIdPutMutation();
  const [deletePrompt] = useDeleteTeamPromptControlPlaneV1TeamsTeamIdPromptsPromptIdDeleteMutation();
  const [publishPrompt] = usePostPublishPromptControlPlaneV1TeamsTeamIdPromptsPromptIdPublishPostMutation();
  const [unpublishPrompt] = usePostUnpublishPromptControlPlaneV1TeamsTeamIdPromptsPromptIdUnpublishPostMutation();
  const [recordPromptUse] = usePostRecordPromptUseControlPlaneV1TeamsTeamIdPromptsPromptIdUsePostMutation();
  const [duplicatePrompt, { isLoading: isDuplicating }] =
    usePostTeamPromptControlPlaneV1TeamsTeamIdPromptsPostMutation();

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
        category_id: editDetail.category_id ?? null,
        tags: editDetail.tags ?? [],
        text: editDetail.text,
      });
      setSeededForId(editDetail.id);
    }
  }, [editingPrompt, editDetail, seededForId]);

  const categoryNameById = useMemo(() => new Map(categories.map((c) => [c.id, c.name])), [categories]);
  const usedCategoryIds = useMemo(
    () => new Set(prompts.map((p) => p.category_id).filter(Boolean) as string[]),
    [prompts],
  );
  const categoryCounts = useMemo(() => {
    const byId = new Map<string, number>();
    let noCategory = 0;
    for (const p of prompts) {
      if (p.category_id) {
        byId.set(p.category_id, (byId.get(p.category_id) ?? 0) + 1);
      } else {
        noCategory += 1;
      }
    }
    return { byId, noCategory };
  }, [prompts]);

  // Client-side filter: search text + active category
  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return prompts.filter((p) => {
      const matchSearch = !q || p.name.toLowerCase().includes(q) || (p.description ?? "").toLowerCase().includes(q);
      const matchCategory =
        !activeCategory ||
        (activeCategory === NO_CATEGORY_FILTER_ID ? !p.category_id : p.category_id === activeCategory);
      return matchSearch && matchCategory;
    });
  }, [prompts, search, activeCategory]);

  const isSubmitting = isCreating || isUpdating;

  const openCreate = () => {
    setForm(emptyForm);
    setIsCreateOpen(true);
  };

  const openPrompt = (prompt: PromptSummary) => {
    setForm({ ...emptyForm, category_id: prompt.category_id ?? null });
    setEditingPrompt(prompt);
  };

  const openView = (prompt: PromptSummary) => {
    setViewingPrompt(prompt);
  };

  const closeModal = () => {
    setIsCreateOpen(false);
    setEditingPrompt(null);
    setForm(emptyForm);
    setSeededForId(null);
  };

  const performSave = async () => {
    if (!teamId) return;
    try {
      if (editingPrompt) {
        await updatePrompt({
          teamId,
          promptId: editingPrompt.id,
          updatePromptRequest: {
            name: form.name,
            description: form.description || undefined,
            category_id: form.category_id,
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
            category_id: form.category_id,
            tags: form.tags,
            text: form.text,
          },
        }).unwrap();
        showSuccess({ summary: "Prompt created" });
      }
      closeModal();
    } catch (error: unknown) {
      const err = error as { data?: { detail?: string }; message?: string };
      showError({
        summary: "Failed to save prompt",
        detail: err?.data?.detail || err?.message || String(error),
      });
    }
  };

  const handleSubmit = async () => {
    if (!teamId || !form.name.trim() || !form.text.trim()) return;
    // Editing a published prompt updates the live marketplace entry too — warn
    // once before saving (spec: confirmation before saving a change to a
    // published prompt).
    if (editingPrompt?.published) {
      showConfirmationDialog({
        title: t("rework.teams.prompts.editPublishedDialog.title"),
        message: t("rework.teams.prompts.editPublishedDialog.message"),
        confirmButtonLabel: t("rework.teams.prompts.editPublishedDialog.confirm"),
        onConfirm: performSave,
      });
      return;
    }
    await performSave();
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

  const handlePublish = (prompt: PromptSummary) => {
    if (!teamId) return;
    showConfirmationDialog({
      title: t("rework.teams.prompts.publishDialog.title"),
      message: t("rework.teams.prompts.publishDialog.message"),
      confirmButtonLabel: t("rework.teams.prompts.publishDialog.confirm"),
      onConfirm: async () => {
        try {
          await publishPrompt({ teamId, promptId: prompt.id }).unwrap();
          showSuccess({ summary: t("rework.teams.prompts.publishDialog.successToast") });
        } catch (error: unknown) {
          const err = error as { data?: { detail?: string }; message?: string };
          showError({
            summary: t("rework.teams.prompts.publishDialog.errorToast"),
            detail: err?.data?.detail || err?.message || String(error),
          });
        }
      },
    });
  };

  const handleUnpublish = (prompt: PromptSummary) => {
    if (!teamId) return;
    showConfirmationDialog({
      criticalAction: true,
      title: t("rework.teams.prompts.unpublishDialog.title"),
      message: t("rework.teams.prompts.unpublishDialog.message"),
      confirmButtonLabel: t("rework.teams.prompts.unpublishDialog.confirm"),
      onConfirm: async () => {
        try {
          await unpublishPrompt({ teamId, promptId: prompt.id }).unwrap();
          showSuccess({ summary: t("rework.teams.prompts.unpublishDialog.successToast") });
        } catch (error: unknown) {
          const err = error as { data?: { detail?: string }; message?: string };
          showError({
            summary: t("rework.teams.prompts.unpublishDialog.errorToast"),
            detail: err?.data?.detail || err?.message || String(error),
          });
        }
      },
    });
  };

  const handleDuplicateConfirm = async (newName: string) => {
    if (!teamId || !duplicateDetail) return;
    try {
      await duplicatePrompt({
        teamId,
        createPromptRequest: {
          name: newName,
          description: duplicateDetail.description || undefined,
          category_id: duplicateDetail.category_id ?? null,
          tags: duplicateDetail.tags ?? [],
          text: duplicateDetail.text,
        },
      }).unwrap();
      showSuccess({ summary: t("rework.teams.prompts.duplicateDialog.successToast") });
      setDuplicatingPrompt(null);
    } catch (error: unknown) {
      const err = error as { data?: { detail?: string }; message?: string };
      // Keep the dialog open on a name conflict so the user can pick another.
      showError({
        summary: t("rework.teams.prompts.duplicateDialog.errorToast"),
        detail: err?.data?.detail || err?.message || String(error),
      });
    }
  };

  const promptsQueryState = getQueryUiState({ isLoading, isFetching, isUninitialized, isError });

  if (!teamId) {
    return <div className={styles.pageError}>Missing team id in route.</div>;
  }

  if (promptsQueryState === "loading") {
    return (
      <div className={styles.loadingState}>
        <Spinner size={20} />
        {t("rework.teams.prompts.loading")}
      </div>
    );
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
      {prompts.length === 0 ? (
        <PageEmptyState
          icon="edit_note"
          message={t("rework.teams.prompts.noPrompt")}
          action={{ label: t("rework.teams.prompts.firstCreate"), onClick: openCreate }}
        />
      ) : (
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
            <div className={styles.searchRow}>
              <div className={styles.searchBar}>
                <SearchInput
                  value={search}
                  onChange={setSearch}
                  placeholder={t("rework.teams.prompts.searchPlaceholder")}
                  clearAriaLabel={t("rework.teams.prompts.clearSearch")}
                  size="small"
                />
              </div>
              {canManage && (
                <Tooltip text={t("rework.promptCategories.manage.buttonAria")}>
                  <IconButton
                    size="medium"
                    color="on-surface-retreat"
                    variant="icon"
                    icon={{ category: "outlined", type: "tune" }}
                    aria-label={t("rework.promptCategories.manage.buttonAria")}
                    onClick={() => setIsManageCategoriesOpen(true)}
                  />
                </Tooltip>
              )}
            </div>

            {categories.length > 0 && (
              <FilterChips
                options={[
                  {
                    id: NO_CATEGORY_FILTER_ID,
                    label: t("rework.promptCategories.noCategory"),
                    count: categoryCounts.noCategory,
                  },
                  ...categories.map((cat) => ({
                    id: cat.id,
                    label: cat.name,
                    count: categoryCounts.byId.get(cat.id) ?? 0,
                  })),
                ]}
                value={activeCategory}
                onChange={(v) => setActiveCategory(v)}
                allLabel={t("rework.teams.agents.podFilter.all")}
                maxVisible={FILTER_VISIBLE}
                showMoreLabel={(count) => `+${count}`}
                showLessLabel="−"
              />
            )}
          </div>

          {filtered.length === 0 ? (
            <div className={styles.emptyState}>{t("rework.teams.prompts.emptySearch")}</div>
          ) : (
            <div className={styles.promptList}>
              {filtered.map((prompt) => (
                <PromptCard
                  key={prompt.id}
                  prompt={prompt}
                  variant="team"
                  categoryName={(prompt.category_id && categoryNameById.get(prompt.category_id)) || null}
                  canManage={canManage}
                  published={prompt.published}
                  onView={() => openView(prompt)}
                  onEdit={() => openPrompt(prompt)}
                  onDuplicate={() => setDuplicatingPrompt(prompt)}
                  onPublish={() => handlePublish(prompt)}
                  onUnpublish={() => handleUnpublish(prompt)}
                  onDelete={() => handleDelete(prompt)}
                />
              ))}
            </div>
          )}
        </>
      )}

      {/* ── Create / Edit modal ── */}
      <FullPageModal
        isOpen={isCreateOpen || !!editingPrompt}
        onClose={closeModal}
        id="prompt-form-modal"
        background="container"
      >
        <div className={styles.modalCard}>
          <div className={styles.modalHeader}>
            <span className={styles.modalTitle}>
              {editingPrompt ? t("rework.teams.prompts.modalEdit") : t("rework.teams.prompts.modalCreate")}
            </span>
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

            <CategoryPicker
              categories={categories}
              value={form.category_id}
              onChange={(categoryId) => setForm((f) => ({ ...f, category_id: categoryId }))}
            />

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

      <ManageCategoriesDialog
        open={isManageCategoriesOpen}
        teamId={teamId}
        categories={categories}
        usedCategoryIds={usedCategoryIds}
        onClose={() => setIsManageCategoriesOpen(false)}
        onChanged={() => refetchCategories()}
      />

      <PromptViewDialog
        open={!!viewingPrompt}
        teamId={teamId}
        promptId={viewingPrompt?.id ?? null}
        categories={categories}
        onCopied={() => {
          if (viewingPrompt) recordPromptUse({ teamId, promptId: viewingPrompt.id });
        }}
        onClose={() => setViewingPrompt(null)}
      />

      <DuplicatePromptDialog
        open={!!duplicatingPrompt}
        initialName={duplicatingPrompt?.name ?? ""}
        isSubmitting={isDuplicating || (!!duplicatingPrompt && !duplicateDetail)}
        onCancel={() => setDuplicatingPrompt(null)}
        onConfirm={handleDuplicateConfirm}
      />
    </div>
  );
}
