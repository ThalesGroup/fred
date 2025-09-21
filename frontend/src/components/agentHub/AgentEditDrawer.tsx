// src/components/agentHub/AgentEditDrawer.tsx
import { Box, Button, Divider, Drawer, Stack, Typography } from "@mui/material";
import { useEffect, useState } from "react";
import { FieldSpec } from "../../slices/agentic/agenticOpenApi";
import { TuningForm } from "./TuningForm";
import { AnyAgent } from "../../common/agent";
import { useAgentUpdater } from "../../hooks/useAgentUpdater";

type Props = { open: boolean; agent: AnyAgent | null; onClose: () => void; onSaved?: () => void; };

export function AgentEditDrawer({ open, agent, onClose, onSaved }: Props) {
  const { updateTuning, isLoading } = useAgentUpdater();

  // local copy; we only mutate FieldSpec.default for now
  const [fields, setFields] = useState<FieldSpec[]>([]);
  useEffect(() => {
    const fs = agent?.tuning?.fields ?? [];
    setFields(JSON.parse(JSON.stringify(fs)));
  }, [agent]);

  const onChange = (i: number, next: any) => {
    setFields(prev => {
      const copy = [...prev];
      copy[i] = { ...copy[i], default: next };
      return copy;
    });
  };

  if (!agent) {
    return <Drawer anchor="right" open={open} onClose={onClose}><Box sx={{ width: 560, p: 2 }}><Typography>No agent selected</Typography></Box></Drawer>;
  }

  const handleSave = async () => {
    const newTuning = { ...(agent.tuning || {}), fields };
    await updateTuning(agent, newTuning);
    onSaved?.();
    onClose();
  };

  return (
    <Drawer anchor="right" open={open} onClose={onClose}>
      <Box sx={{ width: 560, p: 2, display: "flex", flexDirection: "column", gap: 1.5 }}>
        <Typography variant="h6">{agent.name}</Typography>
        <Typography variant="body2" color="text.secondary">{agent.role} — {agent.description}</Typography>
        <Divider sx={{ my: 1 }} />
        {fields.length === 0 ? (
          <Typography variant="body2" color="text.secondary">This agent exposes no tunable fields.</Typography>
        ) : (
          <TuningForm fields={fields} onChange={onChange} />
        )}
        <Stack direction="row" gap={1} justifyContent="flex-end" sx={{ mt: 1 }}>
          <Button variant="outlined" onClick={onClose}>Cancel</Button>
          <Button variant="contained" disabled={isLoading} onClick={handleSave}>Save</Button>
        </Stack>
      </Box>
    </Drawer>
  );
}
