// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";
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
  useAuthorizeSpaceMutation,
  useListAgentInstancesQuery,
  useSpaceAgentTemplatesQuery,
  useGetAgentInstanceQuery,
  useCreateAgentInstanceMutation,
  useUpdateAgentInstanceMutation,
  useDeleteAgentInstanceMutation,
} from "../../../../slices/controlPlane/controlPlaneApiEnhancements";
import type { ManagedAgentInstanceSummary, MySpace } from "../../../../slices/controlPlane/controlPlaneOpenApi";
import AgentFormModal, { type AgentFormPayload } from "./AgentFormModal/AgentFormModal";
import TeamAgentEmptyState from "./TeamAgentEmptyState/TeamAgentEmptyState";
import { filterAgents } from "./agentFilter";
import { sortAgents, storeAgentSort, type AgentSortValue } from "./agentSort";
import { isAgentNameConflict, normalizeAgentName, takenAgentNames } from "./agentNames";
import { agentErrorText, createAgentRequest, resolveAgentSpace, updateAgentRequest } from "./weaverAgents";
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
  return <SpaceAgents key={space.id} space={space} contextStamp={context.fulfilledTimeStamp} />;
}

function AgentNotice({ error }: { error: unknown }) {
  const { t } = useTranslation();
  return <ServiceNotice icon="info" title={agentErrorText(error, t)} />;
}

function SpaceAgents({ space, contextStamp }: { space: MySpace; contextStamp?: number }) {
  const { t } = useTranslation();
  const { showError, showSuccess } = useToast();
  const { showConfirmationDialog } = useConfirmationDialog();
  const { agentsNicknamePlural, agentsNicknameSingular } = useFrontendProperties();
  const spaceId = space.id;
  const [authorize] = useAuthorizeSpaceMutation();
  const [access, setAccess] = useState<{ stamp?: number; allowed: boolean; error?: unknown }>();
  const live = useRef(true);
  useEffect(() => {
    live.current = true;
    return () => {
      live.current = false;
    };
  }, []);
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
  const canManageAgents = access?.stamp === contextStamp && access?.allowed === true;
  const instances = useListAgentInstancesQuery({ spaceId }, { refetchOnMountOrArgChange: true });
  const catalog = useSpaceAgentTemplatesQuery({ spaceId }, { skip: !canManageAgents, refetchOnMountOrArgChange: true });
  const managedInstances = instances.isError ? [] : (instances.currentData ?? []);
  const templates = catalog.isError || !canManageAgents ? [] : (catalog.currentData ?? []);
  const [isEnrollOpen, setIsEnrollOpen] = useState(false);
  const [editingId, setEditingId] = useState<string>();
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
  const busy = creating.isLoading || updating.isLoading || removing.isLoading;
  const unavailable = t("rework.weaverAgents.notConnected");
  const notifyError = (error: unknown) => {
    if (!live.current) return;
    showError({ summary: agentErrorText(error, t) });
  };
  const handleSave = async (payload: AgentFormPayload) => {
    if (!canManageAgents || busy) return;
    try {
      if (editing) {
        await update({
          spaceId,
          agentInstanceId: editing.agent_instance_id,
          updateAgentInstanceRequest: updateAgentRequest(payload, editing),
        }).unwrap();
      } else if (isEnrollOpen) {
        await create({ spaceId, createAgentInstanceRequest: createAgentRequest(payload) }).unwrap();
      } else return;
      if (!live.current) return;
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
      if (live.current)
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
          setEditingId(undefined);
          showSuccess({ summary: t("rework.agentCard.deleteSuccess", { agent: agentsNicknameSingular }) });
        } catch (error) {
          notifyError(error);
        }
      },
    });
  };
  const canCreate = canManageAgents && !catalog.isFetching && !catalog.isError && templates.length > 0;
  const searched = sortAgents(filterAgents(managedInstances, search), sort);
  const names = new Set([...takenAgentNames(managedInstances, editingId), ...refusedNames]);
  return (
    <div className={styles.teamAgentContainer}>
      <div className={styles.title}>
        <PageHeader
          title={t(space.kind === "personal" ? "rework.teams.agents.titlePersonal" : "rework.teams.agents.title")}
          actions={
            <>
              {canManageAgents && (
                <Button
                  color="primary"
                  variant="filled"
                  size="small"
                  icon={{ category: "outlined", type: "add" }}
                  disabled={!canCreate}
                  onClick={() => setIsEnrollOpen(true)}
                >
                  {t("rework.teams.agents.create", { agentsNicknameSingular })}
                </Button>
              )}
              <div className={styles.searchBar}>
                <SearchInput
                  value={search}
                  onChange={setSearch}
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
      </div>
      {access?.error != null && <AgentNotice error={access.error} />}
      {canManageAgents && catalog.isError && <AgentNotice error={catalog.error} />}
      {canManageAgents && !catalog.isFetching && !catalog.isError && catalog.currentData?.length === 0 && (
        <ServiceNotice icon="info" title={t("rework.teams.formAgent.noTemplates")} />
      )}
      {instances.isError ? (
        <AgentNotice error={instances.error} />
      ) : !instances.currentData ? (
        <div className={styles.loadingState}>
          <Spinner size={20} />
          {t("rework.teams.agents.loading", { agentsNicknamePlural })}
        </div>
      ) : managedInstances.length === 0 ? (
        <TeamAgentEmptyState
          canManageAgents={canManageAgents}
          templatesUnavailable={!canCreate}
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
                canManageAgents={canManageAgents}
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
                marketplace={{
                  showBar: false,
                  publishAction: canManageAgents ? { kind: "publish", disabledReason: unavailable } : undefined,
                  canRemove: false,
                  showDetailedState: false,
                  canHide: false,
                  onPublish: () => {},
                  onRemove: () => {},
                  onHide: () => {},
                }}
              />
            ))}
          </div>
        </div>
      )}
      {editingId && canManageAgents && detail.isFetching && <Spinner size={20} />}
      {editingId && canManageAgents && detail.isError && <AgentNotice error={detail.error} />}
      {(isEnrollOpen || editing) && (
        <AgentFormModal
          key={editing?.agent_instance_id ?? "create"}
          isOpen
          isSubmitting={busy || !canManageAgents}
          mode={editing ? "edit" : "create"}
          teamName={space.name}
          templates={templates}
          editInstance={editing}
          takenNames={names}
          onClose={() => {
            setIsEnrollOpen(false);
            setEditingId(undefined);
          }}
          onSubmit={handleSave}
          onDelete={editing && canManageAgents ? () => handleDelete(editing) : undefined}
        />
      )}
    </div>
  );
}
