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
import ButtonGroup from "@shared/atoms/ButtonGroup/ButtonGroup.tsx";
import { KeyCloakService } from "../../../../security/KeycloakService";
import { skipToken } from "@reduxjs/toolkit/query";
import { useWorkingOrganization } from "@core/hooks/useWorkingOrganization";
import { sessionQueryArgs } from "../../../../slices/controlPlane/controlPlaneApi";
import {
  useQueryAnalyticsQuery,
  type AnalyticsQuery,
  type QueryAnalyticsApiArg,
} from "../../../../slices/controlPlane/controlPlaneOpenApi";
import { homePeriodRange } from "./homePeriod";
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

      {tabIndex === 1 && <ActivityTab period={period} />}

      {tabIndex === 2 && <MarketplaceTopPrompts period={period} />}
    </div>
  );
}

/** One mounted activity tab shares current/previous reads and server-ranked lists. */
export function ActivityTab({ period }: { period: HomePeriod }) {
  const { t } = useTranslation();
  const context = useWorkingOrganization();
  const organizationId = context.loading || context.error ? undefined : context.organizationId;
  const identity = KeyCloakService.GetSessionIdentity();
  const memberships = context.memberships.currentData?.filter((s) => s.organization_id === organizationId) ?? [];
  // Membership changes invalidate server-ranked spaces too; no stale team list survives a withdrawal.
  const membershipKey = JSON.stringify(memberships.map((s) => [s.id, s.roles]));
  const range = useMemo(() => homePeriodRange(period), [period]);
  const args = useMemo<{
    sessions: QueryAnalyticsApiArg | typeof skipToken;
    turns: QueryAnalyticsApiArg | typeof skipToken;
  }>(() => {
    if (!organizationId) return { sessions: skipToken, turns: skipToken };
    const previous = {
      since: new Date(2 * Date.parse(range.since) - Date.parse(range.until)).toISOString(),
      until: range.since,
    };
    const scope = { kind: "self" as const, organization_id: organizationId };
    const currentTime = { ...range, timezone: "UTC" as const };
    const previousTime = { ...previous, timezone: "UTC" as const };
    const request = (queries: AnalyticsQuery[]) =>
      sessionQueryArgs<QueryAnalyticsApiArg & { membershipKey: string }>({
        analyticsRequest: { queries },
        membershipKey,
      });
    return {
      sessions: request([
        { name: "current", scope, time: currentTime, measures: ["activity.retained_conversations"] },
        { name: "previous", scope, time: previousTime, measures: ["activity.retained_conversations"] },
      ]),
      turns: request([
        { name: "current", scope, time: currentTime, measures: ["activity.completed_turns", "activity.agents_used"] },
        { name: "previous", scope, time: previousTime, measures: ["activity.completed_turns", "activity.agents_used"] },
        {
          name: "teams",
          scope,
          time: currentTime,
          measures: ["activity.completed_turns"],
          group_by: ["space"],
          limit: 5,
        },
        {
          name: "agents",
          scope,
          time: currentTime,
          measures: ["activity.completed_turns"],
          group_by: ["agent"],
          limit: 5,
        },
      ]),
    };
  }, [organizationId, identity, membershipKey, range]);
  const sessions = useQueryAnalyticsQuery(args.sessions, { refetchOnMountOrArgChange: 300 });
  const turns = useQueryAnalyticsQuery(args.turns, { refetchOnMountOrArgChange: 300 });
  const status = (query: typeof sessions) => {
    if (context.loading) return "loading";
    if (context.error) return "error";
    if (!organizationId) return "organizationRequired";
    if (query.isError)
      return query.error && "status" in query.error && query.error.status === 503 ? "unavailable" : "error";
    if (!query.currentData) return query.isFetching || query.isUninitialized ? "loading" : "unavailable";
    if (!query.currentData.results.current || !query.currentData.results.previous) return "unavailable";
    return undefined;
  };
  const sessionStatus = status(sessions);
  const turnStatus = status(turns);
  const sessionData = sessionStatus ? undefined : sessions.currentData?.results;
  const turnData = turnStatus ? undefined : turns.currentData?.results;
  return (
    <>
      <ActivityKpis
        period={period}
        sessions={sessionData}
        turns={turnData}
        sessionStatus={sessionStatus}
        turnStatus={turnStatus}
      />
      <ResponsibleAiSection period={period} />
      <div className={styles.cols}>
        <TopTeams
          result={turnData?.teams}
          memberships={memberships}
          status={turnStatus ?? (turnData?.teams ? undefined : "unavailable")}
        />
        <TopAgents
          result={turnData?.agents}
          memberships={memberships}
          status={turnStatus ?? (turnData?.agents ? undefined : "unavailable")}
        />
      </div>
      <p>{t("rework.home.activity.observed")}</p>
    </>
  );
}
