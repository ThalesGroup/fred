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
import type { HomePeriod } from "../HomePage.tsx";
import LeaderboardSection from "../LeaderboardSection/LeaderboardSection.tsx";
import RankedList, { type RankedItem } from "../RankedList/RankedList.tsx";

// PLACEHOLDER DATA — "conversations per agent for this user" has no dedicated
// endpoint yet (`top_agents_by_conversations` is platform-scoped). Base counts
// are the 7-day figures; the period scales them up (more days → more usage), so
// the ranking is period-scoped. Swap for a real user-scoped KPI before shipping.
const AGENTS: { name: string; team: string; base: number }[] = [
  { name: "Rédacteur d'appel d'offres", team: "Bid & Capture", base: 20 },
  { name: "Analyste documentaire", team: "Conformité & RH", base: 14 },
  { name: "Créatif — nommage & slogans", team: "Marketing", base: 10 },
  { name: "Traducteur juridique", team: "Legal", base: 8 },
  { name: "Assistant réunion", team: "Communication", base: 6 },
];

interface TopAgentsProps {
  period: HomePeriod;
}

/** Home page — the 5 agents the current user has used most over the period. */
export default function TopAgents({ period }: TopAgentsProps) {
  const { t } = useTranslation();
  const items: RankedItem[] = AGENTS.map((a) => ({
    key: a.name,
    label: a.name,
    sublabel: a.team,
    value: Math.round((a.base * period) / 7),
    unit: t("rework.home.topAgents.unit"),
  }));

  return (
    <LeaderboardSection icon="auto_awesome" title={t("rework.home.topAgents.title")}>
      <RankedList items={items} emptyLabel={t("rework.home.topAgents.empty")} />
    </LeaderboardSection>
  );
}
