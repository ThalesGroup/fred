import { useListTeamsKnowledgeFlowV1TeamsGetQuery } from "../../../../../../slices/knowledgeFlow/knowledgeFlowApiEnhancements.ts";
import TeamSelectionItem from "@shared/organisms/Sidebar/TeamSelectionNavbar/TeamSelectionItem/TeamSelectionItem.tsx";
import styles from "./TeamSelectionNavbar.module.scss";
import Separator from "@shared/atoms/Separator/Separator.tsx";
import { useTranslation } from "react-i18next";
import { useLocation } from "react-router-dom";

export default function TeamSelectionNavbar() {
  const { data: teams } = useListTeamsKnowledgeFlowV1TeamsGetQuery();
  const { pathname } = useLocation();
  const { t } = useTranslation();

  return (
    <div className={styles["team-navbar-container"]}>
      <div>
        <span className={styles.title}>{t("rework.sidebar.title")}</span>
        <TeamSelectionItem
          redirection={"agents"}
          teamName={t("rework.sidebar.team.userTeam")}
          selected={pathname.startsWith(`/agents`) || pathname.startsWith(`/knowledge`)}
        />
        <TeamSelectionItem
          redirection={"/teams"}
          teamName={t("rework.sidebar.team.allTeams")}
          selected={pathname.startsWith(`/teams`)}
        />
      </div>
      <Separator margin={"8px"} />
      <div>
        {teams?.map((team) => {
          return (
            <TeamSelectionItem
              key={team.id}
              redirection={"/team/" + team.id}
              teamName={team.name}
              selected={pathname.startsWith(`/team/${team.id}`)}
              imgUrl={"/public/images/default-team-banner.png"}
            />
          );
        })}
      </div>
    </div>
  );
}
