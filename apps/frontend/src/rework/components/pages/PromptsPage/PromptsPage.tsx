// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { sessionQueryArgs } from "../../../../slices/controlPlane/controlPlaneApi";
import { useEffect, useMemo, useRef, useState } from "react";
import { crossSessionRefreshOptions, useRefetchOnWindowFocus } from "@core/hooks/crossSessionRefresh";
import { normalizeApiError } from "@core/errors/normalizeApiError";
import { useParams, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button";
import { Spinner } from "@shared/atoms/Spinner/Spinner";
import TextInput from "@shared/atoms/TextInput/TextInput";
import { PromptEditor } from "@shared/molecules/PromptEditor/PromptEditor";
import PageEmptyState from "@shared/molecules/PageEmptyState/PageEmptyState";
import ServiceNotice from "@shared/molecules/ServiceNotice/ServiceNotice";
import { FullPageModal } from "@shared/molecules/FullPageModal/FullPageModal";
import PageHeader from "@shared/molecules/PageHeader/PageHeader";
import PromptCard from "@shared/organisms/PromptCard/PromptCard";
import { CategoryPicker } from "@shared/molecules/CategoryPicker/CategoryPicker";
import TagInput from "@shared/molecules/TagInput/TagInput";
import FavoritesFilterChip from "@shared/molecules/FavoritesFilterChip/FavoritesFilterChip";
import { usePromptFavoriteToggle } from "@core/hooks/usePromptFavoriteToggle";
import { useSpaceAccess } from "@core/hooks/useSpaceAccess";
import FilterChips from "@shared/molecules/FilterChips/FilterChips";
import ManageCategoriesDialog from "./ManageCategoriesDialog/ManageCategoriesDialog";
import SearchInput from "@shared/molecules/SearchInput/SearchInput";
import { isPromptLogicalNameValid } from "@rework/utils/promptValidation";
import { countUnicodeCodePoints } from "@core/utils/chatInput";
import { filterPrompts, countPromptsByCategory, NO_CATEGORY_FILTER_ID } from "@shared/utils/promptFilter";
import { useConfirmationDialog } from "@shared/molecules/ConfirmationDialog/ConfirmationDialogProvider";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import {
  useMySpacesQuery,
  useMarketplaceProposalSpacesQuery,
  usePromptCatalogQuery,
  useListPromptCategoriesQuery,
  useGetPromptQuery,
  useCreatePromptMutation,
  useUpdatePromptMutation,
  useDeletePromptMutation,
} from "../../../../slices/controlPlane/controlPlaneApiEnhancements";
import type {
  CreatePromptRequest,
  MySpace,
  PromptMetadata,
  PromptSummary,
} from "../../../../slices/controlPlane/controlPlaneOpenApi";
import { agentErrorText } from "../TeamAgentsPage/weaverAgents";
import PromptViewDialog from "./PromptViewDialog/PromptViewDialog";
import DuplicatePromptDialog from "./DuplicatePromptDialog/DuplicatePromptDialog";
import MarketplaceProposalDialog from "../marketplace/MarketplaceProposalDialog";
import styles from "./PromptsPage.module.scss";

const emptyForm: CreatePromptRequest = {
  display_name: "",
  logical_name: "",
  description: "",
  category_id: null,
  tags: [],
  text: "",
};

export default function PromptsPage() {
  const { teamId } = useParams();
  const { t } = useTranslation();
  const context = useMySpacesQuery(undefined, {
    ...crossSessionRefreshOptions(false),
    refetchOnMountOrArgChange: true,
  });
  const publication = useMarketplaceProposalSpacesQuery(sessionQueryArgs({}), {
    ...crossSessionRefreshOptions(false),
    refetchOnMountOrArgChange: true,
  });
  useRefetchOnWindowFocus(context.refetch, false);
  useRefetchOnWindowFocus(publication.refetch, false);
  const publishingSpace = !publication.isError
    ? publication.currentData?.items.find(
        (item) => item.id === teamId || (teamId === "personal" && item.kind === "personal"),
      )
    : undefined;
  const ordinarySpace = !context.isError
    ? context.currentData?.find((item) => (teamId === "personal" ? item.kind === "personal" : item.id === teamId))
    : undefined;
  const space = ordinarySpace ?? publishingSpace;
  if (context.isError) return <ServiceNotice icon="info" title={agentErrorText(context.error, t)} />;
  if (!context.currentData || (!ordinarySpace && !publication.currentData && !publication.isError))
    return <Spinner size={20} />;
  if (!space) return <ServiceNotice icon="lock" title={t("rework.weaverAgents.scopeUnavailable")} centered />;
  return <SpacePrompts key={space.id} space={space} marketplaceSpaceId={publishingSpace?.marketplace_space_ids[0]} />;
}

function SpacePrompts({
  space,
  marketplaceSpaceId,
}: {
  space: Pick<MySpace, "id" | "kind" | "name">;
  marketplaceSpaceId?: string;
}) {
  const canPublish = !!marketplaceSpaceId;
  const { t } = useTranslation();
  const { showError, showSuccess } = useToast();
  const { showConfirmationDialog } = useConfirmationDialog();
  const spaceId = space.id;
  const live = useRef(true);
  useEffect(() => {
    live.current = true;
    return () => {
      live.current = false;
    };
  }, []);
  const [mutationError, setMutationError] = useState<unknown>();
  const writer = useSpaceAccess(spaceId, "write");
  const reader = useSpaceAccess(spaceId, "read");
  const canManage = writer.allowed && reader.allowed;
  // Display keeps the last answer through a recheck; actions stay on canManage.
  const offersManage = writer.offered && reader.offered;
  const canFavorite = reader.offered;
  const accessError = writer.error ?? reader.error;
  const canPublishRef = useRef(canPublish);
  canPublishRef.current = canPublish;
  const canManageRef = useRef(canManage);
  canManageRef.current = canManage;
  const catalog = usePromptCatalogQuery(
    { spaceId },
    { ...crossSessionRefreshOptions(false), refetchOnMountOrArgChange: true },
  );
  const prompts = catalog.currentData?.items ?? [];
  const categoryCatalog = useListPromptCategoriesQuery(
    { spaceId },
    { ...crossSessionRefreshOptions(false), refetchOnMountOrArgChange: true },
  );
  useRefetchOnWindowFocus(catalog.refetch, false);
  useRefetchOnWindowFocus(categoryCatalog.refetch, false);
  const categories = categoryCatalog.currentData?.items ?? [];
  const categoryNameById = useMemo(
    () => new Map(categories.map((category) => [category.id, category.name])),
    [categories],
  );
  const [managingCategories, setManagingCategories] = useState(false);
  const [activeCategory, setActiveCategory] = useState<string | null>(null);
  const categoryCounts = useMemo(() => countPromptsByCategory(prompts), [prompts]);
  useEffect(() => {
    if (
      categoryCatalog.currentData &&
      !categoryCatalog.isFetching &&
      activeCategory &&
      activeCategory !== NO_CATEGORY_FILTER_ID &&
      !categoryCatalog.currentData.items.some((category) => category.id === activeCategory)
    )
      setActiveCategory(null);
  }, [categoryCatalog.currentData, categoryCatalog.isFetching, activeCategory]);
  const toggleFavorite = usePromptFavoriteToggle(spaceId);
  const [favoritesOnly, setFavoritesOnly] = useState(false);
  const [search, setSearch] = useState("");
  const [mode, setMode] = useState<"create" | "edit" | null>(null);
  const [editingId, setEditingId] = useState<string>();
  const [params] = useSearchParams();
  const [viewingId, setViewingId] = useState<string | undefined>(params.get("resource") ?? undefined);
  const [duplicating, setDuplicating] = useState<PromptSummary>();
  const [form, setForm] = useState<CreatePromptRequest>(emptyForm);
  // Compare edits with the values shown at opening, even if the query refreshes.
  const [initialForm, setInitialForm] = useState<CreatePromptRequest>();
  const [nameError, setNameError] = useState<string>();
  // Increments on every dialog change, including reopening the same prompt.
  const dialogVersion = useRef(0);
  const [create, creating] = useCreatePromptMutation();
  const [update, updating] = useUpdatePromptMutation();
  const [remove, removing] = useDeletePromptMutation();
  const [proposing, setProposing] = useState<PromptMetadata>();
  const busy = creating.isLoading || updating.isLoading || removing.isLoading;
  const detail = useGetPromptQuery(
    { spaceId, promptId: editingId ?? "" },
    {
      skip: !editingId,
      refetchOnMountOrArgChange: true,
    },
  );
  const duplicate = useGetPromptQuery(
    { spaceId, promptId: duplicating?.prompt_id ?? "" },
    {
      skip: !duplicating,
      refetchOnMountOrArgChange: true,
    },
  );
  useEffect(() => {
    if (mode !== "edit" || initialForm || detail.isFetching || detail.isError || !detail.currentData) return;
    const saved = detail.currentData;
    const initial = {
      logical_name: saved.logical_name,
      display_name: saved.display_name,
      description: saved.description,
      category_id: saved.category_id,
      tags: saved.tags,
      text: saved.text,
    };
    setForm(initial);
    setInitialForm(initial);
  }, [mode, initialForm, detail.isFetching, detail.isError, detail.currentData]);
  const close = () => {
    dialogVersion.current++;
    setMode(null);
    setEditingId(undefined);
    setDuplicating(undefined);
    setForm(emptyForm);
    setInitialForm(undefined);
    setNameError(undefined);
  };
  const open = (prompt?: PromptSummary) => {
    close();
    setMode(prompt ? "edit" : "create");
    setEditingId(prompt?.prompt_id);
  };
  const notifyError = (error: unknown) => {
    if (live.current) {
      setMutationError(error);
      showError({ summary: agentErrorText(error, t) });
    }
  };
  const saveError = (error: unknown) => {
    if ((error as { data?: { code?: string } })?.data?.code === "prompt_name_conflict") {
      setNameError(t("rework.weaverPrompts.nameConflict"));
    } else if ((error as { data?: { code?: string } })?.data?.code === "prompt_category_conflict") {
      showError({ summary: t("rework.promptCategories.categoryConflict") });
      void categoryCatalog.refetch();
    } else notifyError(error);
  };
  const validName = isPromptLogicalNameValid(form.logical_name);
  const validTitle =
    Boolean(form.display_name.trim()) && countUnicodeCodePoints(form.display_name.normalize("NFC").trim()) <= 255;
  const validDescription = countUnicodeCodePoints(form.description ?? "") <= 500;
  const validText = Boolean(form.text.trim()) && !form.text.includes("\0");
  const validTags =
    (form.tags ?? []).length <= 20 &&
    (form.tags ?? []).every(
      (tag) =>
        Boolean(tag.trim()) &&
        countUnicodeCodePoints(tag.normalize("NFC").trim()) <= 64 &&
        !/[\u0000-\u001f\u007f-\u009f]/u.test(tag),
    );
  const ready =
    Boolean(categoryCatalog.currentData) &&
    !categoryCatalog.isError &&
    (mode === "create" || (!!initialForm && !detail.isFetching && !detail.isError));
  const save = async () => {
    if (!canManage || busy || !ready || !validName || !validTitle || !validDescription || !validText || !validTags)
      return;
    const version = dialogVersion.current;
    try {
      if (mode === "edit" && editingId && initialForm) {
        await update({
          spaceId,
          promptId: editingId,
          updatePromptRequest: {
            display_name: form.display_name === initialForm.display_name ? undefined : form.display_name,
            description: form.description === initialForm.description ? undefined : form.description || null,
            category_id: form.category_id === initialForm.category_id ? undefined : form.category_id,
            tags: JSON.stringify(form.tags) === JSON.stringify(initialForm.tags) ? undefined : form.tags,
            text: form.text === initialForm.text ? undefined : form.text,
          },
        }).unwrap();
      } else if (mode === "create") {
        await create({ spaceId, createPromptRequest: form }).unwrap();
      } else return;
      if (!live.current || dialogVersion.current !== version) return;
      showSuccess({
        summary: t(mode === "edit" ? "rework.teams.prompts.toasts.updated" : "rework.teams.prompts.toasts.created"),
      });
      close();
    } catch (error) {
      if (live.current && dialogVersion.current === version) saveError(error);
    }
  };
  const handleDelete = (prompt: PromptMetadata) => {
    if (!canManage || busy) return;
    const version = dialogVersion.current;
    showConfirmationDialog({
      criticalAction: true,
      title: t("rework.teams.prompts.deleteDialog.title"),
      message: t("rework.teams.prompts.deleteDialog.message", { name: prompt.display_name }),
      confirmButtonLabel: t("rework.teams.prompts.deleteDialog.confirm"),
      onConfirm: async () => {
        if (!live.current || !canManageRef.current) return;
        try {
          await remove({ spaceId, promptId: prompt.prompt_id }).unwrap();
          if (!live.current) return;
          showSuccess({ summary: t("rework.teams.prompts.toasts.deleted") });
          if (dialogVersion.current === version) close();
        } catch (error) {
          notifyError(error);
        }
      },
    });
  };
  const handleDuplicate = async (logicalName: string) => {
    const source = duplicate.currentData;
    if (!canManage || busy || !source || duplicate.isFetching || duplicate.isError) return;
    const version = dialogVersion.current;
    try {
      await create({
        spaceId,
        createPromptRequest: {
          logical_name: logicalName,
          display_name: source.display_name,
          description: source.description,
          category_id: source.category_id,
          tags: source.tags,
          text: source.text,
        },
      }).unwrap();
      if (!live.current || dialogVersion.current !== version) return;
      showSuccess({ summary: t("rework.teams.prompts.duplicateDialog.successToast") });
      close();
    } catch (error) {
      if (live.current && dialogVersion.current === version) saveError(error);
    }
  };
  const filtered = filterPrompts(prompts, {
    search,
    categoryId: activeCategory,
    favoritesOnly: canFavorite && favoritesOnly,
  });
  // A known refusal invalidates the entire displayed source, including an
  // already-open form. A fresh page admission is required before reusing data.
  const refused = [
    mutationError,
    ...[catalog, categoryCatalog, detail, duplicate].map((query) => (query.isError ? query.error : undefined)),
  ]
    .map(normalizeApiError)
    .some((error) => error.status === 403 || error.status === 404 || error.code === "space_pending_deletion");
  if (refused || (reader.settled && !reader.allowed && !canPublish)) {
    canManageRef.current = false;
    canPublishRef.current = false;
    return (
      <ServiceNotice
        icon="lock"
        title={t("rework.weaverAgents.scopeUnavailable")}
        action={
          <Button color="primary" variant="text" size="small" onClick={() => window.location.reload()}>
            {t("rework.weaverPrompts.retry")}
          </Button>
        }
      />
    );
  }
  return (
    <div className={styles.pageContainer}>
      <PageHeader
        title={t(space.kind === "personal" ? "rework.teams.prompts.titlePersonal" : "rework.teams.prompts.title")}
        subtitle={space.name}
        actions={
          <>
            {offersManage && (
              <Button
                color="primary"
                variant="filled"
                size="small"
                icon={{ category: "outlined", type: "add" }}
                onClick={() => open()}
              >
                {t("rework.teams.prompts.create")}
              </Button>
            )}
            <div className={styles.searchBar}>
              <SearchInput
                value={search}
                onChange={setSearch}
                placeholder={t("rework.teams.prompts.searchPlaceholder")}
                clearAriaLabel={t("rework.teams.prompts.clearSearch")}
                size="xs"
              />
            </div>
            <Button
              color="on-surface"
              variant="text"
              size="small"
              disabled={
                !offersManage ||
                !categoryCatalog.currentData ||
                categoryCatalog.isFetching ||
                categoryCatalog.isError ||
                !catalog.currentData ||
                catalog.isError
              }
              onClick={() => setManagingCategories(true)}
              icon={{ category: "outlined", type: "tune" }}
            >
              {t("rework.promptCategories.manage.buttonAria")}
            </Button>
          </>
        }
      />
      {canFavorite && (
        <FavoritesFilterChip
          label={t("rework.teams.prompts.favorite.filter")}
          active={favoritesOnly}
          onToggle={() => setFavoritesOnly((value) => !value)}
        />
      )}
      {categoryCatalog.currentData && !categoryCatalog.isError && catalog.currentData && !catalog.isError && (
        <FilterChips
          aria-label={t("rework.promptCategories.pickerTitle")}
          options={[
            {
              id: NO_CATEGORY_FILTER_ID,
              label: t("rework.promptCategories.noCategory"),
              count: categoryCounts.get(null) ?? 0,
            },
            ...categories.map((category) => ({
              id: category.id,
              label: category.name,
              count: categoryCounts.get(category.id) ?? 0,
            })),
          ]}
          value={activeCategory}
          onChange={setActiveCategory}
          allLabel={t("rework.teams.agents.podFilter.all")}
          maxVisible={6}
        />
      )}
      {!canPublish && accessError != null && <ServiceNotice icon="info" title={agentErrorText(accessError, t)} />}
      {catalog.isError || categoryCatalog.isError ? (
        <ServiceNotice
          icon="cloud_off"
          title={t(categoryCatalog.isError ? "rework.promptCategories.loadError" : "rework.weaverPrompts.catalogError")}
          description={agentErrorText(categoryCatalog.isError ? categoryCatalog.error : catalog.error, t)}
          action={
            <Button
              color="primary"
              variant="text"
              size="small"
              onClick={() => {
                void catalog.refetch();
                void categoryCatalog.refetch();
              }}
            >
              {t("rework.weaverPrompts.retry")}
            </Button>
          }
        />
      ) : !catalog.currentData || !categoryCatalog.currentData ? (
        <div className={styles.loadingState}>
          <Spinner size={20} />
          {t("rework.teams.prompts.loading")}
        </div>
      ) : prompts.length === 0 ? (
        <PageEmptyState
          icon="chat"
          message={t("rework.teams.prompts.noPrompt")}
          action={offersManage ? { label: t("rework.teams.prompts.firstCreate"), onClick: () => open() } : undefined}
        />
      ) : filtered.length === 0 ? (
        <div className={styles.emptyState}>{t("rework.teams.prompts.emptySearch")}</div>
      ) : (
        <div className={styles.promptList}>
          {filtered.map((prompt) => (
            <PromptCard
              key={prompt.prompt_id}
              prompt={prompt}
              categoryName={prompt.category_id ? categoryNameById.get(prompt.category_id) : null}
              canManage={offersManage && !busy}
              publishable={canPublish && !busy}
              onPropose={() => setProposing(prompt)}
              onToggleFavorite={canFavorite ? () => void toggleFavorite(prompt) : undefined}
              onView={() => setViewingId(prompt.prompt_id)}
              onEdit={() => open(prompt)}
              onDuplicate={() => {
                close();
                setDuplicating(prompt);
              }}
              onDelete={() => handleDelete(prompt)}
            />
          ))}
        </div>
      )}
      {proposing && (
        <MarketplaceProposalDialog
          sourceName={proposing.display_name}
          source={{
            kind: "prompt",
            source_space_id: spaceId,
            source_resource_id: proposing.prompt_id,
            expected_revision: proposing.updated_at,
          }}
          onClose={() => setProposing(undefined)}
        />
      )}
      <FullPageModal isOpen={mode !== null} onClose={close} id="prompt-form-modal" background="container">
        <div className={styles.modalCard}>
          <div className={styles.modalHeader}>
            <span id="prompt-form-modal-title" className={styles.modalTitle}>
              {t(mode === "edit" ? "rework.teams.prompts.modalEdit" : "rework.teams.prompts.modalCreate")}
            </span>
          </div>
          {mode === "edit" && detail.isError ? (
            <ServiceNotice icon="info" title={agentErrorText(detail.error, t)} />
          ) : categoryCatalog.isError ? (
            <ServiceNotice icon="cloud_off" title={t("rework.promptCategories.loadError")} />
          ) : !ready ? (
            <Spinner size={20} />
          ) : (
            <div className={styles.modalContent}>
              <TextInput
                label={t("rework.teams.prompts.form.name")}
                required
                explanation={`${countUnicodeCodePoints(form.display_name.normalize("NFC").trim())}/255`}
                value={form.display_name}
                disabled={!offersManage || busy}
                error={!validTitle && form.display_name ? t("rework.weaverPrompts.titleLimit") : undefined}
                onChange={(e) => setForm((f) => ({ ...f, display_name: e.target.value }))}
              />
              <TextInput
                label={t("rework.weaverPrompts.logicalName")}
                explanation={t(
                  mode === "edit" ? "rework.weaverPrompts.immutableName" : "rework.weaverPrompts.nameHelp",
                )}
                required
                prefix="/"
                readOnly={mode === "edit"}
                disabled={!offersManage || busy}
                value={form.logical_name}
                maxLength={64}
                error={nameError ?? (form.logical_name && !validName ? t("rework.weaverPrompts.nameHelp") : undefined)}
                onChange={(e) => {
                  setNameError(undefined);
                  setForm((f) => ({ ...f, logical_name: e.target.value }));
                }}
              />
              <TextInput
                label={t("rework.teams.prompts.form.description")}
                explanation={`${countUnicodeCodePoints(form.description ?? "")}/500`}
                value={form.description ?? ""}
                disabled={!offersManage || busy}
                error={!validDescription ? t("rework.weaverPrompts.descriptionLimit") : undefined}
                onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
              />
              <CategoryPicker
                categories={categories}
                value={form.category_id}
                disabled={!offersManage || busy}
                onChange={(category_id) => setForm((current) => ({ ...current, category_id }))}
              />
              <TagInput
                label={t("rework.weaverPrompts.tags")}
                tags={form.tags ?? []}
                disabled={!offersManage || busy}
                placeholder={t("rework.teams.prompts.form.tagsPlaceholder")}
                error={!validTags ? t("rework.weaverPrompts.tagsLimit") : undefined}
                removeTagAriaLabel={(tag) => t("rework.teams.prompts.form.removeTagAria", { tag })}
                onChange={(tags) => setForm((current) => ({ ...current, tags }))}
              />
              <PromptEditor
                label={t("rework.teams.prompts.form.text")}
                required
                error={form.text && !validText ? t("rework.weaverPrompts.textRequired") : undefined}
                value={form.text}
                disabled={!offersManage || busy}
                onChange={(text) => setForm((f) => ({ ...f, text }))}
              />
            </div>
          )}
          <div className={styles.modalFooter}>
            {mode === "edit" && detail.currentData && offersManage && (
              <Button
                color="error"
                variant="text"
                size="medium"
                disabled={busy}
                onClick={() => handleDelete(detail.currentData!)}
              >
                {t("rework.delete")}
              </Button>
            )}
            <div className={styles.modalFooterActions}>
              <Button color="on-surface" variant="text" size="medium" onClick={close}>
                {t("rework.cancel")}
              </Button>
              <Button
                color="primary"
                variant="filled"
                size="medium"
                onClick={() => void save()}
                disabled={
                  !canManage ||
                  busy ||
                  !ready ||
                  !validName ||
                  !validTitle ||
                  !validDescription ||
                  !validText ||
                  !validTags
                }
              >
                {t(mode === "edit" ? "rework.save" : "rework.create")}
              </Button>
            </div>
          </div>
        </div>
      </FullPageModal>
      {managingCategories && offersManage && categoryCatalog.currentData && (
        <ManageCategoriesDialog
          open
          spaceId={spaceId}
          categories={categories}
          usedCategoryIds={new Set([...categoryCounts.keys()].filter((id): id is string => id !== null))}
          onClose={() => setManagingCategories(false)}
          onChanged={() => {
            void categoryCatalog.refetch();
            void catalog.refetch();
          }}
        />
      )}
      <PromptViewDialog
        key={viewingId}
        open={Boolean(viewingId)}
        spaceId={spaceId}
        promptId={viewingId}
        categories={categories}
        onClose={() => setViewingId(undefined)}
      />
      <DuplicatePromptDialog
        open={Boolean(duplicating)}
        initialName=""
        error={nameError ?? (duplicate.isError ? agentErrorText(duplicate.error, t) : undefined)}
        onNameChange={() => setNameError(undefined)}
        isSubmitting={busy || !offersManage || duplicate.isFetching || duplicate.isError || !duplicate.currentData}
        onCancel={close}
        onConfirm={handleDuplicate}
      />
    </div>
  );
}
