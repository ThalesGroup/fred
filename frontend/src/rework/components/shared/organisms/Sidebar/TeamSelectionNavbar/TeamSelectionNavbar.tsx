import { useListTeamsQuery } from "../../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import TeamSelectionItem from "@shared/organisms/Sidebar/TeamSelectionNavbar/TeamSelectionItem/TeamSelectionItem.tsx";
import styles from "./TeamSelectionNavbar.module.scss";
import Separator from "@shared/atoms/Separator/Separator.tsx";
import { useTranslation } from "react-i18next";
import { useLocation } from "react-router-dom";
import { useGetUserDetailsControlPlaneV1UserGetQuery } from "../../../../../../slices/controlPlane/controlPlaneOpenApi.ts";

export default function TeamSelectionNavbar() {
  const { data: teams } = useListTeamsQuery();
  const { data: userDetails } = useGetUserDetailsControlPlaneV1UserGetQuery();
  const { pathname } = useLocation();
  const { t } = useTranslation();

  return (
    <div className={styles["team-navbar-container"]}>
      <div>
        <span className={styles.title}>{t("rework.sidebar.title")}</span>
        <TeamSelectionItem
          redirection={`/team/${userDetails?.personalTeam.id}/agents`}
          teamName={t("rework.sidebar.team.userTeam")}
          selected={pathname.startsWith(`/team/${userDetails?.personalTeam.id}`)}
          icon={{ category: "outlined", type: "Person", filled: true }}
        />
        <TeamSelectionItem
          redirection={"/marketplace/teams"}
          teamName={t("rework.sidebar.team.marketplace")}
          selected={pathname.startsWith(`/marketplace`)}
          icon={{ category: "outlined", type: "storefront", filled: false }}
        />
      </div>
      <Separator margin={"var(--spacing-xs)"} />
      <div>
        {teams?.map((team) => {
          return (
            <TeamSelectionItem
              key={team.id}
              redirection={`/team/${team.id}/agents`}
              teamName={team.name}
              selected={pathname.startsWith(`/team/${team.id}`)}
              imgUrl={"/images/default-team-banner.png"}
            />
          );
        })}
      </div>
    </div>
  );
}
