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

import { useContext } from "react";
import { useTranslation } from "react-i18next";
import { isPersonalTeamId } from "@shared/utils/teamId.ts";
import { ApplicationContext } from "../../../../../app/ApplicationContextProvider.tsx";
import { useFrontendBootstrap } from "../../../../../hooks/useFrontendBootstrap";
import { useFrontendProperties } from "../../../../../hooks/useFrontendProperties.ts";
import type {
  FeaturedHomeAgent,
  ManagedAgentInstanceSummary,
} from "../../../../../slices/controlPlane/controlPlaneOpenApi.ts";
import FeaturedCarousel from "../FeaturedCarousel/FeaturedCarousel.tsx";
import HomeAskBox from "../HomeAskBox/HomeAskBox.tsx";
import RecentAgents from "../RecentAgents/RecentAgents.tsx";
import styles from "./AdvancedQuickAccess.module.scss";

interface AdvancedQuickAccessProps {
  featured: FeaturedHomeAgent[];
  /** Agent chosen by the admin for the question field; none hides it. */
  askAgent?: ManagedAgentInstanceSummary | null;
  firstName?: string;
}

/** "Accès rapide" tab of the advanced home: greeting, featured banner, the user's agents. */
export default function AdvancedQuickAccess({ featured, askAgent, firstName }: AdvancedQuickAccessProps) {
  const { t } = useTranslation();
  const { darkMode } = useContext(ApplicationContext);
  const { logoName, logoNameDark, siteDisplayName } = useFrontendProperties();
  const { availableTeams } = useFrontendBootstrap();
  const baseUrl = import.meta.env.BASE_URL?.endsWith("/")
    ? import.meta.env.BASE_URL
    : `${import.meta.env.BASE_URL ?? ""}/`;
  const teamName = (teamId: string) =>
    isPersonalTeamId(teamId)
      ? t("rework.home.topTeams.personalSpace")
      : availableTeams.find((team) => team.id === teamId)?.name;

  return (
    <div className={styles.content}>
      <div className={styles.greeting}>
        <img
          className={styles.logo}
          src={`${baseUrl}images/${darkMode ? logoNameDark : logoName}.svg`}
          alt={siteDisplayName}
        />
        <div className={styles.greetingText}>
          <h1 className={styles.title}>
            {firstName ? t("rework.home.greetingNamed", { name: firstName }) : t("rework.home.greeting")}
          </h1>
          <p className={styles.subtitle}>{t("rework.home.subtitle")}</p>
        </div>
      </div>
      {featured.length > 0 && <FeaturedCarousel featured={featured} teamName={teamName} />}
      {askAgent && <HomeAskBox agent={askAgent} />}
      <RecentAgents variant="detailed" />
    </div>
  );
}
