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
import CompactAgentCard from "./CompactAgentCard.tsx";
import styles from "./RecentAgents.module.scss";

/** Five SQL-backed launchers: recent usable agents, then accessible suggestions. */
export default function RecentAgents() {
  const { t } = useTranslation();
  const { availableTeams } = useFrontendBootstrap();
  const { data, isLoading, isError, refetch } = useHomeAgentsQuery(undefined, { refetchOnMountOrArgChange: true });
  const title = t("rework.home.recentAgents.suggestedTitle");

  return (
    <section className={styles.section} aria-label={title} aria-busy={isLoading}>
      <div className={styles.head}>
        <Icon category="outlined" type="history" />
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
          <div className={styles.row} data-count={data?.agents.length ?? 0}>
            {data?.agents.map((instance) => (
              <CompactAgentCard
                key={instance.agent_instance_id}
                instance={instance}
                teamId={instance.team_id}
                teamName={
                  isPersonalTeamId(instance.team_id)
                    ? t("rework.home.topTeams.personalSpace")
                    : availableTeams.find((team) => team.id === instance.team_id)?.name
                }
              />
            ))}
          </div>
        </>
      )}
    </section>
  );
}
