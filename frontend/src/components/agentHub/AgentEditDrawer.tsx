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
import { Box, Button, Divider, Drawer, Stack, TextField, Typography } from "@mui/material";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { AnyAgent } from "../../common/agent";
import { useAgentUpdater } from "../../hooks/useAgentUpdater";
import { useFrontendProperties } from "../../hooks/useFrontendProperties";
import {
  FieldSpec,
  McpServerRef,
  useCreateAgentAgenticV1AgentsCreatePostMutation,
  useDeleteAgentAgenticV1AgentsAgentIdDeleteMutation,
} from "../../slices/agentic/agenticOpenApi";
import { useConfirmationDialog } from "../ConfirmationDialogProvider";
import { useToast } from "../ToastProvider";
import { AgentPrivateResourcesManager } from "./AgentConfigWorkspaceManagerDrawer";
import { AgentToolsSelection } from "./AgentToolsSelection";
import { TuningForm } from "./TuningForm";

// -----------------------------------------------------------
// NEW TYPE FOR TUNING STATE
// -----------------------------------------------------------
type TopLevelTuningState = {
  role: string;
  description: string;
  tags: string[];
};

type Props = {
  open: boolean;
  /** Pass an agent to edit, or null to create a new one. */
  agent: AnyAgent | null;
  canDelete?: boolean;
  /** Team ownership for the newly created agent (only used in create mode). */
  teamId?: string;

  onClose: () => void;
  onSaved?: () => void;
  onDeleted?: () => void;
};
export function AgentEditDrawer({ open, agent, canDelete, teamId, onClose, onSaved, onDeleted }: Props) {
  const { agentsNicknameSingular } = useFrontendProperties();
  const [createAgent] = useCreateAgentAgenticV1AgentsCreatePostMutation();
  const { updateTuning, isLoading } = useAgentUpdater();
  const { t } = useTranslation();
  const { showConfirmationDialog } = useConfirmationDialog();
  const { showError } = useToast();

  const isCreateMode = agent === null;

  const [triggerDeleteAgent] = useDeleteAgentAgenticV1AgentsAgentIdDeleteMutation();
  // State for agent name (top-level, outside tuning)
  const [agentName, setAgentName] = useState("");
  // State for dynamic fields
  const [fields, setFields] = useState<FieldSpec[]>([]);
  // State for top-level Tuning properties
  const [topLevelTuning, setTopLevelTuning] = useState<TopLevelTuningState>({
    role: "",
    description: "",
    tags: [],
  });
  const [mcpServerRefs, setMcpServerRefs] = useState<McpServerRef[]>([]);

  // --- Effects ---

  useEffect(() => {
    if (agent) {
      setAgentName(agent.name);
    }
    if (agent?.tuning) {
      // 1. Initialize dynamic fields (deep clone)
      const fs = agent.tuning.fields ?? [];
      setFields(JSON.parse(JSON.stringify(fs)));

      // 2. Initialize top-level tuning fields
      setTopLevelTuning({
        role: agent.tuning.role,
        description: agent.tuning.description,
        tags: agent.tuning.tags ?? [],
      });
      const normalizedRefs =
        (agent.tuning.mcp_servers ?? []).map((ref) => ({
          id: ref.id,
          require_tools: ref.require_tools ?? [],
        })) ?? [];
      setMcpServerRefs(normalizedRefs);
    } else {
      // Reset state if agent is null or has no tuning
      setAgentName("");
      setFields([]);
      setTopLevelTuning({ role: "", description: "", tags: [] });
      setMcpServerRefs([]);
    }
  }, [agent]);

  // --- Handlers ---

  // Handler for dynamic fields (TuningForm)
  const onChange = (i: number, next: any) => {
    setFields((prev) => {
      const copy = [...prev];
      copy[i] = { ...copy[i], default: next };
      return copy;
    });
  };

  // Handler for top-level fields (Role, Description)
  const onTopLevelChange = (key: keyof TopLevelTuningState, value: string | string[]) => {
    setTopLevelTuning((prev) => ({
      ...prev,
      [key]: value,
    }));
  };

  const handleSave = async () => {
    const trimmedName = agentName.trim();

    try {
      // In create mode, create the agent first then update its tuning
      const targetAgent = isCreateMode
        ? await createAgent({
            createAgentRequest: { name: trimmedName, type: "basic", team_id: teamId },
          }).unwrap()
        : agent;

      // Merge form values on top of the target agent's tuning (preserves defaults from creation)
      const newTuning = {
        ...(targetAgent.tuning || {}),
        role: topLevelTuning.role,
        description: topLevelTuning.description,
        tags: topLevelTuning.tags,
        mcp_servers: mcpServerRefs,
        // In create mode, keep the default fields from the created agent
        ...(isCreateMode ? {} : { fields }),
      };

      await updateTuning({ ...targetAgent, name: trimmedName }, newTuning);
      onSaved?.();
      onClose();
    } catch (e: any) {
      showError({
        summary: isCreateMode
          ? t("agentEditDrawer.errors.createFailed")
          : t("agentEditDrawer.errors.updateFailed"),
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

  const isSaveDisabled = isLoading || !agentName.trim() || !topLevelTuning.role || !topLevelTuning.description;

  return (
    <Drawer
      anchor="right"
      open={open}
      onClose={onClose}
      PaperProps={{ sx: { width: { xs: "100%", sm: 720, md: 880 } } }}
    >
      <Box sx={{ height: "100%", display: "flex", flexDirection: "column" }}>
        {/* Header - Remains mostly the same, shows name */}
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

            {/* Dynamic Fields (edit mode only) */}
            {!isCreateMode &&
              (fields.length === 0 ? (
                <Typography variant="body2" color="text.secondary">
                  {t("agentEditDrawer.noTunableFields")}
                </Typography>
              ) : (
                <TuningForm fields={fields} onChange={onChange} />
              ))}

            {/* Workspace Files (edit mode only) */}
            {!isCreateMode && (
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
            bgcolor: "background.paper",
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
    </Drawer>
  );
}
