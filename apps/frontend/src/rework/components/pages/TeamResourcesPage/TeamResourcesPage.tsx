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

import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";
import ServiceNotice from "@shared/molecules/ServiceNotice/ServiceNotice.tsx";
import IconButton from "@shared/atoms/IconButton/IconButton.tsx";
import { SettingChip } from "@shared/atoms/SettingChip/SettingChip.tsx";
import ProgressBar from "@shared/atoms/ProgressBar/ProgressBar.tsx";
import Tabs, { type TabItem } from "@shared/molecules/Tabs/Tabs.tsx";
import { getQueryUiState } from "@core/utils/queryUiState.ts";
import { useFrontendBootstrap } from "../../../../hooks/useFrontendBootstrap.ts";
import {
  useListAllTagsKnowledgeFlowV1TagsGetQuery,
  useGetCorpusTypeStatsKnowledgeFlowV1TagsStatsGetQuery,
  useTypeStatsKnowledgeFlowV1FsStatsPathGetQuery,
} from "../../../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { useGetTeamQuery } from "../../../../slices/controlPlane/controlPlaneApiEnhancements";
import { useTeamCapabilities } from "@hooks/useTeamCapabilities.ts";
import { KeyCloakService } from "../../../../security/KeycloakService.ts";
import { isPersonalTeamId, personalTeamId } from "@shared/utils/teamId.ts";
import { formatBytes } from "../../../utils/formatBytes.ts";
import DocumentWorkspace, { type DocumentWorkspaceHandle } from "./DocumentWorkspace/DocumentWorkspace.tsx";
import TeamFilesystemBrowser from "./TeamFilesystemBrowser/TeamFilesystemBrowser.tsx";
import AgentFilesystemBrowser from "./AgentFilesystemBrowser/AgentFilesystemBrowser.tsx";
import WorkspaceRoot from "./WorkspaceRoot/WorkspaceRoot.tsx";
import FsRootMeta from "./FsRootMeta/FsRootMeta.tsx";
import FsRootAddMenu from "./FsRootAddMenu/FsRootAddMenu.tsx";
import ResourceStatsCards from "./ResourceStatsCards/ResourceStatsCards.tsx";
import styles from "./TeamResourcesPage.module.css";

type ResourceRootTab = "resources" | "mine" | "team" | "agents";

/**
 * Official rework workspace page (FILES-04). A single tree with four differentiated roots:
 * - Resources: document ingestion into the searchable corpus. Files must live in a library
 *   (folder/tag) to be indexed, so the root only creates libraries — no top-level upload.
 * - Mon espace: the user's personal-in-team files (teams/{team}/users/{uid}, via /fs)
 * - Espace d'équipe: the team-shared files (teams/{team}/shared, via /fs)
 * - Agents: per-agent generated files (teams/{team}/agents/{instance}/users/{uid}, via /fs)
 */
