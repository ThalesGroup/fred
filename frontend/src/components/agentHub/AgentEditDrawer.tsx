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
import {
  FieldSpec,
  McpServerRef,
  useDeleteAgentAgenticV1AgentsAgentIdDeleteMutation,
} from "../../slices/agentic/agenticOpenApi";
import { useConfirmationDialog } from "../ConfirmationDialogProvider";
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
  agent: AnyAgent | null;
  canDelete?: boolean;

  onClose: () => void;
  onSaved?: () => void;
  onDeleted?: () => void;
};
export function AgentEditDrawer({ open, agent, canDelete, onClose, onSaved, onDeleted }: Props) {
  const { updateTuning, isLoading } = useAgentUpdater();
  const { t } = useTranslation();
  const { showConfirmationDialog } = useConfirmationDialog();

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
    if (!agent) return;

    // 1. Construct the new AgentTuning object by merging all parts
    const newTuning = {
      // Retain other properties like mcp_servers
      ...(agent.tuning || {}),
      // Overwrite/set top-level fields
      role: topLevelTuning.role,
      description: topLevelTuning.description,
      tags: topLevelTuning.tags,
      // Overwrite/set dynamic fields
      fields: fields,
      mcp_servers: mcpServerRefs,
    };

    const updatedAgent = { ...agent, name: agentName };
    await updateTuning(updatedAgent, newTuning);
    onSaved?.();
    onClose();
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

  const isSaveDisabled =
    isLoading || !agent || !agentName.trim() || !topLevelTuning.role || !topLevelTuning.description;

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
          <Typography variant="h6">{agent?.name ?? "—"}</Typography>
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
              helperText={t("agentEditDrawer.nameHelperText")}
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
              helperText={t("agentEditDrawer.roleHelperText")}
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
              helperText={t("agentEditDrawer.descriptionHelperText")}
            />

            {/* <TagsInput
              label={t("agentEditDrawer.tagsLabel")}
              helperText={t("agentEditDrawer.tagsHelperText")}
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
            <Button
              variant="contained"
              color="error"
              startIcon={<DeleteIcon />}
              onClick={handleDelete}
              disabled={!canDelete}
            >
              {t("common.delete")}
            </Button>
          </Stack>
          <Stack direction="row" gap={1} justifyContent="flex-end">
            <Button variant="outlined" onClick={onClose}>
              {t("dialogs.cancel")}
            </Button>
            <Button variant="contained" disabled={isSaveDisabled} onClick={handleSave}>
              {t("common.save")}
            </Button>
          </Stack>
        </Box>
      </Box>
    </Drawer>
  );
}
