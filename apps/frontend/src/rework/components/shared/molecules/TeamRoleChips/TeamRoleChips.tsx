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
import { UserTeamRelation } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import styles from "./TeamRoleChips.module.scss";

// AUTHZ-06 (RFC Part 7 §37): one independently togglable chip per elevated
// team role — a member may hold several at once, so this is a multi-select
// toggle group, not a single-select pattern. `team_member` is deliberately
// excluded: it's the implicit baseline when none of the three apply, not a
// toggle of its own.
export const ELEVATED_TEAM_ROLES: UserTeamRelation[] = ["team_admin", "team_editor", "team_analyst"];

interface TeamRoleChipsProps {
  heldRoles: UserTeamRelation[];
  onToggle: (role: UserTeamRelation, held: boolean) => void;
  /** Per-role gate for the current actor. Omit to leave every chip enabled. */
  canAdminister?: (role: UserTeamRelation) => boolean;
}

export default function TeamRoleChips({ heldRoles, onToggle, canAdminister }: TeamRoleChipsProps) {
  const { t } = useTranslation();

  return (
    <div className={styles.roleChips} role="group">
      {ELEVATED_TEAM_ROLES.map((role) => {
        const held = heldRoles.includes(role);
        const disabled = canAdminister ? !canAdminister(role) : false;
        return (
          <button
            key={role}
            type="button"
            className={styles.roleChip}
            data-active={held}
            aria-pressed={held}
            disabled={disabled}
            onClick={() => onToggle(role, held)}
          >
            {t(`rework.teamRoles.${role}`)}
          </button>
        );
      })}
    </div>
  );
}
