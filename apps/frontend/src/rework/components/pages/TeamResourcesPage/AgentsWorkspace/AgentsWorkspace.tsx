// Copyright Thales 2026
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

import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import ResourceExplorer from "@shared/organisms/ResourceExplorer/ResourceExplorer.tsx";
import type { DataTableColumn } from "@shared/molecules/DataTable/DataTable.tsx";
import Icon from "@shared/atoms/Icon/Icon.tsx";
import FilesystemWorkspace from "../FilesystemWorkspace/FilesystemWorkspace.tsx";
import { useGetTeamAgentInstancesControlPlaneV1TeamsTeamIdAgentInstancesGetQuery } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import {
  type FilesystemResourceInfoResult,
  useLsQuery,
} from "../../../../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { FOLDER_ICON } from "../../../../utils/fileIconSpec.ts";
import styles from "./AgentsWorkspace.module.css";

interface AgentInstance {
  agent_instance_id: string;
  display_name: string;
}

/**
 * Map each agent_instance_id to a display label, disambiguating identical
 * names render-time (G6): when two instances share a display_name, both get
 * a short `· {id-prefix}` suffix so no two folders render the same label.
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

interface AgentsWorkspaceProps {
  /** Canonical fs team id (resolves "personal" → personal-<uid>); keys both registry + /fs. */
  fsTeamId: string;
  /** Current user id — agent files live under agents/{instance}/users/{uid}. */
  userId: string;
}

/**
 * The "Agents" root (FILES-04 §3/§4), one unified table (RFC §13.7 FRONT-09.H,
 * step 3 of the "other three tabs" plan). Its root is virtual — not a real
 * `/fs` path — listing the agent instances that have files for the current
 * user, one folder row per agent, labelled by the agent's display name
 * (never the uuid). Clicking one navigates "into" it exactly like any other
 * folder: from there on it's `FilesystemWorkspace` browsing the agent's real
 * per-user file space (`agents/{instance}/users/{uid}`, hiding those two
 * segments as separate navigable levels, same shortcut the old tree used),
 * with `onNavigateAboveRoot` wired back to this virtual root so the
 * breadcrumb's "Agents" segment (or the back button, at the agent's own top
 * level) returns here — one continuous table the whole time.
 */
export default function AgentsWorkspace({ fsTeamId, userId }: AgentsWorkspaceProps) {
  const { t } = useTranslation();
  const agentsRoot = `teams/${fsTeamId}/agents`;
  const [selectedAgent, setSelectedAgent] = useState<{ instanceId: string; label: string } | null>(null);

  const { data: instances, isLoading: namesLoading } =
    useGetTeamAgentInstancesControlPlaneV1TeamsTeamIdAgentInstancesGetQuery({ teamId: fsTeamId });
  const { data, isLoading: dirsLoading } = useLsQuery({ path: agentsRoot });
  // Same backend typing gap as FilesystemWorkspace (LsApiResponse = any).
  const entries = (Array.isArray(data) ? data : []) as FilesystemResourceInfoResult[];
  const folders = useMemo(() => entries.filter((entry) => entry.type === "directory"), [entries]);

  const labelById = useMemo(() => buildAgentLabels(instances ?? []), [instances]);
  // Wait for names before labelling, so a real agent never flashes "Removed agent".
  const loading = namesLoading || dirsLoading;

  if (selectedAgent) {
    return (
      <FilesystemWorkspace
        root={`${agentsRoot}/${selectedAgent.instanceId}/users/${userId}`}
        rootLabel={selectedAgent.label}
        emptyHintKey="rework.resources.empty.agentFiles"
        onNavigateAboveRoot={() => setSelectedAgent(null)}
      />
    );
  }

  const columns: DataTableColumn<FilesystemResourceInfoResult>[] = [
    {
      label: t("rework.resources.columns.name"),
      size: "2fr",
      cellRenderer: (entry) => {
        const label = labelById.get(entry.path) ?? t("rework.resources.roots.removedAgent");
        return (
          <button
            type="button"
            className={styles.nameButton}
            onClick={() => setSelectedAgent({ instanceId: entry.path, label })}
          >
            <span className={styles.rowIcon} style={{ color: FOLDER_ICON.color }}>
              <Icon category="outlined" type={FOLDER_ICON.type} filled={FOLDER_ICON.filled} />
            </span>
            <span>{label}</span>
          </button>
        );
      },
    },
    { label: t("rework.resources.columns.size"), size: "6.5rem", cellRenderer: () => <span>—</span> },
    { label: t("rework.resources.columns.created"), size: "9rem", cellRenderer: () => <span>—</span> },
    { label: t("rework.resources.columns.author"), size: "9rem", cellRenderer: () => <span>—</span> },
    { label: "", size: "6rem", cellRenderer: () => null },
  ];

  return (
    <ResourceExplorer<FilesystemResourceInfoResult>
      breadcrumb={{
        segments: [{ label: t("rework.resources.roots.agents") }],
        onBack: () => {},
        canGoBack: false,
        backLabel: t("rework.resources.action.back"),
      }}
      selectable={false}
      loading={loading}
      loadingMessage={t("rework.resources.loading")}
      empty={!loading && folders.length === 0}
      emptyMessage={t("rework.resources.empty.agents")}
      columns={columns}
      rows={folders}
      rowKey={(entry) => entry.path}
    />
  );
}
