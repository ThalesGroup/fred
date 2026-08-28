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

import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";
import ServiceNotice from "@shared/molecules/ServiceNotice/ServiceNotice.tsx";
import { SettingChip } from "@shared/atoms/SettingChip/SettingChip.tsx";
import { Spinner } from "@shared/atoms/Spinner/Spinner.tsx";
import ProgressBar from "@shared/atoms/ProgressBar/ProgressBar.tsx";
import ButtonGroup from "@shared/atoms/ButtonGroup/ButtonGroup.tsx";
import type { ButtonGroupItemProps } from "@shared/atoms/ButtonGroup/ButtonGroupItem/ButtonGroupItem.tsx";
import { getQueryUiState } from "@core/utils/queryUiState.ts";
import {
  useListAllTagsKnowledgeFlowV1TagsGetQuery,
  useGetCorpusTypeStatsKnowledgeFlowV1TagsStatsGetQuery,
  useTypeStatsKnowledgeFlowV1FsStatsPathGetQuery,
} from "../../../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { useGetTeamQuery } from "../../../../slices/controlPlane/controlPlaneApiEnhancements";
import { useFrontendBootstrap } from "../../../../hooks/useFrontendBootstrap.ts";
import { useTeamCapabilities } from "@hooks/useTeamCapabilities.ts";
import { KeyCloakService } from "../../../../security/KeycloakService.ts";
import { isPersonalTeamId, personalTeamId } from "@shared/utils/teamId.ts";
import { formatBytes } from "@shared/utils/formatBytes.ts";
import DocumentWorkspace from "./DocumentWorkspace/DocumentWorkspace.tsx";
import FilesystemWorkspace from "./FilesystemWorkspace/FilesystemWorkspace.tsx";
import AgentsWorkspace from "./AgentsWorkspace/AgentsWorkspace.tsx";
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
 *
 * Mon espace/Espace d'équipe/Agents are gated behind the platform-wide
 * `enableAllResourceSpaces` feature flag (`platform.frontend.feature_flags`
 * in `configuration.yaml`, default off) — the team isn't yet confident these
 * three spaces pull their weight next to Corpus d'équipe, so only Corpus is
 * reachable until the flag is turned on. The other three tabs' code stays
 * fully in place either way; only their entries in the tab switcher are
 * conditional.
 */
