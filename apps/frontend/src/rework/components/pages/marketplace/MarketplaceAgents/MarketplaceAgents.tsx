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
import Chip from "@shared/atoms/Chip/Chip.tsx";
import Icon from "@shared/atoms/Icon/Icon.tsx";
import { Spinner } from "@shared/atoms/Spinner/Spinner.tsx";
import PageEmptyState from "@shared/molecules/PageEmptyState/PageEmptyState.tsx";
import SearchInput from "@shared/molecules/SearchInput/SearchInput.tsx";
import ServiceNotice from "@shared/molecules/ServiceNotice/ServiceNotice.tsx";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import MarketplaceAgentCard from "@shared/organisms/AgentCard/MarketplaceAgentCard.tsx";
import { getQueryUiState } from "@core/utils/queryUiState.ts";
import { stripDiacritics } from "../../../../utils/stripDiacritics.ts";
import {
  useLikeMarketplaceAgentMutation,
  useMarketplaceAgentsQuery,
  useUnlikeMarketplaceAgentMutation,
} from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import type { MarketplaceAgentSummary } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import ImportAgentDialog from "./ImportAgentDialog/ImportAgentDialog.tsx";
import MarketplaceAgentDialog from "./MarketplaceAgentDialog/MarketplaceAgentDialog.tsx";
import styles from "./MarketplaceAgents.module.scss";

const fold = (text: string) => stripDiacritics(text).toLowerCase();

/** Every published agent, in server order (newest first). Search and the team
 * filter run client-side so the page can tell "nothing published yet" from
 * "nothing matches". */
export default function MarketplaceAgents() {
  const { t } = useTranslation();
  const { showError } = useToast();
  const [search, setSearch] = useState("");
  const [teamFilter, setTeamFilter] = useState<{ id: string; name: string } | null>(null);
  const [viewing, setViewing] = useState<MarketplaceAgentSummary | null>(null);
  const [importing, setImporting] = useState<MarketplaceAgentSummary | null>(null);
  const [pendingLikes, setPendingLikes] = useState<Set<string>>(new Set());

  const { data: agents = [], isLoading, isUninitialized, isError } = useMarketplaceAgentsQuery({});
  const [like] = useLikeMarketplaceAgentMutation();
  const [unlike] = useUnlikeMarketplaceAgentMutation();

  const filtered = useMemo(() => {
    const q = fold(search.trim());
    return agents.filter((agent) => {
      const matchSearch =
        !q ||
        [agent.display_name, agent.role, agent.description ?? "", agent.team_name ?? ""].some((field) =>
          fold(field).includes(q),
        );
      return matchSearch && (!teamFilter || agent.team_id === teamFilter.id);
    });
  }, [agents, search, teamFilter]);

  const toggleLike = async (agent: MarketplaceAgentSummary) => {
    setPendingLikes((prev) => new Set(prev).add(agent.entry_id));
    try {
      await (agent.liked_by_me ? unlike : like)({ entryId: agent.entry_id }).unwrap();
    } catch {
      showError({ summary: t("rework.marketplace.agents.likeError") });
    } finally {
      setPendingLikes((prev) => {
        const next = new Set(prev);
        next.delete(agent.entry_id);
        return next;
      });
    }
  };

  const queryState = getQueryUiState({ isLoading, isUninitialized, isError });
  if (queryState === "loading") {
    return (
      <div className={styles.loadingState}>
        <Spinner size={20} />
        {t("rework.marketplace.agents.loading")}
      </div>
    );
  }
  if (queryState === "error") {
    return (
      <ServiceNotice
        icon="cloud_off"
        title={t("rework.serviceNotice.controlPlane.title")}
        description={t("rework.serviceNotice.controlPlane.description")}
        centered
      />
    );
  }

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <h1 className={styles.title}>{t("rework.marketplace.agents.title")}</h1>
        {agents.length > 0 && (
          <div className={styles.search}>
            <SearchInput
              value={search}
              onChange={setSearch}
              placeholder={t("rework.marketplace.agents.searchPlaceholder")}
              clearAriaLabel={t("rework.marketplace.agents.clearSearch")}
              size="small"
            />
          </div>
        )}
      </div>
      {teamFilter && (
        <div className={styles.filterChips}>
          <Chip
            label={t("rework.marketplace.agents.teamFilter.chip", { team: teamFilter.name })}
            leading={<Icon category="outlined" type="groups" />}
            onRemove={() => setTeamFilter(null)}
            removeAriaLabel={t("rework.marketplace.agents.teamFilter.clear", { team: teamFilter.name })}
          />
        </div>
      )}

      {agents.length === 0 ? (
        <PageEmptyState
          icon="storefront"
          message={t("rework.marketplace.agents.empty.title")}
          description={t("rework.marketplace.agents.empty.description")}
        />
      ) : filtered.length === 0 ? (
        <PageEmptyState
          icon="search_off"
          message={t("rework.marketplace.agents.emptySearch.title")}
          description={t("rework.marketplace.agents.emptySearch.description")}
        />
      ) : (
        <div className={styles.agentList}>
          {filtered.map((agent) => (
            <MarketplaceAgentCard
              key={agent.entry_id}
              agent={agent}
              likePending={pendingLikes.has(agent.entry_id)}
              onOpen={() => setViewing(agent)}
              onToggleLike={() => void toggleLike(agent)}
              onImport={() => setImporting(agent)}
              onTeamClick={() => setTeamFilter({ id: agent.team_id, name: agent.team_name || agent.team_id })}
            />
          ))}
        </div>
      )}

      <MarketplaceAgentDialog
        agent={viewing}
        onImport={(agent) => {
          setViewing(null);
          setImporting(agent);
        }}
        onClose={() => setViewing(null)}
      />
      <ImportAgentDialog agent={importing} onClose={() => setImporting(null)} />
    </div>
  );
}
