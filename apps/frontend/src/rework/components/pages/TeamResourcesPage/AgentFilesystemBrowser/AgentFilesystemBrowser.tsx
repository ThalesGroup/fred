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
  const { t } = useTranslation();
  const agentsRoot = `teams/${fsTeamId}/agents`;
  const { data: instances, isLoading: namesLoading } =
    useGetTeamAgentInstancesControlPlaneV1TeamsTeamIdAgentInstancesGetQuery({ teamId: fsTeamId });
  const { data: agentDirs, isLoading: dirsLoading } = useLsQuery({ path: agentsRoot });

  // Wait for names before labelling, so a real agent never flashes "Removed agent".
  if (namesLoading) return null;

  const labelById = buildAgentLabels(instances ?? []);
  const folders = (Array.isArray(agentDirs) ? (agentDirs as FsEntry[]) : []).filter((entry) => isDirectory(entry.type));

  // No agent has files yet: explain what the area is for instead of rendering nothing.
  if (!dirsLoading && folders.length === 0) {
    return <div className={styles.hint}>{t("rework.resources.empty.agents")}</div>;
  }

  return (
    <>
      {folders.map((folder) => (
        <AgentFolder
          key={folder.path}
          name={labelById.get(folder.path)}
          filesRoot={`${agentsRoot}/${folder.path}/users/${userId}`}
          instanceId={folder.path}
        />
      ))}
    </>
  );
}

interface AgentInstance {
  agent_instance_id: string;
  display_name: string;
}

/**
 * Map each agent_instance_id to a display label, disambiguating identical names
 * render-time (G6): when two instances share a display_name, both get a short
 * `· {id-prefix}` suffix so no two folders render the same label.
 */
function buildAgentLabels(instances: AgentInstance[]): Map<string, string> {
  const counts = new Map<string, number>();
  for (const instance of instances) {
    counts.set(instance.display_name, (counts.get(instance.display_name) ?? 0) + 1);
  }
  return new Map(
    instances.map((instance) => {
      const duplicated = (counts.get(instance.display_name) ?? 0) > 1;
      const label = duplicated
        ? `${instance.display_name} · ${instance.agent_instance_id.slice(0, 6)}`
        : instance.display_name;
      return [instance.agent_instance_id, label];
    }),
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
      {/* baseDepth=1 indents the agent's files one level under its folder, matching the rest of the tree. */}
      {expanded && (
        <TeamFilesystemBrowser root={filesRoot} baseDepth={1} emptyHintKey="rework.resources.empty.agentFiles" />
      )}
    </>
  );
}
