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
import { Autocomplete, Box, Divider, TextField, Typography } from "@mui/material";
import { Ref, useCallback, useEffect, useImperativeHandle, useState } from "react";
import { useTranslation } from "react-i18next";
import { useAgentUpdater } from "../../hooks/useAgentUpdater";
import { KeyCloakService } from "../../security/KeycloakService";
import {
  FieldSpec,
  McpServerRef,
  ReActProfileSummary,
  useCreateV1AgentAgenticV1AgentsV1CreatePostMutation,
  useCreateV2AgentAgenticV1AgentsV2CreatePostMutation,
  useDeleteAgentAgenticV1AgentsAgentIdDeleteMutation,
  useLazyGetClassPathTuningAgenticV1AgentsClassPathsTuningGetQuery as useLazyGetClassPathTuningQuery,
  useListDeclaredAgentClassPathsAgenticV1AgentsClassPathsGetQuery as useListDeclaredAgentClassPathsQuery,
  useListReactAgentProfilesAgenticV1AgentsReactProfilesGetQuery as useListReactProfilesQuery,
  useListV2DefinitionRefsAgenticV1AgentsV2DefinitionRefsGetQuery as useListV2DefinitionRefsQuery,
} from "../../slices/agentic/agenticOpenApi";
import { useConfirmationDialog } from "../ConfirmationDialogProvider";
import { useToast } from "../ToastProvider";
import { AgentPrivateResourcesManager } from "./AgentConfigWorkspaceManagerDrawer";
import { AgentToolsSelection } from "./AgentToolsSelection";
import { TuningForm } from "./TuningForm";
import ButtonGroup from "@shared/atoms/ButtonGroup/ButtonGroup.tsx";
import { useGetUserDetailsControlPlaneV1UserGetQuery } from "../../slices/controlPlane/controlPlaneOpenApi.ts";
import TextInput from "@shared/atoms/TextInput/TextInput.tsx";
import TextArea from "@shared/atoms/TextArea/TextArea.tsx";
import { AnyAgent } from "../../common/agent.ts";

type TopLevelTuningState = {
  role: string;
  description: string;
  tags: string[];
};

/** How a v2 agent is created. Only relevant in create mode. */
type V2CreateMode = "react" | "profile" | "definition_ref";

/** Top-level version choice in create mode (admin only). */
type AgentVersion = "v2" | "v1";

export interface CreationFormCallback {
  save: () => void;
  delete: () => void;
}

export type AgentCreateEditFormProps = {
  /** Pass an agent to edit, or null to create a new one. */
  agent: AnyAgent | null;
  canDelete?: boolean;
  /** Team ownership for the newly created agent (only used in create mode). */
  teamId?: string;

  onClose: () => void;
  onSaved?: () => void;
  onDeleted?: () => void;

  ref?: Ref<CreationFormCallback | null>;
  onValidityChange: (validity: boolean) => void;
};

