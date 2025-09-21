// src/components/agentHub/CrewEditor.tsx
import { Button, Chip, Dialog, DialogActions, DialogContent, DialogTitle, Stack, TextField, Typography } from "@mui/material";
import { useMemo, useState } from "react";
import { Leader } from "../../slices/agentic/agenticOpenApi";
import { useAgentUpdater } from "../../hooks/useAgentUpdater";
import { AnyAgent } from "../../common/agent";

type Props = { open: boolean; leader: (Leader & { type: "leader" }) | null; allAgents: AnyAgent[]; onClose: () => void; onSaved?: () => void; };

export function CrewEditor({ open, leader, allAgents, onClose, onSaved }: Props) {
  const { updateLeaderCrew, isLoading } = useAgentUpdater();
  const [newMember, setNewMember] = useState("");

  const crew = leader?.crew || [];
  const candidates = useMemo(
    () => allAgents.filter(a => a.type === "agent" && !crew.includes(a.name)).map(a => a.name),
    [allAgents, crew]
  );

  const removeMember = async (name: string) => {
    if (!leader) return;
    const next = crew.filter(n => n !== name);
    await updateLeaderCrew(leader, next);
    onSaved?.();
  };

  const addMember = async () => {
    if (!leader || !newMember) return;
    const next = Array.from(new Set([...crew, newMember]));
    await updateLeaderCrew(leader, next);
    setNewMember("");
    onSaved?.();
  };

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle>Crew for {leader?.name}</DialogTitle>
      <DialogContent>
        <Typography variant="subtitle2">Current members</Typography>
        <Stack direction="row" flexWrap="wrap" gap={1} sx={{ my: 1 }}>
          {crew.length ? crew.map(n => <Chip key={n} label={n} onDelete={() => removeMember(n)} disabled={isLoading} />)
                       : <Typography variant="body2" color="text.secondary">No members yet</Typography>}
        </Stack>

        <Typography variant="subtitle2" sx={{ mt: 2 }}>Add member</Typography>
        <Stack direction="row" gap={1} sx={{ mt: 1 }}>
          <TextField
            select
            label="Agent"
            value={newMember}
            onChange={e => setNewMember(e.target.value)}
            SelectProps={{ native: true }}
            fullWidth
          >
            <option value=""></option>
            {candidates.map(n => <option key={n} value={n}>{n}</option>)}
          </TextField>
          <Button variant="contained" onClick={addMember} disabled={!newMember || isLoading}>Add</Button>
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Close</Button>
      </DialogActions>
    </Dialog>
  );
}
