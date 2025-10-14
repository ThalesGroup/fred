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
import { Box, Button, Divider, Drawer, Stack, Typography } from "@mui/material";
import { useEffect, useState } from "react";
import { AnyAgent } from "../../common/agent";
import { useAgentUpdater } from "../../hooks/useAgentUpdater";
import { FieldSpec } from "../../slices/agentic/agenticOpenApi";
import { TuningForm } from "./TuningForm";

type Props = { open: boolean; agent: AnyAgent | null; onClose: () => void; onSaved?: () => void };

export function AgentEditDrawer({ open, agent, onClose, onSaved }: Props) {
  const { updateTuning, isLoading } = useAgentUpdater();
  const [fields, setFields] = useState<FieldSpec[]>([]);

  useEffect(() => {
    const fs = agent?.tuning?.fields ?? [];
    // deep clone
    setFields(JSON.parse(JSON.stringify(fs)));
  }, [agent]);

  const onChange = (i: number, next: any) => {
    setFields((prev) => {
      const copy = [...prev];
      copy[i] = { ...copy[i], default: next };
      return copy;
    });
  };

  const handleSave = async () => {
    if (!agent) return;
    const newTuning = { ...(agent.tuning || {}), fields };
    await updateTuning(agent, newTuning);
    onSaved?.();
    onClose();
  };

  return (
    <Drawer
      anchor="right"
      open={open}
      onClose={onClose}
      PaperProps={{ sx: { width: { xs: "100%", sm: 720, md: 880 } } }}
    >
      <Box sx={{ height: "100%", display: "flex", flexDirection: "column" }}>
        {/* Header */}
        <Box sx={{ p: 2 }}>
          <Typography variant="h6">{agent?.name ?? "—"}</Typography>
          {agent && (
            <Typography variant="body2" color="text.secondary">
              {agent.role} — {agent.description}
            </Typography>
          )}
        </Box>
        <Divider />

        {/* Body (scrollable) */}
        <Box sx={{ p: 2, flex: 1, overflow: "auto" }}>
          {fields.length === 0 ? (
            <Typography variant="body2" color="text.secondary">
              This agent exposes no tunable fields.
            </Typography>
          ) : (
            <TuningForm fields={fields} onChange={onChange} />
          )}
        </Box>

        {/* Sticky footer */}
        <Divider />
        <Box sx={{ p: 1.5, position: "sticky", bottom: 0, bgcolor: "background.paper" }}>
          <Stack direction="row" gap={1} justifyContent="flex-end">
            <Button variant="outlined" onClick={onClose}>
              Cancel
            </Button>
            <Button variant="contained" disabled={isLoading} onClick={handleSave}>
              Save
            </Button>
          </Stack>
        </Box>
      </Box>
    </Drawer>
  );
}
