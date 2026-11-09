// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useParams, useSearchParams } from "react-router-dom";
import Button from "@shared/atoms/Button/Button";
import { Spinner } from "@shared/atoms/Spinner/Spinner";
import AgentCard from "@shared/organisms/AgentCard/AgentCard";
import SearchInput from "@shared/molecules/SearchInput/SearchInput";
import Select from "@shared/molecules/Select/Select";
import PageHeader from "@shared/molecules/PageHeader/PageHeader";
import ServiceNotice from "@shared/molecules/ServiceNotice/ServiceNotice";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import { useConfirmationDialog } from "@shared/molecules/ConfirmationDialog/ConfirmationDialogProvider";
import { useFrontendProperties } from "../../../../hooks/useFrontendProperties";
import { useCurrentUserPreference } from "../../../../app/userPreferences";
import {
  useMySpacesQuery,
  useListAgentInstancesQuery,
  useSpaceAgentTemplatesQuery,
  useGetAgentInstanceQuery,
  useCreateAgentInstanceMutation,
  useUpdateAgentInstanceMutation,
  useDeleteAgentInstanceMutation,
  useUploadPowerpointTemplateMutation,
  useResolvePowerpointTemplateQuery,
} from "../../../../slices/controlPlane/controlPlaneApiEnhancements";
import type { ManagedAgentInstanceSummary, MySpace } from "../../../../slices/controlPlane/controlPlaneOpenApi";
import AgentFormModal, { type AgentFormPayload } from "./AgentFormModal/AgentFormModal";
import TeamAgentEmptyState from "./TeamAgentEmptyState/TeamAgentEmptyState";
import { filterAgents } from "./agentFilter";
import { sortAgents, storeAgentSort, type AgentSortValue } from "./agentSort";
import { isAgentNameConflict, normalizeAgentName, takenAgentNames } from "./agentNames";
import { useMediaQuery } from "@core/hooks/useMediaQuery";
import { useSpaceAccess } from "@core/hooks/useSpaceAccess";
import { agentErrorText, createAgentRequest, resolveAgentSpace, updateAgentRequest } from "./weaverAgents";
import MarketplaceProposalDialog from "../marketplace/MarketplaceProposalDialog";
import styles from "./TeamAgentsPage.module.css";

export default function TeamAgentsPage() {
  const { teamId } = useParams();
  const { t } = useTranslation();
  const context = useMySpacesQuery(undefined, { refetchOnMountOrArgChange: true });
  const space = resolveAgentSpace(context.currentData, teamId);
  if (context.isError) return <AgentNotice error={context.error} />;
  if (!context.currentData) return <Spinner size={20} />;
  if (!space) return <ServiceNotice icon="lock" title={t("rework.weaverAgents.scopeUnavailable")} centered />;
  // A new scope cannot inherit the previous scope's list, dialog or write decision.
  return <SpaceAgents key={space.id} space={space} />;
}

function AgentNotice({ error }: { error: unknown }) {
  const { t } = useTranslation();
  return <ServiceNotice icon="info" title={agentErrorText(error, t)} />;
}