export function AgentCreateEditForm({
  ref,
  agent,
  teamId,
  onSaved,
  onDeleted,
  onValidityChange,
}: AgentCreateEditFormProps) {
  const [createV2Agent] = useCreateV2AgentAgenticV1AgentsV2CreatePostMutation();
  const [createV1Agent] = useCreateV1AgentAgenticV1AgentsV1CreatePostMutation();
  const { data: userDetails } = useGetUserDetailsControlPlaneV1UserGetQuery();
  const { updateTuning, isLoading } = useAgentUpdater();
  const { t } = useTranslation();
  const { showConfirmationDialog } = useConfirmationDialog();
  const { showError } = useToast();

  const isCreateMode = agent === null;

  const [triggerDeleteAgent] = useDeleteAgentAgenticV1AgentsAgentIdDeleteMutation();
  const [agentName, setAgentName] = useState(agent?.name ?? "");
  const [fields, setFields] = useState<FieldSpec[]>(
    agent?.tuning?.fields ? JSON.parse(JSON.stringify(agent.tuning.fields)) : [],
  );
  const [topLevelTuning, setTopLevelTuning] = useState<TopLevelTuningState>({
    role: agent?.tuning?.role ?? "",
    description: agent?.tuning?.description ?? "",
    tags: agent?.tuning?.tags ?? [],
  });
  const [mcpServerRefs, setMcpServerRefs] = useState<McpServerRef[]>(
    (agent?.tuning?.mcp_servers ?? []).map((ref) => ({
      id: ref.id,
      require_tools: ref.require_tools ?? [],
    })),
  );
  const [classPath, setClassPath] = useState<string | null>(agent?.class_path ?? null);
  const [profileId, setProfileId] = useState<string | null>(null);
  const [definitionRef, setDefinitionRef] = useState<string | null>(null);

  // Create-mode choices (reset when toggling)
  const [agentVersion, setAgentVersion] = useState<AgentVersion>("v2");
  const [v2CreateMode, setV2CreateMode] = useState<V2CreateMode>("react");

  const userRoles = KeyCloakService.GetUserRoles();
  const isAdmin = userRoles.includes("admin");

  const { data: reactProfiles = [] } = useListReactProfilesQuery(undefined, {
    skip: !isCreateMode || !isAdmin,
  });
  const hasReactProfiles = reactProfiles.length > 0;

  const { data: v2DefinitionRefs = [] } = useListV2DefinitionRefsQuery(undefined, {
    skip: !isCreateMode || !isAdmin,
  });
  const hasDefinitionRefs = v2DefinitionRefs.length > 0;

  const { data: declaredClassPaths = [] } = useListDeclaredAgentClassPathsQuery(undefined, {
    skip: !isAdmin,
  });

  const [fetchClassPathTuning] = useLazyGetClassPathTuningQuery();

  const mergeFields = useCallback((newFields: FieldSpec[], currentFields: FieldSpec[]): FieldSpec[] => {
    const currentByKey = new Map(currentFields.map((f) => [f.key, f]));
    return newFields.map((newField) => {
      const existing = currentByKey.get(newField.key);
      if (existing) {
        return { ...newField, default: existing.default };
      }
      return newField;
    });
  }, []);

  // Reset v2 sub-choice state when switching modes
  const handleV2CreateModeChange = (next: V2CreateMode) => {
    setV2CreateMode(next);
    setProfileId(null);
    setDefinitionRef(null);
    setFields([]);
    setTopLevelTuning({ role: "", description: "", tags: [] });
    setMcpServerRefs([]);
  };

  // Reset everything when switching V1/V2
  const handleAgentVersionChange = (next: AgentVersion) => {
    setAgentVersion(next);
    setV2CreateMode("react");
    setClassPath(null);
    setProfileId(null);
    setDefinitionRef(null);
  };

  // Fetch default tuning when classPath or definitionRef changes (create react mode or edit).
  const editDefinitionRef = !isCreateMode ? (agent?.definition_ref ?? null) : null;
  useEffect(() => {
    if (isCreateMode && (v2CreateMode === "profile" || v2CreateMode === "definition_ref")) {
      return;
    }
    fetchClassPathTuning({
      classPath: classPath ?? undefined,
      definitionRef: editDefinitionRef ?? undefined,
    })
      .unwrap()
      .then((tuning) => {
        setFields((prev) => (isCreateMode ? (tuning.fields ?? []) : mergeFields(tuning.fields ?? [], prev)));
        setTopLevelTuning((prev) => ({
          role: prev.role || tuning.role || "",
          description: prev.description || tuning.description || "",
          tags: prev.tags.length > 0 ? prev.tags : tuning.tags || [],
        }));
        if (isCreateMode) {
          setMcpServerRefs(
            (tuning.mcp_servers ?? []).map((ref) => ({
              id: ref.id,
              require_tools: ref.require_tools ?? [],
            })),
          );
        }
      });
  }, [classPath, editDefinitionRef, fetchClassPathTuning, isCreateMode, v2CreateMode, mergeFields]);

  // --- Handlers ---

  const onChange = (i: number, next: any) => {
    setFields((prev) => {
      const copy = [...prev];
      copy[i] = { ...copy[i], default: next };
      return copy;
    });
  };

  const onTopLevelChange = (key: keyof TopLevelTuningState, value: string | string[]) => {
    setTopLevelTuning((prev) => ({
      ...prev,
      [key]: value,
    }));
  };

  const handleSave = async () => {
    const trimmedName = agentName.trim();

    try {
      const targetAgent = isCreateMode
        ? agentVersion === "v1"
          ? await createV1Agent({
              createV1AgentRequest: {
                name: trimmedName,
                team_id: teamId === userDetails.personalTeam.id ? undefined : teamId,
                class_path: classPath!,
              },
            }).unwrap()
          : await createV2Agent({
              createV2AgentRequest: {
                name: trimmedName,
                team_id: teamId === userDetails.personalTeam.id ? undefined : teamId,
                profile_id: v2CreateMode === "profile" ? profileId || undefined : undefined,
                definition_ref: v2CreateMode === "definition_ref" ? definitionRef || undefined : undefined,
              },
            }).unwrap()
        : agent;

      // Profile, definition_ref, and V1 class_path agents are created with defaults — skip tuning update.
      if (isCreateMode && (v2CreateMode === "profile" || v2CreateMode === "definition_ref" || agentVersion === "v1")) {
        onSaved?.();
        return;
      }

      const newTuning = {
        ...(targetAgent.tuning || {}),
        role: topLevelTuning.role,
        description: topLevelTuning.description,
        tags: topLevelTuning.tags,
        mcp_servers: mcpServerRefs,
        fields,
      };

      await updateTuning({ ...targetAgent, name: trimmedName, class_path: classPath }, newTuning);
      onSaved?.();
    } catch (e: any) {
      showError({
        summary: isCreateMode ? t("agentEditDrawer.errors.createFailed") : t("agentEditDrawer.errors.updateFailed"),
        detail: e?.data?.detail || e?.message || String(e),
      });
    }
  };

  const handleDelete = () => {
    if (!agent) return;

    showConfirmationDialog({
      criticalAction: true,
      title: t("agentHub.confirmDeleteTitle"),
      message: t("agentHub.confirmDeleteMessage"),
      onConfirm: async () => {
        try {
          await triggerDeleteAgent({ agentId: agent.id }).unwrap();
          onDeleted?.();
        } catch (err) {
          console.error("Failed to delete agent:", err);
        }
      },
    });
  };

  useImperativeHandle(ref, () => ({
    save: handleSave,
    delete: handleDelete,
  }));

  const hasEmptyRequiredFields = fields.some(
    (f) => f.required && (f.default === undefined || f.default === null || f.default === ""),
  );

  useEffect(() => {
    onValidityChange(isSaveDisabled);
  }, [
    agentName,
    isLoading,
    isCreateMode,
    topLevelTuning.role,
    topLevelTuning.description,
    hasEmptyRequiredFields,
    agentVersion,
    classPath,
    v2CreateMode,
    profileId,
    definitionRef,
  ]);

  const isSaveDisabled = (() => {
    if (!agentName.trim()) return true;
    if (isLoading) return true;
    if (!isCreateMode) return !topLevelTuning.role || !topLevelTuning.description || hasEmptyRequiredFields;
    if (agentVersion === "v1") return !classPath;
    if (v2CreateMode === "profile") return !profileId;
    if (v2CreateMode === "definition_ref") return !definitionRef;
    // react: require role + description
    return !topLevelTuning.role || !topLevelTuning.description || hasEmptyRequiredFields;
  })();

  // Derived booleans for JSX clarity
  const showTuningFields = !isCreateMode || (agentVersion === "v2" && v2CreateMode === "react");

  return (
    <>
      {/* ── Version toggle (create mode, team admin only) ── */}
      {isCreateMode && isAdmin && (
        <ButtonGroup
          items={[
            {
              key: "v2",
              value: "v2",
              label: t("agentHub.fields.agentVersionV2"),
              onClick: () => handleAgentVersionChange("v2"),
            },
            {
              key: "v1",
              value: "v1",
              label: t("agentHub.fields.agentVersionV1"),
              onClick: () => handleAgentVersionChange("v1"),
            },
          ]}
          size={"medium"}
          color={"secondary"}
        />
      )}

      {/* ── V2 type toggle (create mode, team admin only) ── */}
      {isCreateMode && isAdmin && agentVersion === "v2" && (
        <ButtonGroup
          items={[
            {
              key: "react",
              value: "react",
              label: t("agentHub.fields.v2ModeReact"),
              onClick: () => handleV2CreateModeChange("react"),
            },
            hasReactProfiles && {
              key: "profile",
              value: "profile",
              label: t("agentHub.fields.v2ModeProfile"),
              onClick: () => handleV2CreateModeChange("profile"),
            },
            hasDefinitionRefs && {
              key: "definition_ref",
              value: "definition_ref",
              label: t("agentHub.fields.v2ModeDefinition"),
              onClick: () => handleV2CreateModeChange("definition_ref"),
            },
          ]}
          size={"medium"}
          color={"secondary"}
        />
      )}

      {/* Agent Name */}
      <TextInput
        placeholder={t("rework.teams.formAgent.fields.name.placeholder")}
        label={t("rework.teams.formAgent.fields.name.label")}
        value={agentName}
        onChange={(e) => setAgentName(e.target.value)}
        maxLength={20}
        required
      />

      {/* ── Profile picker (V2 profile mode) ── */}
      {isCreateMode && v2CreateMode === "profile" && (
        <Autocomplete
          options={reactProfiles}
          value={reactProfiles.find((p) => p.profile_id === profileId) ?? null}
          isOptionEqualToValue={(option, value) => option.profile_id === value.profile_id}
          getOptionLabel={(option) => option.title}
          onChange={(_, value) => setProfileId(value?.profile_id ?? null)}
          renderOption={(props, option) => (
            <li {...props} key={option.profile_id}>
              <Box>
                <Typography variant="body2">{option.title}</Typography>
                <Typography variant="caption" color="text.secondary">
                  {option.description}
                </Typography>
              </Box>
            </li>
          )}
          renderInput={(params) => (
            <TextField
              {...params}
              size="small"
              label={t("agentHub.fields.profile")}
              helperText={
                reactProfiles.find((p) => p.profile_id === profileId)?.agent_description ??
                t("agentHub.fields.profileHelp")
              }
            />
          )}
        />
      )}

      {/* ── Definition ref picker (V2 definition mode) ── */}
      {isCreateMode && v2CreateMode === "definition_ref" && (
        <Autocomplete<string>
          options={v2DefinitionRefs}
          value={definitionRef}
          onChange={(_, value) => setDefinitionRef(value)}
          renderInput={(params) => (
            <TextField
              {...params}
              size="small"
              label={t("agentHub.fields.definitionRef")}
              helperText={t("agentHub.fields.definitionRefHelp")}
            />
          )}
        />
      )}

      {/* ── Class path picker (V1 create or edit, admin only) ── */}
      {isAdmin && (!isCreateMode || agentVersion === "v1") && (
        <Autocomplete<string>
          options={declaredClassPaths}
          value={classPath}
          onChange={(_, value) => setClassPath(value)}
          renderInput={(params) => (
            <TextField
              {...params}
              size="small"
              label={t("agentHub.fields.classPath")}
              placeholder="my_module.agents.MyCustomAgent"
              helperText={t("agentHub.fields.classPathHelp")}
            />
          )}
        />
      )}

      {/* ── Tuning core fields (react create or edit) ── */}
      {showTuningFields && (
        <>
          <TextInput
            placeholder={t("rework.teams.formAgent.fields.role.placeholder")}
            label={t("rework.teams.formAgent.fields.role.label")}
            value={topLevelTuning.role}
            onChange={(e) => onTopLevelChange("role", e.target.value)}
            maxLength={55}
            required
          />
          <TextArea
            placeholder={t("rework.teams.formAgent.fields.description.placeholder")}
            label={t("rework.teams.formAgent.fields.description.label")}
            maxLength={80}
            value={topLevelTuning.description}
            onChange={(e) => onTopLevelChange("description", e.target.value)}
            required
          />
        </>
      )}

      {/* ── Tools ── */}
      {showTuningFields && (
        <AgentToolsSelection mcpServerRefs={mcpServerRefs} onMcpServerRefsChange={setMcpServerRefs} />
      )}

      {/* ── Dynamic tuning fields ── */}
      {showTuningFields &&
        (fields.length === 0 ? (
          <Typography variant="body2" color="text.secondary">
            {t("agentEditDrawer.noTunableFields")}
          </Typography>
        ) : (
          <TuningForm fields={fields} onChange={onChange} />
        ))}

      {/* ── Profile description (profile mode) ── */}
      {isCreateMode && v2CreateMode === "profile" && profileId && (
        <Typography variant="body2" color="text.secondary">
          {reactProfiles.find((p: ReActProfileSummary) => p.profile_id === profileId)?.agent_description ??
            t("agentHub.fields.profileHelp")}
        </Typography>
      )}

      {/* Workspace Files (edit mode only, admin only) */}
      {isAdmin && !isCreateMode && (
        <>
          <Divider />
          <Typography variant="h6">{t("assetManager.title", { agentId: agent?.name })}</Typography>
          {agent && <AgentPrivateResourcesManager agentId={agent.id} />}
        </>
      )}
    </>
  );
}
