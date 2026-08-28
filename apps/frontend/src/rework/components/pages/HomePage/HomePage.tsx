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

import { useState } from "react";
import { useTranslation } from "react-i18next";
import ButtonGroup from "@shared/atoms/ButtonGroup/ButtonGroup.tsx";
import { KeyCloakService } from "../../../../security/KeycloakService";
import HomeSearch from "./HomeSearch/HomeSearch.tsx";
import ActivityKpis from "./ActivityKpis/ActivityKpis.tsx";
import RecentAgents from "./RecentAgents/RecentAgents.tsx";
import ResponsibleAiSection from "./ResponsibleAiSection/ResponsibleAiSection.tsx";
import TopAgents from "./TopAgents/TopAgents.tsx";
import TopTeams from "./TopTeams/TopTeams.tsx";
import MarketplaceTopPrompts from "./MarketplaceTopPrompts/MarketplaceTopPrompts.tsx";
import styles from "./HomePage.module.scss";

/** Days a home-page statistic is scoped to, chosen by the header selector. */
export type HomePeriod = 7 | 30 | 90;
const PERIODS: HomePeriod[] = [7, 30, 90];

/**
 * Landing page behind the mainNavBar Home entry (`/home`, #2298). First pass of
 * the user dashboard: a "responsible AI" nudge panel and the top community
 * prompts. A period selector in the header scopes every statistic on screen.
 */
export default function HomePage() {
  const { t } = useTranslation();
  // Same source as the chat welcome: the `given_name` claim. The bootstrap
  // payload has no first name and its `username` is an opaque identifier on
  // real realms, so no name here means the unnamed greeting, never an id.
  const firstName = KeyCloakService.GetUserGivenName() || undefined;

  // Default to 30 days (index 1 in PERIODS) — a fuller picture than 7 on landing.
  const [periodIndex, setPeriodIndex] = useState(1);
  const period = PERIODS[periodIndex];

  // Tabs split the dashboard so the landing view stays light (#2298). Default to
  // "Accès rapide" (search + recent agents); the period-scoped stats live under
  // the other two tabs, so the period selector is hidden on this first one.
  const [tabIndex, setTabIndex] = useState(0);
  const showPeriod = tabIndex !== 0;

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <ButtonGroup
          size="2xs"
          color="secondary"
          variant="radio"
          aria-label={t("rework.home.tabs.aria")}
          selectedIndex={tabIndex}
          onSelectedIndexChange={setTabIndex}
          items={[
            { label: t("rework.home.tabs.quickAccess") },
            { label: t("rework.home.tabs.activity") },
            { label: t("rework.home.tabs.trending") },
          ]}
        />
        {showPeriod && (
          <div className={styles.periodSlot}>
            <ButtonGroup
              size="small"
              color="secondary"
              variant="radio"
              aria-label={t("rework.home.period.label")}
              selectedIndex={periodIndex}
              onSelectedIndexChange={setPeriodIndex}
              items={PERIODS.map((days) => ({
                label: t("rework.home.period.days", { count: days }),
                title: t(`rework.home.period.d${days}`),
              }))}
            />
          </div>
        )}
      </header>

      {/* Only the active tab mounts, so a tab's queries fire when it's opened. */}
      {tabIndex === 0 && (
        <div className={styles.quickAccessTab}>
          <div className={styles.headerText}>
            <h1 className={styles.title}>
              {firstName ? t("rework.home.greetingNamed", { name: firstName }) : t("rework.home.greeting")}
            </h1>
            <p className={styles.subtitle}>{t("rework.home.subtitle")}</p>
          </div>
          <HomeSearch />
          <RecentAgents />
        </div>
      )}

      {tabIndex === 1 && (
        <>
          <ActivityKpis period={period} />
          <ResponsibleAiSection period={period} />
          <div className={styles.cols}>
            <TopTeams period={period} />
            <TopAgents period={period} />
          </div>
        </>
      )}

      {tabIndex === 2 && <MarketplaceTopPrompts period={period} />}
    </div>
  );
}
