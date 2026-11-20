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
import AdvancedQuickAccess from "./AdvancedQuickAccess/AdvancedQuickAccess.tsx";
import { useMyHomeQuery } from "../../../../slices/controlPlane/controlPlaneApiEnhancements";
import { useFrontendBootstrap } from "../../../../hooks/useFrontendBootstrap";
import styles from "./HomePage.module.scss";

/** Days a home-page statistic is scoped to, chosen by the header selector. */
export type HomePeriod = 7 | 30 | 90;
const PERIODS: HomePeriod[] = [7, 30, 90];
type HomeTab = "quickAccess" | "activity" | "trending";

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

  // Tabs keep the landing view light. Quick access contains search and recent
  // agents; period-scoped stats use the remaining tabs.
  const [selectedTab, setSelectedTab] = useState<HomeTab>("quickAccess");
  // Activity metrics need KPI presets; cleanup stays available in Quick access.
  const { bootstrap, isLoading: bootstrapLoading } = useFrontendBootstrap();
  const kpiAvailable = bootstrap?.kpi_analytics_available === true;
  const tabs: HomeTab[] = kpiAvailable ? ["quickAccess", "activity", "trending"] : ["quickAccess", "trending"];
  const tab = tabs.includes(selectedTab) ? selectedTab : "quickAccess";
  const showPeriod = tab !== "quickAccess";

  // Platform-wide mode set on the admin "Interface" page; any failure keeps the classic home.
  // Refetched on each visit: agents may have changed since (no reload in a single-page app).
  const { data: home, isLoading: homeLoading } = useMyHomeQuery(undefined, { refetchOnMountOrArgChange: true });
  const advanced = home?.layout === "advanced";

  return (
    // Fills the shell card (no shell inset), so the scrollbar sits at the card's right edge.
    <div className={styles.scroller} data-shell-inset="none">
      <div className={styles.page} data-layout={advanced ? "advanced" : "classic"}>
        <header className={styles.header}>
          <ButtonGroup
            size={advanced ? "medium" : "2xs"}
            color="secondary"
            variant="radio"
            aria-label={t("rework.home.tabs.aria")}
            selectedIndex={tabs.indexOf(tab)}
            onSelectedIndexChange={(index) => setSelectedTab(tabs[index] ?? "quickAccess")}
            items={tabs.map((key) => ({ label: t(`rework.home.tabs.${key}`) }))}
          />
          {!showPeriod && advanced && (
            <div className={styles.periodSlot}>
              <HomeSearch compact />
            </div>
          )}
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
        {/* Empty while the mode loads, so the classic home never flashes before the advanced one. */}
        {tab === "quickAccess" && homeLoading && <div className={styles.quickAccessTab} aria-busy="true" />}

        {tab === "quickAccess" && advanced && (
          <AdvancedQuickAccess
            featured={home?.featured ?? []}
            askAgent={home?.ask_agent}
            askMaxChars={home?.ask_max_chat_input_chars}
            firstName={firstName}
          />
        )}

        {tab === "quickAccess" && !homeLoading && !advanced && (
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

        {tab === "quickAccess" && !bootstrapLoading && !kpiAvailable && !homeLoading && (
          <ResponsibleAiSection period={period} kpiAvailable={false} />
        )}

        {tab === "activity" && (
          <>
            <ActivityKpis period={period} />
            <ResponsibleAiSection period={period} />
            <div className={styles.cols}>
              <TopTeams period={period} />
              <TopAgents period={period} />
            </div>
          </>
        )}

        {tab === "trending" && <MarketplaceTopPrompts period={period} />}
      </div>
    </div>
  );
}
