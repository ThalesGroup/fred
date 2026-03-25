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
import { Drawer } from "@mui/material";
import { AnyAgent } from "../../common/agent";
import { AgentCreateEditForm } from "./AgentCreateEditForm";

export type AgentCreateEditDrawerProps = {
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

export function AgentCreateEditDrawer({
  open,
  agent,
  canDelete,
  teamId,
  onClose,
  onSaved,
  onDeleted,
}: AgentCreateEditDrawerProps) {
  return (
    <Drawer
      anchor="right"
      open={open}
      onClose={onClose}
      PaperProps={{ sx: { width: { xs: "100%", sm: 720, md: 880 } } }}
    >
      <AgentCreateEditForm
        key={agent?.id ?? "create"}
        agent={agent}
        canDelete={canDelete}
        teamId={teamId}
        onClose={onClose}
        onSaved={onSaved}
        onDeleted={onDeleted}
      />
    </Drawer>
  );
}
