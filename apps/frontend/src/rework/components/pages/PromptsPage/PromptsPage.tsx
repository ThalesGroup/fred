// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
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
import SearchInput from "@shared/molecules/SearchInput/SearchInput";
import { isPromptLogicalNameValid } from "@rework/utils/promptValidation";
import { countUnicodeCodePoints } from "@core/utils/chatInput";
import { filterPrompts } from "@shared/utils/promptFilter";
import { useConfirmationDialog } from "@shared/molecules/ConfirmationDialog/ConfirmationDialogProvider";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import {
  useMySpacesQuery,
  useAuthorizeSpaceMutation,
  usePromptCatalogQuery,
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
import { agentErrorText, resolveAgentSpace } from "../TeamAgentsPage/weaverAgents";
import PromptViewDialog from "./PromptViewDialog/PromptViewDialog";
import DuplicatePromptDialog from "./DuplicatePromptDialog/DuplicatePromptDialog";
import styles from "./PromptsPage.module.scss";

const emptyForm: CreatePromptRequest = { display_name: "", logical_name: "", description: "", text: "" };

export default function PromptsPage() {
  const { teamId } = useParams();
  const { t } = useTranslation();
  const context = useMySpacesQuery(undefined, { refetchOnMountOrArgChange: true });
  const space = resolveAgentSpace(context.currentData, teamId);
  if (context.isError) return <ServiceNotice icon="info" title={agentErrorText(context.error, t)} />;
  if (!context.currentData) return <Spinner size={20} />;
  if (!space) return <ServiceNotice icon="lock" title={t("rework.weaverAgents.scopeUnavailable")} centered />;
  return <SpacePrompts key={space.id} space={space} contextStamp={context.fulfilledTimeStamp} />;
}

function SpacePrompts({ space, contextStamp }: { space: MySpace; contextStamp?: number }) {
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
  const [authorize] = useAuthorizeSpaceMutation();
  const [access, setAccess] = useState<{ stamp?: number; allowed: boolean; error?: unknown }>();
  useEffect(() => {
    let current = true;
    const request = authorize({ spaceCheck: { space_id: spaceId, permission: "write" } });
    void request.unwrap().then(
      ({ allowed }) => {
        if (current) setAccess({ stamp: contextStamp, allowed });
      },
      (error: unknown) => {
        if (current) setAccess({ stamp: contextStamp, allowed: false, error });
      },
    );
    return () => {
      current = false;
      request.abort();
    };
  }, [authorize, spaceId, contextStamp]);
  const canManage = access?.stamp === contextStamp && access?.allowed === true;
  const canManageRef = useRef(canManage);
  canManageRef.current = canManage;
  const catalog = usePromptCatalogQuery({ spaceId }, { refetchOnMountOrArgChange: true });
  const prompts = catalog.currentData?.items ?? [];
  const [search, setSearch] = useState("");
  const [mode, setMode] = useState<"create" | "edit" | null>(null);
  const [editingId, setEditingId] = useState<string>();
  const [viewingId, setViewingId] = useState<string>();
  const [duplicating, setDuplicating] = useState<PromptSummary>();
  const [form, setForm] = useState<CreatePromptRequest>(emptyForm);
  const [seeded, setSeeded] = useState(false);
  const [nameError, setNameError] = useState<string>();
  // Increments on every dialog change, including reopening the same prompt.
  const dialogVersion = useRef(0);
  const [create, creating] = useCreatePromptMutation();
  const [update, updating] = useUpdatePromptMutation();
  const [remove, removing] = useDeletePromptMutation();
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
    if (mode !== "edit" || seeded || detail.isFetching || detail.isError || !detail.currentData) return;
    const saved = detail.currentData;
    setForm({
      logical_name: saved.logical_name,
      display_name: saved.display_name,
      description: saved.description,
      text: saved.text,
    });
    setSeeded(true);
  }, [mode, seeded, detail.isFetching, detail.isError, detail.currentData]);
  const close = () => {
    dialogVersion.current++;
    setMode(null);
    setEditingId(undefined);
    setDuplicating(undefined);
    setForm(emptyForm);
    setSeeded(false);
    setNameError(undefined);
  };
  const open = (prompt?: PromptSummary) => {
    close();
    setMode(prompt ? "edit" : "create");
    setEditingId(prompt?.prompt_id);
  };
  const notifyError = (error: unknown) => {
    if (live.current) showError({ summary: agentErrorText(error, t) });
  };
  const saveError = (error: unknown) => {
    if ((error as { data?: { code?: string } })?.data?.code === "prompt_name_conflict") {
      setNameError(t("rework.weaverPrompts.nameConflict"));
    } else notifyError(error);
  };
  const validName = isPromptLogicalNameValid(form.logical_name);
  const validTitle =
    Boolean(form.display_name.trim()) && countUnicodeCodePoints(form.display_name.normalize("NFC").trim()) <= 255;
  const validDescription = countUnicodeCodePoints(form.description ?? "") <= 500;
  const ready = mode === "create" || (seeded && !detail.isFetching && !detail.isError);
  const save = async () => {
    if (!canManage || busy || !ready || !validName || !validTitle || !validDescription) return;
    const version = dialogVersion.current;
    try {
      if (mode === "edit" && editingId && detail.currentData) {
        await update({
          spaceId,
          promptId: editingId,
          updatePromptRequest: {
            display_name: form.display_name === detail.currentData.display_name ? undefined : form.display_name,
            description: form.description === detail.currentData.description ? undefined : form.description || null,
            text: form.text === detail.currentData.text ? undefined : form.text,
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
  const filtered = filterPrompts(prompts, { search, categoryId: null });
  const unavailable = t("rework.weaverAgents.notConnected");
  return (
    <div className={styles.pageContainer}>
      <PageHeader
        title={t(space.kind === "personal" ? "rework.teams.prompts.titlePersonal" : "rework.teams.prompts.title")}
        actions={
          <>
            {canManage && (
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
              disabled
              title={unavailable}
              icon={{ category: "outlined", type: "tune" }}
            >
              {t("rework.promptCategories.manage.buttonAria")}
            </Button>
          </>
        }
      />
      <ServiceNotice icon="info" title={t("rework.weaverPrompts.deferred")} />
      {access?.error != null && <ServiceNotice icon="info" title={agentErrorText(access.error, t)} />}
      {catalog.isError ? (
        <ServiceNotice
          icon="cloud_off"
          title={t("rework.weaverPrompts.catalogError")}
          description={agentErrorText(catalog.error, t)}
          action={
            <Button color="primary" variant="text" size="small" onClick={() => void catalog.refetch()}>
              {t("rework.weaverPrompts.retry")}
            </Button>
          }
        />
      ) : !catalog.currentData ? (
        <div className={styles.loadingState}>
          <Spinner size={20} />
          {t("rework.teams.prompts.loading")}
        </div>
      ) : prompts.length === 0 ? (
        <PageEmptyState
          icon="edit_note"
          message={t("rework.teams.prompts.noPrompt")}
          action={canManage ? { label: t("rework.teams.prompts.firstCreate"), onClick: () => open() } : undefined}
        />
      ) : filtered.length === 0 ? (
        <div className={styles.emptyState}>{t("rework.teams.prompts.emptySearch")}</div>
      ) : (
        <div className={styles.promptList}>
          {filtered.map((prompt) => (
            <PromptCard
              key={prompt.prompt_id}
              prompt={prompt}
              canManage={canManage && !busy}
              publishable={false}
              unavailableReason={unavailable}
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
      <FullPageModal isOpen={mode !== null} onClose={close} id="prompt-form-modal" background="container">
        <div className={styles.modalCard}>
          <div className={styles.modalHeader}>
            <span id="prompt-form-modal-title" className={styles.modalTitle}>
              {t(mode === "edit" ? "rework.teams.prompts.modalEdit" : "rework.teams.prompts.modalCreate")}
            </span>
          </div>
          {mode === "edit" && detail.isError ? (
            <ServiceNotice icon="info" title={agentErrorText(detail.error, t)} />
          ) : !ready ? (
            <Spinner size={20} />
          ) : (
            <div className={styles.modalContent}>
              <TextInput
                label={t("rework.teams.prompts.form.name")}
                required
                value={form.display_name}
                disabled={!canManage || busy}
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
                disabled={!canManage || busy}
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
                value={form.description ?? ""}
                disabled={!canManage || busy}
                error={!validDescription ? t("rework.weaverPrompts.descriptionLimit") : undefined}
                onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
              />
              <PromptEditor
                label={t("rework.teams.prompts.form.text")}
                value={form.text}
                disabled={!canManage || busy}
                onChange={(text) => setForm((f) => ({ ...f, text }))}
              />
            </div>
          )}
          <div className={styles.modalFooter}>
            {mode === "edit" && detail.currentData && canManage && (
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
                onClick={save}
                disabled={!canManage || busy || !ready || !validName || !validTitle || !validDescription}
              >
                {t(mode === "edit" ? "rework.save" : "rework.create")}
              </Button>
            </div>
          </div>
        </div>
      </FullPageModal>
      <PromptViewDialog
        key={viewingId}
        open={Boolean(viewingId)}
        spaceId={spaceId}
        promptId={viewingId}
        onClose={() => setViewingId(undefined)}
      />
      <DuplicatePromptDialog
        open={Boolean(duplicating)}
        initialName=""
        error={nameError ?? (duplicate.isError ? agentErrorText(duplicate.error, t) : undefined)}
        onNameChange={() => setNameError(undefined)}
        isSubmitting={busy || !canManage || duplicate.isFetching || duplicate.isError || !duplicate.currentData}
        onCancel={close}
        onConfirm={handleDuplicate}
      />
    </div>
  );
}
