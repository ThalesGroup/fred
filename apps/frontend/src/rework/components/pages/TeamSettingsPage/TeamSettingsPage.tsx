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

import { Link, Navigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useSelectedTeam } from "../../../../hooks/useSelectedTeam.ts";
import TeamSettingsMembers from "@shared/organisms/TeamSettingsPanel/TeamSettingsMembers/TeamSettingsMembers.tsx";
import TeamSettingsParameters from "@shared/organisms/TeamSettingsPanel/TeamSettingsParameters/TeamSettingsParameters.tsx";
import TeamSettingsEvaluations from "@shared/organisms/TeamSettingsPanel/TeamSettingsEvaluations/TeamSettingsEvaluations.tsx";
import TeamSettingsRouting from "@shared/organisms/TeamSettingsPanel/TeamSettingsRouting/TeamSettingsRouting.tsx";
import TaskActivity from "@shared/organisms/TaskActivity/TaskActivity.tsx";
import TeamSettingsResponsibilities from "@shared/organisms/TeamSettingsPanel/TeamSettingsResponsibilities/TeamSettingsResponsibilities.tsx";
import ServiceNotice from "@shared/molecules/ServiceNotice/ServiceNotice.tsx";
import Button from "@shared/atoms/Button/Button.tsx";
import { useTeamAdminCharterStatusQuery } from "../../../../slices/controlPlane/controlPlaneApiEnhancements.ts";
import { useTeamCapabilities } from "@hooks/useTeamCapabilities.ts";
import { hasElevatedTeamRole } from "@hooks/teamCapabilities.ts";
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
  const capabilities = useTeamCapabilities(selectedTeam);
  const { canUpdateInfo, canUpdateAgents, canUpdateResources } = capabilities;
  const { t } = useTranslation();
  // From the relations, not the permissions: an admin who has not accepted the
  // charter holds no admin-only permission but must still reach it.
  const isTeamAdmin =
    !!selectedTeam && "my_relations" in selectedTeam && (selectedTeam.my_relations ?? []).includes("team_admin");
  // Refetched on every visit: a promotion made by another admin never reaches this session's cache.
  const { data: charterStatus } = useTeamAdminCharterStatusQuery(undefined, {
    skip: !isTeamAdmin,
    refetchOnMountOrArgChange: true,
  });

  // Permissions arrive with the per-team fetch. While they are still loading
  // `selectedTeam` is either undefined or a permission-less bootstrap summary —
  // render nothing (the banner/chrome are already visible) rather than bounce
  // the user out before we actually know they lack access.
  const permissionsLoaded = !!selectedTeam && "permissions" in selectedTeam && Array.isArray(selectedTeam.permissions);
  if (!selectedTeam || !permissionsLoaded) return null;

  // Permissions are loaded and the user isn't even a team member: settings is
  // not for them. Guards direct navigation / refresh on a settings URL.
  if (!canOpenTeamSettings) return <Navigate to={`/team/${teamId}/agents`} replace />;

  // AUTHZ-09: the outer gate above only proves membership — every non-"members"
  // section still needs its own capability check, since a plain member reaching
  // this page (by design, for "Members" + "Leave team") must not also reach
  // sections the sidebar hides for them via a direct/refreshed URL.
  const sectionAllowed =
    section === "members" ||
    (section === "responsibilities" && isTeamAdmin) ||
    ((section === "parameters" || section === "retention") && canUpdateInfo) ||
    (section === "evaluations" && canUpdateAgents) ||
    ((section === "activity" || section === "routing") && hasElevatedTeamRole(capabilities));
  if (section && !sectionAllowed) return <Navigate to={`/team/${teamId}/settings/members`} replace />;

  const renderSection = () => {
    switch (section) {
      case "members":
        return <TeamSettingsMembers team={selectedTeam} />;
      case "parameters":
        return <TeamSettingsParameters team={selectedTeam} />;
      case "retention":
        // Retention now lives inside the Parameters section (no dedicated tab).
        // Redirect any old /settings/retention link there.
        return <Navigate to={`/team/${teamId}/settings/parameters`} replace />;
      case "evaluations":
        return <TeamSettingsEvaluations team={selectedTeam} />;
      case "activity":
        // The exact same shared surface the platform admin sees (OPS-04 §3.4),
        // scoped to this team. Server enforces CAN_READ_MEMBERS.
        return <TaskActivity scope="team" teamId={teamId} />;
      case "routing":
        // TEAM-05, #2118: team_editor writes, team_admin reads (hard
        // cross-write rule) — canUpdateResources is team_editor-only.
        return <TeamSettingsRouting team={selectedTeam} canWrite={canUpdateResources} />;
      case "responsibilities":
        return <TeamSettingsResponsibilities />;
      default:
        return <Navigate to={`/team/${teamId}/settings/members`} replace />;
    }
  };

  return (
    <div className={styles.teamSettingsPage}>
      {charterStatus?.required && section !== "responsibilities" && (
        <div className={styles.charterNotice}>
          <ServiceNotice title={t("rework.teamAdminCharter.pendingNotice")} />
          <Link to={`/team/${teamId}/settings/responsibilities`}>
            <Button color="primary" variant="text" size="medium">
              {t("rework.teamAdminCharter.reviewCharter")}
            </Button>
          </Link>
        </div>
      )}
      {renderSection()}
    </div>
  );
}
