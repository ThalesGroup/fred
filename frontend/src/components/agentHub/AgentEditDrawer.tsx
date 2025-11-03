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
import { Autocomplete, Box, Button, Chip, Divider, Drawer, Stack, TextField, Typography } from "@mui/material";
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { AnyAgent } from "../../common/agent";
import { useAgentUpdater } from "../../hooks/useAgentUpdater";
import { FieldSpec, McpServerConfiguration, McpServerRef } from "../../slices/agentic/agenticOpenApi";
import { TagsInput } from "./AgentTagsInput";
import { TuningForm } from "./TuningForm";

// -----------------------------------------------------------
// NEW TYPE FOR TUNING STATE
// -----------------------------------------------------------
type TopLevelTuningState = {
  role: string;
  description: string;
  tags: string[];
};

type KnownMcpServer = McpServerConfiguration & McpServerRef;

type Props = {
  open: boolean;
  agent: AnyAgent | null;
  onClose: () => void;
  onSaved?: () => void;
  knownMcpServers: McpServerConfiguration[];
  isLoadingKnownMcpServers?: boolean;
};

export function AgentEditDrawer({
  open,
  agent,
  onClose,
  onSaved,
  knownMcpServers,
  isLoadingKnownMcpServers = false,
}: Props) {
  const { updateTuning, isLoading } = useAgentUpdater();
  const { t } = useTranslation();
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
      setMcpServerRefs(agent.tuning.mcp_servers ?? []);
    } else {
      // Reset state if agent is null or has no tuning
      setFields([]);
      setTopLevelTuning({ role: "", description: "", tags: [] });
      setMcpServerRefs([]);
    }
  }, [agent]);

  const normalizedKnownServers = useMemo<KnownMcpServer[]>(() => {
    const seen = new Set<string>();
    const result: KnownMcpServer[] = [];

    knownMcpServers.forEach((server) => {
      if (!server) return;
      const name = typeof server.name === "string" ? server.name.trim() : "";
      if (!name || seen.has(name)) return;

      const requireTools =
        Array.isArray((server as Partial<McpServerRef>).require_tools) &&
        (server as Partial<McpServerRef>).require_tools!.length > 0
          ? (server as Partial<McpServerRef>).require_tools
          : undefined;

      result.push({ ...server, name, require_tools: requireTools });
      seen.add(name);
    });

    return result;
  }, [knownMcpServers]);

  const selectedKnownServers = useMemo<KnownMcpServer[]>(() => {
    if (mcpServerRefs.length === 0) return [];

    const byName = new Map(normalizedKnownServers.map((server) => [server.name, server]));

    return mcpServerRefs.map((ref) => {
      const base = byName.get(ref.name);
      if (!base) {
        return { name: ref.name, require_tools: ref.require_tools } as KnownMcpServer;
      }
      return {
        ...base,
        require_tools: ref.require_tools ?? base.require_tools,
      };
    });
  }, [mcpServerRefs, normalizedKnownServers]);

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

  const handleSave = async (isGlobal: boolean) => {
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

    console.log("Saving agent tuning", newTuning, "with global scope:", isGlobal);

    await updateTuning(agent, newTuning, isGlobal);
    onSaved?.();
    onClose();
  };

  const isSaveDisabled = isLoading || !agent || !topLevelTuning.role || !topLevelTuning.description;

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

            <TagsInput
              label={t("agentEditDrawer.tagsLabel")}
              helperText={t("agentEditDrawer.tagsHelperText")}
              value={topLevelTuning.tags}
              onChange={(next) => onTopLevelChange("tags", next)}
            />

            <Autocomplete<KnownMcpServer, true, false, false>
              multiple
              disableCloseOnSelect
              options={normalizedKnownServers}
              value={selectedKnownServers}
              loading={isLoadingKnownMcpServers}
              onChange={(_event, value) => {
                setMcpServerRefs(
                  value.map((server) => ({
                    name: server.name,
                    require_tools:
                      server.require_tools && server.require_tools.length > 0 ? server.require_tools : undefined,
                  })),
                );
              }}
              isOptionEqualToValue={(option, value) => option.name === value.name}
              getOptionLabel={(option) => option.name}
              disablePortal
              renderOption={(props, option) => (
                <li {...props} key={option.name}>
                  <Box sx={{ display: "flex", flexDirection: "column" }}>
                    <Typography variant="body2">{option.name}</Typography>
                    {(option.transport || option.url) && (
                      <Typography variant="caption" color="text.secondary">
                        {option.transport}
                        {option.transport && option.url ? " · " : ""}
                        {option.url}
                      </Typography>
                    )}
                  </Box>
                </li>
              )}
              renderTags={(value, getTagProps) =>
                value.map((option, index) => (
                  <Chip {...getTagProps({ index })} key={option.name} label={option.name} size="small" />
                ))
              }
              renderInput={(params) => (
                <TextField
                  {...params}
                  size="small"
                  label={t("agentHub.fields.mcp_servers", "MCP Servers")}
                  placeholder={t("agentEditDrawer.selectMcpServers")}
                  sx={{
                    // Label (normal + shrunk)
                    "& .MuiInputLabel-root": (theme) => ({
                      fontSize: theme.typography.body2.fontSize,
                    }),
                    "& .MuiInputLabel-shrink": (theme) => ({
                      fontSize: theme.typography.body2.fontSize,
                    }),
                    // Input text (for consistency)
                    "& .MuiInputBase-input": (theme) => ({
                      fontSize: theme.typography.body2.fontSize,
                    }),
                  }}
                  helperText={normalizedKnownServers.length === 0 ? t("agentEditDrawer.noMcpServers") : undefined}
                />
              )}
              noOptionsText={isLoadingKnownMcpServers ? t("common.loading") : t("agentEditDrawer.noMcpServers")}
            />

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
        <Box sx={{ p: 1.5, position: "sticky", bottom: 0, bgcolor: "background.paper" }}>
          <Stack direction="row" gap={1} justifyContent="flex-end">
            <Button variant="outlined" onClick={onClose}>
              {t("dialogs.cancel")}
            </Button>
            <Button
              variant="contained"
              disabled={isSaveDisabled}
              onClick={() => handleSave(false)} // Pass false for user-specific
            >
              {t("agentEditDrawer.saveUser")}
            </Button>

            <Button
              variant="contained"
              color="secondary" // Use a different color to highlight global scope
              disabled={isSaveDisabled}
              onClick={() => handleSave(true)} // Pass true for global scope
            >
              {t("agentEditDrawer.saveGlobal")}
            </Button>
          </Stack>
        </Box>
      </Box>
    </Drawer>
  );
}
