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
import {
  Button,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  InputLabel,
  MenuItem,
  Select,
  Stack,
  Typography,
} from "@mui/material";
import { useMemo, useState } from "react";
import { AnyAgent } from "../../common/agent";
import { useAgentUpdater } from "../../hooks/useAgentUpdater";
import { Leader } from "../../slices/agentic/agenticOpenApi";

type Props = {
  open: boolean;
  leader: (Leader & { type: "leader" }) | null;
  allAgents: AnyAgent[];
  onClose: () => void;
  onSaved?: () => void;
};

export function CrewEditor({ open, leader, allAgents, onClose, onSaved }: Props) {
  const { updateLeaderCrew, isLoading } = useAgentUpdater();
  const [newMember, setNewMember] = useState("");

  const crew = leader?.crew || [];
  const candidates = useMemo(
    () => allAgents.filter((a) => a.type === "agent" && !crew.includes(a.name)).map((a) => a.name),
    [allAgents, crew],
  );

  const removeMember = async (name: string) => {
    if (!leader) return;
    const next = crew.filter((n) => n !== name);
    await updateLeaderCrew(leader, next);
    onSaved?.();
    onClose(); // Close after removing a member
  };

  const addMember = async () => {
    if (!leader || !newMember) return;
    const next = Array.from(new Set([...crew, newMember]));
    await updateLeaderCrew(leader, next);
    setNewMember("");
    onSaved?.();
    onClose(); // Close after adding a member
  };

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle>Crew for {leader?.name}</DialogTitle>
      <DialogContent>
        <Typography variant="subtitle2">Current members</Typography>
        <Stack direction="row" flexWrap="wrap" gap={1} sx={{ my: 1 }}>
          {crew.length ? (
            crew.map((n) => <Chip key={n} label={n} onDelete={() => removeMember(n)} disabled={isLoading} />)
          ) : (
            <Typography variant="body2" color="text.secondary">
              No members yet
            </Typography>
          )}
        </Stack>

        <Typography variant="subtitle2" sx={{ mt: 2 }}>
          Add member
        </Typography>
        <Stack direction="row" gap={1} sx={{ mt: 1 }}>
          <FormControl fullWidth>
            <InputLabel id="select-agent-label">Agent</InputLabel>
            <Select
              labelId="select-agent-label"
              id="select-agent"
              value={newMember}
              label="Agent"
              onChange={(e) => setNewMember(e.target.value as string)}
            >
              <MenuItem value="">
                <em>None</em>
              </MenuItem>
              {candidates.map((n) => (
                <MenuItem key={n} value={n}>
                  {n}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
          <Button variant="contained" onClick={addMember} disabled={!newMember || isLoading}>
            Add
          </Button>
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Close</Button>
      </DialogActions>
    </Dialog>
  );
}
