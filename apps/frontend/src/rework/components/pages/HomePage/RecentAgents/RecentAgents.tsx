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

import { useTranslation } from "react-i18next";
import Icon from "@shared/atoms/Icon/Icon.tsx";
import Button from "@shared/atoms/Button/Button.tsx";
import { isPersonalTeamId } from "@shared/utils/teamId.ts";
import { useHomeAgentsQuery } from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import { useFrontendBootstrap } from "../../../../../hooks/useFrontendBootstrap";
import AgentCard from "@shared/organisms/AgentCard/AgentCard.tsx";
import CompactAgentCard from "./CompactAgentCard.tsx";
import SectionMarker from "../SectionMarker/SectionMarker.tsx";
import styles from "./RecentAgents.module.scss";

interface RecentAgentsProps {
  /** `detailed` (advanced home) shows the team agents page card; the selection is the same. */
  variant?: "compact" | "detailed";
}

// The home never manages agents: the shared card shows no menu without that right.
const noop = () => undefined;

/** Five SQL-backed launchers: recent usable agents, then accessible suggestions. */
export default function RecentAgents({ variant = "compact" }: RecentAgentsProps) {
  const { t } = useTranslation();
  const { availableTeams } = useFrontendBootstrap();
  const { data, isLoading, isError, refetch } = useHomeAgentsQuery({}, { refetchOnMountOrArgChange: true });
  const title = t("rework.home.recentAgents.suggestedTitle");
  const teamName = (teamId: string) =>
    isPersonalTeamId(teamId)
      ? t("rework.home.topTeams.personalSpace")
      : availableTeams.find((team) => team.id === teamId)?.name;

  return (
    <section className={styles.section} data-variant={variant} aria-label={title} aria-busy={isLoading}>
      <div className={styles.head}>
        {variant === "detailed" ? <SectionMarker /> : <Icon category="outlined" type="history" />}
        <h2 className={styles.title}>{title}</h2>
      </div>
      {isLoading ? (
        <p role="status">{t("rework.home.recentAgents.loading")}</p>
      ) : isError ? (
        <div role="alert">
          <p>{t("rework.home.recentAgents.error")}</p>
          <Button color="secondary" variant="outlined" size="small" onClick={() => void refetch()}>
            {t("rework.home.recentAgents.retry")}
          </Button>
        </div>
      ) : (
        <>
          {data?.history_unavailable && <p role="status">{t("rework.home.recentAgents.historyUnavailable")}</p>}
          {data?.agents.length === 0 && <p>{t("rework.home.recentAgents.empty")}</p>}
          <div className={variant === "detailed" ? styles.grid : styles.row} data-count={data?.agents.length ?? 0}>
            {data?.agents.map((instance) =>
              variant === "detailed" ? (
                <AgentCard
                  key={instance.agent_instance_id}
                  instance={instance}
                  teamId={instance.team_id}
                  canManageAgents={false}
                  onEdit={noop}
                  onToggleEnabled={noop}
                  onDuplicate={noop}
                  onCopyTo={noop}
                  onDelete={noop}
                />
              ) : (
                <CompactAgentCard
                  key={instance.agent_instance_id}
                  instance={instance}
                  teamId={instance.team_id}
                  teamName={teamName(instance.team_id)}
                />
              ),
            )}
          </div>
        </>
      )}
    </section>
  );
}
