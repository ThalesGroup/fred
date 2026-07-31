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

import TeamSettingsMembersTable from "./TeamSettingsMembersTable/TeamSettingsMembersTable.tsx";
import LeaveTeamButton from "./LeaveTeamButton/LeaveTeamButton.tsx";
import AddTeamMembersDialog from "./AddTeamMembersDialog/AddTeamMembersDialog.tsx";
import Button from "@shared/atoms/Button/Button.tsx";
import TextInput from "@shared/atoms/TextInput/TextInput.tsx";
import IconButton from "@shared/atoms/IconButton/IconButton.tsx";
import PageHeader from "@shared/molecules/PageHeader/PageHeader.tsx";
import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { TeamWithPermissions } from "../../../../../../slices/controlPlane/controlPlaneOpenApi";
import { useTeamCapabilities } from "@hooks/useTeamCapabilities.ts";
import styles from "./TeamSettingsMembers.module.scss";

interface TeamSettingsMembersProps {
  team: TeamWithPermissions;
}

export default function TeamSettingsMembers({ team }: TeamSettingsMembersProps) {
  const { t } = useTranslation();

  const { canAdministerMembers: can_administer_members } = useTeamCapabilities(team);

  const [isAddDialogOpen, setIsAddDialogOpen] = useState(false);
  const [search, setSearch] = useState("");
  const searchInputRef = useRef<HTMLInputElement>(null);

  return (
    <div className={styles["team-settings-members-container"]}>
      <PageHeader
        title={t("rework.teamSettings.members.title")}
        actions={
          <>
            <div className={styles["team-settings-members-search"]}>
              <TextInput
                ref={searchInputRef}
                compact
                icon={{ category: "outlined", type: "search" }}
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder={t("rework.teamSettings.members.search.placeholder")}
                aria-label={t("rework.teamSettings.members.search.ariaLabel")}
                style={search ? { paddingRight: "calc(var(--spacing-2xs) + 2rem + var(--spacing-xs))" } : undefined}
              />
              {search && (
                <span className={styles["team-settings-members-search-clear"]}>
                  <IconButton
                    type="button"
                    size="small"
                    color="on-surface-retreat"
                    variant="icon"
                    icon={{ category: "outlined", type: "close" }}
                    aria-label={t("rework.teamSettings.members.search.clearAriaLabel")}
                    onClick={() => {
                      setSearch("");
                      searchInputRef.current?.focus();
                    }}
                  />
                </span>
              )}
            </div>
            <LeaveTeamButton team={team} />
            {can_administer_members && (
              <Button color="primary" variant="filled" size="medium" onClick={() => setIsAddDialogOpen(true)}>
                {t("rework.teamSettings.members.addMembersDialog.buttonLabel")}
              </Button>
            )}
          </>
        }
      />
      <div className={styles["team-settings-members-table-wrapper"]}>
        <TeamSettingsMembersTable team={team} search={search} />
      </div>
      {can_administer_members && (
        <AddTeamMembersDialog open={isAddDialogOpen} team={team} onClose={() => setIsAddDialogOpen(false)} />
      )}
    </div>
  );
}