export default function TeamResourcesPage() {
  const { t } = useTranslation();
  const { teamId = "" } = useParams<{ teamId: string }>();
  // isPersonalTeamId alone is authoritative (handles both the bare "personal"
  // alias and the canonical "personal-<uid>" id — see its own doc comment).
  // An earlier `|| teamId === activeTeam?.id` fallback dates from before real
  // multi-team support existed, when "active team" and "personal space" were
  // the same concept — it silently misclassified any real team as personal
  // whenever you viewed the Resources page for your currently active team,
  // hiding "Espace partagé" for a legitimate team.
  const isPersonalTeam = isPersonalTeamId(teamId);
  const userId = KeyCloakService.GetUserId() ?? "";
  // The URL may carry the bare "personal" alias, but /fs ReBAC resolves against the
  // canonical personal-<uid> resource id. Canonicalize before building any /fs path.
  const fsTeamId = teamId === "personal" ? personalTeamId(userId) : teamId;
  const userRoot = `teams/${fsTeamId}/users/${userId}`;
  const sharedRoot = `teams/${fsTeamId}/shared`;
  // `refetch` as well as `data`: the storage-quota meter below reads this team
  // row's `current_resources_storage_size`, but every write to it comes from
  // the knowledge-flow API (upload charges it, delete releases it) — a
  // different RTK Query instance, whose tag invalidations cannot reach this
  // control-plane cache entry. Without a manual refetch on the workspace's own
  // change signal the meter keeps showing the figure it had at mount.
  const { data: team, refetch: refetchTeam, isUninitialized: teamUninitialized } = useGetTeamQuery({ teamId });
  const { canUpdateResources: canCreateFolder } = useTeamCapabilities(team);
  const { bootstrap } = useFrontendBootstrap();
  const enableAllResourceSpaces = bootstrap?.feature_flags?.enableAllResourceSpaces ?? false;

  const [activeTab, setActiveTab] = useState<ResourceRootTab>("resources");
  const [statsOpen, setStatsOpen] = useState(false);
  // "Espace partagé" only exists for a real team — if the active team turns out to be
  // personal (e.g. navigating here via a stale tab from a different team), fall back
  // rather than leave a tab selected that's about to disappear from the switcher.
  useEffect(() => {
    if (isPersonalTeam && activeTab === "team") setActiveTab("resources");
  }, [isPersonalTeam, activeTab]);

  const rootTabs: { value: ResourceRootTab; label: string }[] = [
    { value: "resources", label: t("rework.resources.roots.resources") },
    ...(enableAllResourceSpaces
      ? [
          { value: "mine" as const, label: t("rework.resources.roots.mine") },
          ...(isPersonalTeam ? [] : [{ value: "team" as const, label: t("rework.resources.roots.team") }]),
          { value: "agents" as const, label: t("rework.resources.roots.agents") },
        ]
      : []),
  ];
  const rootTabItems: ButtonGroupItemProps[] = rootTabs.map((tab) => ({ label: tab.label }));
  const activeTabIndex = rootTabs.findIndex((tab) => tab.value === activeTab);

  // Usage-by-type stats (§13.5/13.7 FRONT-09.I) — one query per tab's data source,
  // each skipped unless it's the active tab so switching tabs never fires every query
  // at once. "Agents" has no single filesystem root (its table's root is virtual,
  // fanning out per agent instance — see AgentsWorkspace) so it has no stats source
  // yet — RFC §13.5.
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
    return (
      <div className={styles.loadingState}>
        <Spinner size={20} />
        {t("rework.resources.loading")}
      </div>
    );
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
          <h1 className={styles.title}>
            {isPersonalTeam ? t("rework.resources.pageTitlePersonal") : t("rework.resources.pageTitle")}
          </h1>
          <p className={styles.subtitle}>
            {isPersonalTeam ? t("rework.resources.pageSubtitlePersonal") : t("rework.resources.pageSubtitle")}
          </p>
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

      {rootTabs.length > 1 && (
        <ButtonGroup
          items={rootTabItems}
          size="2xs"
          color="secondary"
          variant="tabs"
          aria-label={t("rework.resources.rootsAria")}
          selectedIndex={activeTabIndex}
          onSelectedIndexChange={(index) => setActiveTab(rootTabs[index].value)}
        />
      )}

      <div className={styles.panel}>
        {activeTab === "resources" && (
          <DocumentWorkspace
            teamId={teamId}
            isPersonalTeam={isPersonalTeam}
            // Guarded: DocumentWorkspace's useNotifyOnNewTaskTarget does a
            // catch-up fire on mount for any task target already in the
            // store — in the same commit where activeTab just switched to
            // "resources", DocumentWorkspace (child) mounts and can run this
            // effect before these queries' own subscribing effects (parent)
            // have dispatched their initial fetch, since React flushes child
            // effects before parent effects. Calling .refetch() on a query
            // that was never started throws and takes down the whole app.
            // Safe to just skip in that case — the query's own mount fetch
            // is already about to run.
            onDocumentsChanged={() => {
              if (!corpusStats.isUninitialized) void corpusStats.refetch();
              if (!teamUninitialized) void refetchTeam();
            }}
          />
        )}

        {activeTab === "mine" && <FilesystemWorkspace root={userRoot} rootLabel={t("rework.resources.roots.mine")} />}

        {activeTab === "team" && !isPersonalTeam && (
          <FilesystemWorkspace
            root={sharedRoot}
            rootLabel={t("rework.resources.roots.team")}
            canWrite={canCreateFolder}
          />
        )}

        {activeTab === "agents" && <AgentsWorkspace fsTeamId={fsTeamId} userId={userId} />}
      </div>
    </div>
  );
}
