import TeamSelectionItem from "@shared/organisms/Sidebar/TeamSelectionNavbar/TeamSelectionItem/TeamSelectionItem.tsx";
import styles from "./TeamSelectionNavbar.module.scss";
import Separator from "@shared/atoms/Separator/Separator.tsx";
import { useTranslation } from "react-i18next";
import { useLocation } from "react-router-dom";
import { useFrontendProperties } from "../../../../../../hooks/useFrontendProperties.ts";
import { useFrontendBootstrap } from "../../../../../../hooks/useFrontendBootstrap.ts";

/**
 * Render the left-side team selector from the bootstrap-owned team list.
 *
 * Why this component exists:
 * - the shell needs one navigation surface that works in the personal-team-only
 *   baseline without relying on the temporary user-details endpoint
 *
 * How to use it:
 * - mount it inside the main sidebar layout
 *
 * Example:
 * - `<TeamSelectionNavbar />`
 */
export default function TeamSelectionNavbar() {
  const { defaultTeamAvatarFile, defaultPersonalAvatarFile } = useFrontendProperties();
  const { siteTitle, siteSubtitle } = useFrontendProperties();
  const { activeTeam, availableTeams } = useFrontendBootstrap();
  const { pathname } = useLocation();
  const { t } = useTranslation();

  const personalTeamId = activeTeam?.id ?? "personal";
  const collaborativeTeams = availableTeams.filter((team) => team.id !== personalTeamId);

  return (
    <div className={styles.teamNavbarContainer}>
      <div>
        <div className={styles.titleContainer}>
          <span className={styles.title}>{siteTitle}</span>
          <span className={styles.subTitle}>{siteSubtitle}</span>
        </div>
        <TeamSelectionItem
          redirection={`/team/${personalTeamId}/agents`}
          teamName={t("rework.sidebar.team.userTeam")}
          selected={pathname.startsWith(`/team/${personalTeamId}`)}
          icon={{ category: "outlined", type: "person", filled: true }}
          imgUrl={`/images/${defaultPersonalAvatarFile}`}
        />
        {collaborativeTeams.length > 0 && (
          <TeamSelectionItem
            redirection={"/marketplace/teams"}
            teamName={t("rework.sidebar.team.marketplace")}
            selected={pathname.startsWith(`/marketplace`)}
            icon={{ category: "outlined", type: "storefront", filled: false }}
          />
        )}
      </div>
      <Separator margin={"var(--spacing-xs)"} />
      <div className={styles.teamContainer}>
        {collaborativeTeams.map((team) => {
          return (
            <TeamSelectionItem
              key={team.id}
              redirection={`/team/${team.id}/agents`}
              teamName={team.name}
              selected={pathname.startsWith(`/team/${team.id}`)}
              imgUrl={team.banner_image_url ?? `/images/${defaultTeamAvatarFile}`}
            />
          );
        })}
      </div>
    </div>
  );
}
