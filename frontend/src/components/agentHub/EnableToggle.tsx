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
