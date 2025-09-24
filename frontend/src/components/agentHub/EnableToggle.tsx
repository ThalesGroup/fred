// src/components/agentHub/EnableToggle.tsx
import { Button } from "@mui/material";
import { AnyAgent } from "../../common/agent";
import { useAgentUpdater } from "../../hooks/useAgentUpdater";

export function EnableToggle({ agent, onSaved }: { agent: AnyAgent; onSaved?: () => void }) {
  const { updateEnabled, isLoading } = useAgentUpdater();
  const toggle = async () => {
    await updateEnabled(agent, !agent.enabled);
    onSaved?.();
  };
  return (
    <Button size="small" variant="outlined" onClick={toggle} disabled={isLoading}>
      {agent.enabled ? "Disable" : "Enable"}
    </Button>
  );
}
