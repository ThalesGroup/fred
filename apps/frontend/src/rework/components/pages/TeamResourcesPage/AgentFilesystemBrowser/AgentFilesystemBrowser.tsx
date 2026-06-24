// Copyright Thales 2026
//
// Licensed under the Apache License, Version 2.0 (the "License");
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { FolderRow } from "@shared/molecules/FolderRow/FolderRow.tsx";
import { useGetTeamAgentInstancesControlPlaneV1TeamsTeamIdAgentInstancesGetQuery } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import { useLsQuery } from "../../../../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import TeamFilesystemBrowser from "../TeamFilesystemBrowser/TeamFilesystemBrowser.tsx";
import styles from "./AgentFilesystemBrowser.module.css";

/** One /fs/list entry (only `path` = agent_instance_id, and `type` matter here). */
interface FsEntry {
  path: string;
  type?: string;
}

function isDirectory(type: string | undefined): boolean {
  return typeof type === "string" && type.toLowerCase().includes("directory");
}

interface AgentFilesystemBrowserProps {
  /** Canonical fs team id (resolves "personal" → personal-<uid>); keys both registry + /fs. */
  fsTeamId: string;
  /** Current user id — agent files live under agents/{instance}/users/{uid}. */
  userId: string;
}

/**
 * The "Agents" root (FILES-04 §3/§4). Lists the agent instances that have files for the
 * current user, labelled by the agent's display name (resolved from the control-plane
 * registry, never the uuid). Expanding an agent jumps straight to its per-user file space,
 * hiding the agents/{id}/users/{uid} navigation levels, and reuses the standard file tree
 * (download/delete + the généré provenance badge).
 */
export default function AgentFilesystemBrowser({ fsTeamId, userId }: AgentFilesystemBrowserProps) {
  const agentsRoot = `teams/${fsTeamId}/agents`;
  const { data: instances, isLoading: namesLoading } =
    useGetTeamAgentInstancesControlPlaneV1TeamsTeamIdAgentInstancesGetQuery({ teamId: fsTeamId });
  const { data: agentDirs } = useLsQuery({ path: agentsRoot });

  // Wait for names before labelling, so a real agent never flashes "Removed agent".
  if (namesLoading) return null;

  const nameById = new Map((instances ?? []).map((instance) => [instance.agent_instance_id, instance.display_name]));
  const folders = (Array.isArray(agentDirs) ? (agentDirs as FsEntry[]) : []).filter((entry) => isDirectory(entry.type));

  return (
    <>
      {folders.map((folder) => (
        <AgentFolder
          key={folder.path}
          name={nameById.get(folder.path)}
          filesRoot={`${agentsRoot}/${folder.path}/users/${userId}`}
          instanceId={folder.path}
        />
      ))}
    </>
  );
}

interface AgentFolderProps {
  instanceId: string;
  /** Display name from the registry; undefined when the instance was deleted. */
  name: string | undefined;
  /** teams/{team}/agents/{instance}/users/{uid} — the agent's per-user file space. */
  filesRoot: string;
}

/** One agent folder (labelled by name) whose children are the agent's per-user files. */
function AgentFolder({ instanceId, name, filesRoot }: AgentFolderProps) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);

  return (
    <>
      <FolderRow
        id={instanceId}
        name={name ?? t("rework.resources.roots.removedAgent")}
        expanded={expanded}
        onToggle={() => setExpanded((value) => !value)}
      />
      {expanded && (
        <div className={styles.nested}>
          <TeamFilesystemBrowser root={filesRoot} />
        </div>
      )}
    </>
  );
}
