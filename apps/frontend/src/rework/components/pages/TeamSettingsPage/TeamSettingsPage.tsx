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

import { Navigate, useParams } from "react-router-dom";
import { useSelectedTeam } from "../../../../hooks/useSelectedTeam.ts";
import TeamSettingsMembers from "@shared/organisms/TeamSettingsPanel/TeamSettingsMembers/TeamSettingsMembers.tsx";
import TeamSettingsParameters from "@shared/organisms/TeamSettingsPanel/TeamSettingsParameters/TeamSettingsParameters.tsx";
import TeamSettingsRetention from "@shared/organisms/TeamSettingsPanel/TeamSettingsRetention/TeamSettingsRetention.tsx";
import TeamSettingsEvaluations from "@shared/organisms/TeamSettingsPanel/TeamSettingsEvaluations/TeamSettingsEvaluations.tsx";
import styles from "./TeamSettingsPage.module.scss";

/**
 * Team settings, rendered in the main content area instead of a full-page
 * modal. The two-sidebar shell stays mounted: `TeamContentNavbar` keeps the
 * coloured team banner and swaps its menu to the settings sections, and the
 * left team rail is dimmed by `Sidebar`. This page only renders the section
 * body for the `:section` route param.
 */
export default function TeamSettingsPage() {
  const { section } = useParams<{ section: string }>();
  const { teamId, selectedTeam, canOpenTeamSettings } = useSelectedTeam();

  // Permissions arrive with the per-team fetch. While they are still loading
  // `selectedTeam` is either undefined or a permission-less bootstrap summary —
  // render nothing (the banner/chrome are already visible) rather than bounce
  // the user out before we actually know they lack access.
  const permissionsLoaded = !!selectedTeam && "permissions" in selectedTeam && Array.isArray(selectedTeam.permissions);
  if (!selectedTeam || !permissionsLoaded) return null;

  // Permissions are loaded and the user cannot administer this team: settings is
  // not for them. Guards direct navigation / refresh on a settings URL.
  if (!canOpenTeamSettings) return <Navigate to={`/team/${teamId}/agents`} replace />;

  const renderSection = () => {
    switch (section) {
      case "members":
        return <TeamSettingsMembers team={selectedTeam} />;
      case "parameters":
        return <TeamSettingsParameters team={selectedTeam} />;
      case "retention":
        return <TeamSettingsRetention team={selectedTeam} />;
      case "evaluations":
        return <TeamSettingsEvaluations team={selectedTeam} />;
      default:
        return <Navigate to={`/team/${teamId}/settings/members`} replace />;
    }
  };

  return <div className={styles.teamSettingsPage}>{renderSection()}</div>;
}
