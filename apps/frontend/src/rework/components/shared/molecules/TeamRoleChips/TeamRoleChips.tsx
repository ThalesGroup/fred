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

import { useMemo, type ReactNode } from "react";
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
// limited conversation slices those datasets are built from (REBAC.md §Team
// analyst — keep the "limited" scoping, the role does not confer general
// access to the team's conversations).
// That is a materially different kind of access from "edit team content", and
// the flat pill row gives no hint of it — hence the extra warning row.
const ROLES_WITH_WARNING: readonly UserTeamRelation[] = ["team_analyst"];

// The implicit baseline, rendered as a static badge rather than a toggle.
const BASELINE_TEAM_ROLE: UserTeamRelation = "team_member";

interface TeamRoleChipsProps {
  heldRoles: UserTeamRelation[];
  onToggle: (role: UserTeamRelation, held: boolean) => void;
  /** Per-role gate for the current actor. Omit to leave every chip enabled. */
  canAdminister?: (role: UserTeamRelation) => boolean;
}

export default function TeamRoleChips({ heldRoles, onToggle, canAdminister }: TeamRoleChipsProps) {
  const { t } = useTranslation();

  // Built once per instance instead of once per render: the members table
  // mounts one of these per member row and re-renders every row on each search
  // keystroke, yet these panels are identical every time and are discarded
  // unrendered unless the badge is actually hovered.
  const panels = useMemo(() => {
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
    return Object.fromEntries(
      [BASELINE_TEAM_ROLE, ...ELEVATED_TEAM_ROLES].map((role) => [role, describe(role)]),
    ) as Record<UserTeamRelation, ReactNode>;
  }, [t]);

  return (
    <div className={styles.roleChips} role="group">
      {/* Informational, never a fourth toggle: `team_member` is the implicit
          baseline — automatic for anyone holding an elevated role, granted
          directly to anyone holding none (REBAC.md §Team member) — and the API
          refuses to revoke a member's last remaining relation. Rendering it as
          a static badge keeps a plain member from reading as role-less, which
          three inactive pills otherwise look exactly like. `role="note"` plus
          the tab stop is what makes its description reachable without a mouse;
          without them the badge is bare text inside a group of controls. */}
      <Tooltip content={panels[BASELINE_TEAM_ROLE]}>
        <span className={styles.baselineChip} role="note" tabIndex={0}>
          {t(`rework.teamRoles.${BASELINE_TEAM_ROLE}`)}
        </span>
      </Tooltip>
      {ELEVATED_TEAM_ROLES.map((role) => {
        const held = heldRoles.includes(role);
        // `aria-disabled` rather than `disabled`: a disabled button leaves the
        // tab order and stops firing pointer events, so it would silently lose
        // the very description that tells the reader what the role they cannot
        // grant actually is. The click guard below is what makes it inert.
        const readOnly = canAdminister ? !canAdminister(role) : false;
        return (
          <Tooltip key={role} content={panels[role]}>
            <button
              type="button"
              className={styles.roleChip}
              data-active={held}
              aria-pressed={held}
              aria-disabled={readOnly}
              onClick={() => {
                if (!readOnly) onToggle(role, held);
              }}
            >
              {t(`rework.teamRoles.${role}`)}
            </button>
          </Tooltip>
        );
      })}
    </div>
  );
}
