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
import Icon from "@shared/atoms/Icon/Icon.tsx";
import { Tooltip } from "@shared/atoms/Tooltip/Tooltip.tsx";
import { UserTeamRelation } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import styles from "./TeamRoleChips.module.scss";

// AUTHZ-06 (RFC Part 7 §37): one independently togglable chip per elevated
// team role — a member may hold several at once, so this is a multi-select
// toggle group, not a single-select pattern. `team_member` is deliberately
// excluded: it's the implicit baseline when none of the three apply, not a
// toggle of its own.
export const ELEVATED_TEAM_ROLES: UserTeamRelation[] = ["team_admin", "team_editor", "team_analyst"];

// `team_analyst` grants evaluation-campaign execution plus access to the
// conversation slices those datasets are built from (REBAC.md §Team analyst).
// That is a materially different kind of access from "edit team content", and
// the flat pill row gives no hint of it — hence the extra warning row.
const ROLES_WITH_WARNING: readonly UserTeamRelation[] = ["team_analyst"];

interface TeamRoleChipsProps {
  heldRoles: UserTeamRelation[];
  onToggle: (role: UserTeamRelation, held: boolean) => void;
  /** Per-role gate for the current actor. Omit to leave every chip enabled. */
  canAdminister?: (role: UserTeamRelation) => boolean;
}

export default function TeamRoleChips({ heldRoles, onToggle, canAdminister }: TeamRoleChipsProps) {
  const { t } = useTranslation();

  const describe = (role: UserTeamRelation) => (
    <span className={styles.roleTooltip}>
      <span className={styles.roleTooltipTitle}>{t(`rework.teamRoles.${role}`)}</span>
      <span className={styles.roleTooltipText}>{t(`rework.teamRoles.descriptions.${role}`)}</span>
      {ROLES_WITH_WARNING.includes(role) && (
        <span className={styles.roleTooltipWarning}>
          <Icon category="outlined" type="warning" />
          <span>{t(`rework.teamRoles.warnings.${role}`)}</span>
        </span>
      )}
    </span>
  );

  return (
    <div className={styles.roleChips} role="group">
      {/* Informational, never a fourth toggle: `team_member` is the implicit
          baseline — automatic for anyone holding an elevated role, granted
          directly to anyone holding none (REBAC.md §Team member) — and the API
          refuses to revoke a member's last remaining relation. Rendering it as
          a static badge keeps a plain member from reading as role-less, which
          three inactive pills otherwise look exactly like. */}
      <Tooltip content={describe("team_member")}>
        <span className={styles.baselineChip} tabIndex={0}>
          {t("rework.teamRoles.team_member")}
        </span>
      </Tooltip>
      {ELEVATED_TEAM_ROLES.map((role) => {
        const held = heldRoles.includes(role);
        const disabled = canAdminister ? !canAdminister(role) : false;
        return (
          <Tooltip key={role} content={describe(role)}>
            <button
              type="button"
              className={styles.roleChip}
              data-active={held}
              aria-pressed={held}
              disabled={disabled}
              onClick={() => onToggle(role, held)}
            >
              {t(`rework.teamRoles.${role}`)}
            </button>
          </Tooltip>
        );
      })}
    </div>
  );
}