function SpaceAgents({ space }: { space: MySpace }) {
  const { t } = useTranslation();
  const { showError, showSuccess } = useToast();
  const { showConfirmationDialog } = useConfirmationDialog();
  const { agentsNicknamePlural, agentsNicknameSingular } = useFrontendProperties();
  // Search ready on arrival with a mouse or trackpad; never on touch, where it would pop the keyboard.
  const finePointer = useMediaQuery("(pointer: fine)");
  const spaceId = space.id;
  const access = useSpaceAccess(spaceId, "write");
  const { allowed: canManageAgents, offered: offersManagement } = access;
  const live = useRef(true);
  useEffect(() => {
    live.current = true;
    return () => {
      live.current = false;
    };
  }, []);
  const [preparationPolling, setPreparationPolling] = useState(0);
  const instances = useListAgentInstancesQuery(
    { spaceId },
    { refetchOnMountOrArgChange: true, pollingInterval: preparationPolling },
  );
  useEffect(() => {
    setPreparationPolling(
      instances.currentData?.items.some((instance) => instance.preparation_state === "pending") ? 5000 : 0,
    );
  }, [instances.currentData]);
  const catalog = useSpaceAgentTemplatesQuery(
    { spaceId },
    { skip: !offersManagement, refetchOnMountOrArgChange: true },
  );
  const managedInstances = instances.isError ? [] : (instances.currentData?.items ?? []);
  const templates = catalog.isError ? [] : (catalog.data ?? []);
  const [isEnrollOpen, setIsEnrollOpen] = useState(false);
  const [params] = useSearchParams();
  const [editingId, setEditingId] = useState<string | undefined>(params.get("resource") ?? undefined);
  const [proposing, setProposing] = useState<ManagedAgentInstanceSummary>();
  const [refusedNames, setRefusedNames] = useState<ReadonlySet<string>>(new Set());
  const [search, setSearch] = useState("");
  const sort = useCurrentUserPreference("agent_sort", "name") as AgentSortValue;
  const [create, creating] = useCreateAgentInstanceMutation();
  const [update, updating] = useUpdateAgentInstanceMutation();
  const [remove, removing] = useDeleteAgentInstanceMutation();
  const detail = useGetAgentInstanceQuery(
    { spaceId, agentInstanceId: editingId ?? "" },
    {
      skip: !editingId,
      refetchOnMountOrArgChange: true,
    },
  );
  const editing = !detail.isError && !detail.isFetching ? detail.currentData : undefined;
  const [uploadTemplate, uploadingTemplate] = useUploadPowerpointTemplateMutation();
  const [savingTemplate, setSavingTemplate] = useState(false);
  const templateFile = useResolvePowerpointTemplateQuery(
    { spaceId, agentInstanceId: editingId ?? "" },
    { skip: !editingId, refetchOnMountOrArgChange: true },
  );
  const busy =
    creating.isLoading || updating.isLoading || removing.isLoading || uploadingTemplate.isLoading || savingTemplate;
  const unavailable = t("rework.weaverAgents.notConnected");
  const notifyError = (error: unknown) => {
    if (!live.current) return;
    showError({ summary: agentErrorText(error, t) });
  };
  const handleSave = async (payload: AgentFormPayload) => {
    if (!canManageAgents || busy) return;
    if (
      Object.entries(payload.capabilityAssetFiles).some(
        ([id, slots]) => id !== "ppt_builder" && Object.keys(slots).length > 0,
      )
    ) {
      showError({ summary: t("rework.weaverAgents.templateUploadsUnavailable") });
      return;
    }
    setSavingTemplate(true);
    try {
      const file = payload.capabilityAssetFiles.ppt_builder?.template;
      const removeTemplate = payload.capabilityConfigValues.ppt_builder?.remove_template === true;
      const own = templateFile.currentData?.source === "agent" ? templateFile.currentData.file : null;
      if (editing && (file || removeTemplate) && !templateFile.currentData) {
        throw new Error("Saved PowerPoint attachment is unavailable");
      }
      const staged = file
        ? await uploadTemplate({
            spaceId,
            agentInstanceId: editing?.agent_instance_id ?? crypto.randomUUID(),
            templateId: editing ? undefined : payload.templateId,
            expectedFileId: own?.id,
            "Idempotency-Key": crypto.randomUUID(),
            fileUpload: { file },
          }).unwrap()
        : undefined;
      const powerpoint =
        staged || removeTemplate ? { file_id: staged?.id ?? null, expected_file_id: own?.id ?? null } : undefined;
      if (editing) {
        await update({
          spaceId,
          agentInstanceId: editing.agent_instance_id,
          updateAgentInstanceRequest: { ...updateAgentRequest(payload, editing), powerpoint },
        }).unwrap();
      } else if (isEnrollOpen) {
        await create({ spaceId, createAgentInstanceRequest: { ...createAgentRequest(payload), powerpoint } }).unwrap();
      } else return;
      if (!live.current) return;
      // As on swift: tag invalidation alone has left the list stale after a save.
      void instances.refetch();
      showSuccess({
        summary: t(editing ? "rework.agentCard.updateSuccess" : "rework.agentCard.createSuccess", {
          agent: agentsNicknameSingular,
        }),
      });
      setEditingId(undefined);
      setIsEnrollOpen(false);
    } catch (error) {
      if (live.current && isAgentNameConflict(error))
        setRefusedNames((names) => new Set([...names, normalizeAgentName(payload.displayName)]));
      notifyError(error);
    } finally {
      setSavingTemplate(false);
    }
  };
  const handleToggle = async (instance: ManagedAgentInstanceSummary) => {
    if (!canManageAgents || busy) return;
    const status = instance.status === "enabled" ? "disabled" : "enabled";
    try {
      await update({
        spaceId,
        agentInstanceId: instance.agent_instance_id,
        updateAgentInstanceRequest: { status },
      }).unwrap();
      if (!live.current) return;
      void instances.refetch();
      showSuccess({
        summary: t("rework.agentCard.toggleSuccess", {
          agent: agentsNicknameSingular,
          status: t(status === "enabled" ? "rework.agentCard.statusEnabled" : "rework.agentCard.statusDisabled"),
        }),
      });
    } catch (error) {
      notifyError(error);
    }
  };
  const handleDelete = (instance: ManagedAgentInstanceSummary) => {
    if (!canManageAgents || busy) return;
    showConfirmationDialog({
      criticalAction: true,
      title: t("rework.agentCard.deleteDialog.title"),
      message: t("rework.agentCard.deleteDialog.message", { name: instance.display_name }),
      confirmButtonLabel: t("rework.agentCard.deleteDialog.confirm"),
      cancelButtonLabel: t("rework.agentCard.deleteDialog.cancel"),
      onConfirm: async () => {
        if (!live.current) return;
        try {
          await remove({ spaceId, agentInstanceId: instance.agent_instance_id }).unwrap();
          if (!live.current) return;
          void instances.refetch();
          setEditingId(undefined);
          showSuccess({ summary: t("rework.agentCard.deleteSuccess", { agent: agentsNicknameSingular }) });
        } catch (error) {
          notifyError(error);
        }
      },
    });
  };
  const canCreate = offersManagement && !catalog.isFetching && !catalog.isError && templates.length > 0;
  const disabledReason =
    !catalog.isFetching && !catalog.isError && catalog.currentData?.length === 0
      ? t("rework.teams.formAgent.noTemplates")
      : undefined;
  const searched = sortAgents(filterAgents(managedInstances, search), sort);
  const names = new Set([...takenAgentNames(managedInstances, editingId), ...refusedNames]);
  return (
    <div className={styles.teamAgentContainer}>
      <PageHeader
        title={t(space.kind === "personal" ? "rework.teams.agents.titlePersonal" : "rework.teams.agents.title")}
        actions={
          <>
            {offersManagement && (
              <Button
                color="primary"
                variant="filled"
                size="small"
                icon={{ category: "outlined", type: "add" }}
                disabled={!canCreate}
                disabledReason={disabledReason}
                onClick={() => setIsEnrollOpen(true)}
              >
                {t("rework.teams.agents.create", { agentsNicknameSingular })}
              </Button>
            )}
            <div className={styles.searchBar}>
              <SearchInput
                value={search}
                onChange={setSearch}
                autoFocus={finePointer}
                placeholder={t("rework.teams.agents.searchPlaceholder", { agentsNicknamePlural })}
                clearAriaLabel={t("rework.teams.agents.clearSearch")}
                size="xs"
              />
            </div>
            <div className={styles.sortSelect}>
              <Select<AgentSortValue>
                size="xs"
                compact
                value={sort}
                onChange={storeAgentSort}
                ariaLabel={t("rework.teams.agents.sortLabel")}
                options={[
                  { value: "name", key: "name", label: t("rework.teams.agents.sort.name") },
                  { value: "created_at:desc", key: "created", label: t("rework.teams.agents.sort.created") },
                  { value: "updated_at:desc", key: "updated", label: t("rework.teams.agents.sort.updated") },
                ]}
              />
            </div>
          </>
        }
      />
      {access.error != null && <AgentNotice error={access.error} />}
      {offersManagement && catalog.isError && <AgentNotice error={catalog.error} />}
      {instances.isError ? (
        <AgentNotice error={instances.error} />
      ) : !instances.currentData ? (
        <div className={styles.loadingState}>
          <Spinner size={20} />
          {t("rework.teams.agents.loading", { agentsNicknamePlural })}
        </div>
      ) : managedInstances.length === 0 ? (
        <TeamAgentEmptyState
          canManageAgents={offersManagement}
          templatesUnavailable={!canCreate}
          disabledReason={disabledReason}
          onCreateAgent={() => setIsEnrollOpen(true)}
        />
      ) : searched.length === 0 ? (
        <div className={styles.emptySearch}>{t("rework.teams.agents.emptySearch")}</div>
      ) : (
        <div className={styles.agentListScroll}>
          <div className={styles.agentList}>
            {searched.map((instance) => (
              <AgentCard
                key={instance.agent_instance_id}
                instance={instance}
                templateDisplayName={
                  templates.find((item) => item.template_id === instance.template_id)?.display_name ??
                  instance.source_agent_id
                }
                runtimeId={instance.source_runtime_id}
                teamId={spaceId}
                chatAvailable
                canManageAgents={offersManagement}
                managementBusy={busy}
                unavailableActionsReason={unavailable}
                onEdit={() => {
                  setIsEnrollOpen(false);
                  setEditingId(instance.agent_instance_id);
                }}
                onToggleEnabled={() => void handleToggle(instance)}
                onDelete={() => handleDelete(instance)}
                onDuplicate={() => {}}
                onCopyTo={() => {}}
                onPropose={canManageAgents && !busy ? () => setProposing(instance) : undefined}
              />
            ))}
          </div>
        </div>
      )}
      {proposing && canManageAgents && (
        <MarketplaceProposalDialog
          source={{
            kind: "agent",
            source_space_id: spaceId,
            source_resource_id: proposing.agent_instance_id,
            expected_revision: String(proposing.configuration_revision),
          }}
          onClose={() => setProposing(undefined)}
        />
      )}
      {editingId && offersManagement && detail.isFetching && <Spinner size={20} />}
      {editingId && offersManagement && detail.isError && <AgentNotice error={detail.error} />}
      {(isEnrollOpen || editing) && (
        <AgentFormModal
          key={editing?.agent_instance_id ?? "create"}
          isOpen
          isSubmitting={busy || !offersManagement}
          mode={editing ? "edit" : "create"}
          teamName={space.name}
          teamId={spaceId}
          templates={templates}
          editInstance={editing}
          takenNames={names}
          onClose={() => {
            setIsEnrollOpen(false);
            setEditingId(undefined);
          }}
          onSubmit={handleSave}
          onDelete={editing && offersManagement ? () => handleDelete(editing) : undefined}
        />
      )}
    </div>
  );
}