export default function TeamResourcesPage() {
  const { t } = useTranslation();
  const { teamId = "" } = useParams<{ teamId: string }>();
  const { activeTeam } = useFrontendBootstrap();
  const isPersonalTeam = isPersonalTeamId(teamId) || teamId === activeTeam?.id;
  const userId = KeyCloakService.GetUserId() ?? "";
  const teamName = activeTeam?.name ?? teamId;
  // The URL may carry the bare "personal" alias, but /fs ReBAC resolves against the
  // canonical personal-<uid> resource id. Canonicalize before building any /fs path.
  const fsTeamId = teamId === "personal" ? personalTeamId(userId) : teamId;
  const userRoot = `teams/${fsTeamId}/users/${userId}`;
  const sharedRoot = `teams/${fsTeamId}/shared`;
  const corpusRef = useRef<DocumentWorkspaceHandle>(null);
  const { data: team } = useGetTeamQuery({ teamId });
  const { canUpdateResources: canCreateFolder } = useTeamCapabilities(team);

  const [activeTab, setActiveTab] = useState<ResourceRootTab>("resources");
  const [statsOpen, setStatsOpen] = useState(true);
  // "Espace partagé" only exists for a real team — if the active team turns out to be
  // personal (e.g. navigating here via a stale tab from a different team), fall back
  // rather than leave a tab selected that's about to disappear from the switcher.
  useEffect(() => {
    if (isPersonalTeam && activeTab === "team") setActiveTab("resources");
  }, [isPersonalTeam, activeTab]);

  const rootTabs: TabItem<ResourceRootTab>[] = [
    { value: "resources", label: t("rework.resources.roots.resources") },
    { value: "mine", label: t("rework.resources.roots.mine") },
    ...(isPersonalTeam ? [] : [{ value: "team" as const, label: t("rework.resources.roots.team") }]),
    { value: "agents", label: t("rework.resources.roots.agents") },
  ];

  // Usage-by-type stats (§13.5/13.7 FRONT-09.I) — one query per tab's data source,
  // each skipped unless it's the active tab so switching tabs never fires every query
  // at once. "Agents" has no single filesystem root (it fans out per agent instance,
  // see AgentFilesystemBrowser) so it has no stats source yet — RFC §13.5.
  const corpusStats = useGetCorpusTypeStatsKnowledgeFlowV1TagsStatsGetQuery(
    { teamId: fsTeamId },
    { skip: activeTab !== "resources" },
  );
  const mineStats = useTypeStatsKnowledgeFlowV1FsStatsPathGetQuery({ path: userRoot }, { skip: activeTab !== "mine" });
  const teamStats = useTypeStatsKnowledgeFlowV1FsStatsPathGetQuery(
    { path: sharedRoot },
    { skip: activeTab !== "team" },
  );
  const activeStats =
    activeTab === "resources"
      ? corpusStats
      : activeTab === "mine"
        ? mineStats
        : activeTab === "team"
          ? teamStats
          : null;

  // KF health gate — identical pattern to the old KnowledgeHubPage.
  const { isError, isLoading, isFetching, isUninitialized } = useListAllTagsKnowledgeFlowV1TagsGetQuery({
    type: "document",
    limit: 1,
    offset: 0,
  });
  const kfState = getQueryUiState({ isLoading, isFetching, isUninitialized, isError });

  if (kfState === "loading") {
    return <div className={styles.loadingState}>{t("rework.resources.loading")}</div>;
  }
  if (kfState === "error") {
    return (
      <ServiceNotice
        icon="cloud_off"
        title={t("rework.serviceNotice.knowledgeService.title")}
        description={t("rework.serviceNotice.knowledgeService.description")}
        centered
      />
    );
  }

  const hasQuota = team?.max_resources_storage_size != null;

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div>
          <h1 className={styles.title}>{t("rework.resources.pageTitle")}</h1>
          <p className={styles.subtitle}>{t("rework.resources.pageSubtitle")}</p>
        </div>
        <div className={styles.headerEnd}>
          <SettingChip
            label={t("rework.resources.stats.toggle")}
            icon={{ category: "outlined", type: "bar_chart" }}
            open={statsOpen}
            activeColor="secondary"
            onClick={() => setStatsOpen((value) => !value)}
          />
          {hasQuota && (
            <div className={styles.quota}>
              <div className={styles.quotaLabelRow}>
                <span className={styles.quotaLabel}>{t("rework.resources.storageQuota")}</span>
                <span className={styles.quotaValue}>
                  {formatBytes(team!.current_resources_storage_size ?? 0)} /{" "}
                  {formatBytes(team!.max_resources_storage_size!)}
                </span>
              </div>
              <ProgressBar
                theme="primary"
                current={team!.current_resources_storage_size ?? 0}
                max={team!.max_resources_storage_size!}
              />
            </div>
          )}
        </div>
      </header>

      {statsOpen && activeTab !== "agents" && (
        <ResourceStatsCards
          entries={activeStats?.data?.entries}
          isLoading={activeStats?.isLoading ?? false}
          isError={activeStats?.isError ?? false}
        />
      )}

      <Tabs<ResourceRootTab> tabs={rootTabs} value={activeTab} onChange={setActiveTab} />

      <div className={styles.panel}>
        {activeTab === "resources" && (
          <WorkspaceRoot
            icon={{ category: "outlined", type: "database" }}
            title={t("rework.resources.roots.resources")}
            hint={t("rework.resources.hints.resources")}
            meta={<span className={styles.badge}>{t("rework.resources.roots.indexed")}</span>}
            collapsible={false}
            action={
              canCreateFolder ? (
                <IconButton
                  color="on-surface"
                  variant="outlined"
                  size="xs"
                  icon={{ category: "outlined", type: "create_new_folder" }}
                  aria-label={t("rework.resources.menu.newFolder")}
                  title={t("rework.resources.menu.newFolder")}
                  onClick={() => corpusRef.current?.openNewFolder()}
                />
              ) : undefined
            }
          >
            <DocumentWorkspace ref={corpusRef} teamId={teamId} isPersonalTeam={isPersonalTeam} />
          </WorkspaceRoot>
        )}

        {activeTab === "mine" && (
          <WorkspaceRoot
            icon={{ category: "outlined", type: "person" }}
            title={t("rework.resources.roots.mine")}
            hint={t("rework.resources.hints.mine")}
            collapsible={false}
            meta={
              <FsRootMeta
                root={userRoot}
                nature={
                  isPersonalTeam
                    ? t("rework.resources.roots.privatePersonal")
                    : t("rework.resources.roots.private", { team: teamName })
                }
              />
            }
            action={<FsRootAddMenu root={userRoot} />}
          >
            <TeamFilesystemBrowser root={userRoot} />
          </WorkspaceRoot>
        )}

        {activeTab === "team" && !isPersonalTeam && (
          <WorkspaceRoot
            icon={{ category: "outlined", type: "groups" }}
            title={t("rework.resources.roots.team")}
            hint={t("rework.resources.hints.team")}
            collapsible={false}
            meta={<FsRootMeta root={sharedRoot} />}
            action={canCreateFolder ? <FsRootAddMenu root={sharedRoot} /> : undefined}
          >
            <TeamFilesystemBrowser root={sharedRoot} canWrite={canCreateFolder} />
          </WorkspaceRoot>
        )}

        {activeTab === "agents" && (
          <WorkspaceRoot
            icon={{ category: "outlined", type: "auto_awesome" }}
            title={t("rework.resources.roots.agents")}
            hint={t("rework.resources.hints.agents")}
            collapsible={false}
          >
            <AgentFilesystemBrowser fsTeamId={fsTeamId} userId={userId} />
          </WorkspaceRoot>
        )}
      </div>
    </div>
  );
}
