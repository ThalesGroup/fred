// Copyright Thales 2025
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
import DeleteIcon from "@mui/icons-material/Delete";
import { Autocomplete, Box, Button, Divider, Stack, TextField, Typography } from "@mui/material";
import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useAgentUpdater } from "../../hooks/useAgentUpdater";
import { useFrontendProperties } from "../../hooks/useFrontendProperties";
import { KeyCloakService } from "../../security/KeycloakService";
import {
  FieldSpec,
  McpServerRef,
  useCreateAgentAgenticV1AgentsCreatePostMutation,
  useDeleteAgentAgenticV1AgentsAgentIdDeleteMutation,
  useLazyGetClassPathTuningAgenticV1AgentsClassPathsTuningGetQuery as useLazyGetClassPathTuningQuery,
  useListDeclaredAgentClassPathsAgenticV1AgentsClassPathsGetQuery as useListDeclaredAgentClassPathsQuery,
  useListReactAgentProfilesAgenticV1AgentsReactProfilesGetQuery as useListReactProfilesQuery,
} from "../../slices/agentic/agenticOpenApi";
import { useConfirmationDialog } from "../ConfirmationDialogProvider";
import { useToast } from "../ToastProvider";
import { AgentPrivateResourcesManager } from "./AgentConfigWorkspaceManagerDrawer";
import { AgentCreateEditDrawerProps } from "./AgentCreateEditDrawer";
import { AgentToolsSelection } from "./AgentToolsSelection";
import { TuningForm } from "./TuningForm";

type TopLevelTuningState = {
  role: string;
  description: string;
  tags: string[];
};

export type AgentCreateEditFormProps = Omit<AgentCreateEditDrawerProps, "open">;

export function AgentCreateEditForm({
  agent,
  canDelete,
  teamId,
  onClose,
  onSaved,
  onDeleted,
}: AgentCreateEditFormProps) {
  const { agentsNicknameSingular } = useFrontendProperties();
  const [createAgent] = useCreateAgentAgenticV1AgentsCreatePostMutation();
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

  const userRoles = KeyCloakService.GetUserRoles();
  const isAdmin = userRoles.includes("admin");

  const { data: reactProfiles = [] } = useListReactProfilesQuery(undefined, {
    skip: !isCreateMode || !isAdmin,
  });
  const hasReactProfiles = reactProfiles.length > 0;

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

  // Fetch default tuning when classPath changes
  useEffect(() => {
    fetchClassPathTuning({ classPath: classPath ?? undefined })
      .unwrap()
      .then((tuning) => {
        setFields((prev) => mergeFields(tuning.fields ?? [], prev));
      });
  }, [classPath, fetchClassPathTuning, mergeFields]);

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
        ? await createAgent({
            createAgentRequest: {
              name: trimmedName,
              type: "basic",
              team_id: teamId,
              class_path: classPath || undefined,
              profile_id: profileId || undefined,
            },
          }).unwrap()
        : agent;

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
      onClose();
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
          onClose();
        } catch (err) {
          console.error("Failed to delete agent:", err);
        }
      },
    });
  };

  const hasEmptyRequiredFields = fields.some(
    (f) => f.required && (f.default === undefined || f.default === null || f.default === ""),
  );

  const isSaveDisabled =
    isLoading || !agentName.trim() || !topLevelTuning.role || !topLevelTuning.description || hasEmptyRequiredFields;

  return (
    <Box sx={{ height: "100%", display: "flex", flexDirection: "column" }}>
      {/* Header */}
      <Box sx={{ p: 2 }}>
        <Typography variant="h6">
          {isCreateMode
            ? t("agentEditDrawer.headerTitleCreate", { agentsNicknameSingular })
            : t("agentEditDrawer.headerTitle", { agentsNicknameSingular })}
        </Typography>
      </Box>
      <Divider />

      {/* Body (scrollable) */}
      <Box sx={{ p: 2, flex: 1, overflow: "auto" }}>
        <Stack spacing={3}>
          {/* Agent Name */}
          <TextField
            label={t("agentEditDrawer.nameLabel")}
            size="small"
            value={agentName}
            onChange={(e) => setAgentName(e.target.value)}
            required
            fullWidth
            slotProps={{
              input: {
                sx: (theme) => ({
                  fontSize: theme.typography.body2.fontSize,
                }),
              },
            }}
          />
          {/* Profile selection (create mode only, when profiles are available) */}
          {isCreateMode && isAdmin && hasReactProfiles && (
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

          {/* Class path selection (admin only) */}
          {isAdmin && (
            <Autocomplete
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

          {/* Tuning Core Fields */}
          <TextField
            label="Role"
            size="small"
            value={topLevelTuning.role}
            onChange={(e) => onTopLevelChange("role", e.target.value)}
            required
            fullWidth
            slotProps={{
              input: {
                sx: (theme) => ({
                  fontSize: theme.typography.body2.fontSize,
                }),
              },
            }}
          />
          <TextField
            label="Description"
            size="small"
            value={topLevelTuning.description}
            onChange={(e) => onTopLevelChange("description", e.target.value)}
            required
            multiline
            rows={3}
            fullWidth
            slotProps={{
              input: {
                sx: (theme) => ({
                  fontSize: theme.typography.body2.fontSize,
                }),
              },
            }}
          />

          {/* <TagsInput
            label={t("agentEditDrawer.tagsLabel")}
            value={topLevelTuning.tags}
            onChange={(next) => onTopLevelChange("tags", next)}
          /> */}

          <AgentToolsSelection mcpServerRefs={mcpServerRefs} onMcpServerRefsChange={setMcpServerRefs} />

          {/* Dynamic Fields */}
          {fields.length === 0 ? (
            <Typography variant="body2" color="text.secondary">
              {t("agentEditDrawer.noTunableFields")}
            </Typography>
          ) : (
            <TuningForm fields={fields} onChange={onChange} />
          )}

          {/* Workspace Files (edit mode only. Only for admin for now to simplify. Should be moved to tools param that require files) */}
          {isAdmin && !isCreateMode && (
            <>
              <Divider />
              <Typography variant="h6">{t("assetManager.title", { agentId: agent?.name })}</Typography>
              {agent && <AgentPrivateResourcesManager agentId={agent.id} />}
            </>
          )}
        </Stack>
      </Box>

      {/* Sticky footer */}
      <Divider />
      <Box
        sx={{
          p: 1.5,
          position: "sticky",
          bottom: 0,
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
        }}
      >
        <Stack direction="row" justifyContent="flex-start">
          {!isCreateMode && (
            <Button
              variant="contained"
              color="error"
              startIcon={<DeleteIcon />}
              onClick={handleDelete}
              disabled={!canDelete}
            >
              {t("common.delete")}
            </Button>
          )}
        </Stack>
        <Stack direction="row" gap={1} justifyContent="flex-end">
          <Button variant="outlined" onClick={onClose}>
            {t("dialogs.cancel")}
          </Button>
          <Button variant="contained" disabled={isSaveDisabled} onClick={handleSave}>
            {isCreateMode ? t("common.create") : t("common.save")}
          </Button>
        </Stack>
      </Box>
    </Box>
  );
}
