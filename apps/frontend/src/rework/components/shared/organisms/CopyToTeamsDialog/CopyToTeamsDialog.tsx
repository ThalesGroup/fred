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

import { useEffect, useMemo, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import Checkbox from "@shared/atoms/Checkbox/Checkbox.tsx";
import Icon from "@shared/atoms/Icon/Icon.tsx";
import { Tooltip } from "@shared/atoms/Tooltip/Tooltip.tsx";
import SearchInput from "@shared/molecules/SearchInput/SearchInput.tsx";
import { Dialog } from "@shared/molecules/Dialog/Dialog.tsx";
import { isPersonalTeamId } from "@shared/utils/teamId.ts";
import { canEditTeamContent } from "@hooks/teamCapabilities";
import { useFrontendBootstrap } from "../../../../../hooks/useFrontendBootstrap";
import styles from "./CopyToTeamsDialog.module.scss";

/** What a destination can receive, when the caller knows it. */
export interface CopyTargetStatus {
  /** The team cannot be selected; the reason replaces the selection. */
  disabledReason?: string;
  /** The team can be selected but loses something; `detail` fills the tooltip. */
  warning?: { label: string; detail: ReactNode };
}

export interface CopyToTeamsDialogProps {
  open: boolean;
  title: string;
  /** Tooltip content of an info icon shown beside the title. */
  titleInfo?: ReactNode;
  subtitle: string;
  /** Shown above the list, e.g. what a warning means. */
  explanation?: ReactNode;
  confirmLabel: string;
  /** Shown when the caller edits no team besides the personal space. */
  noEditableTeamsLabel: string;
  /** The team that already holds the item: shown checked, never submitted. */
  originTeamId?: string | null;
  statusByTeamId?: Record<string, CopyTargetStatus>;
  isSubmitting?: boolean;
  onConfirm: (teamIds: string[]) => void;
  onClose: () => void;
}

/** Multi-select picker of the caller's own spaces: the personal space plus every
 * team the caller edits. Shared by prompt imports and agent copies. */
export default function CopyToTeamsDialog({
  open,
  title,
  titleInfo,
  subtitle,
  explanation,
  confirmLabel,
  noEditableTeamsLabel,
  originTeamId,
  statusByTeamId,
  isSubmitting = false,
  onConfirm,
  onClose,
}: CopyToTeamsDialogProps) {
  const { t } = useTranslation();
  const { activeTeam, availableTeams } = useFrontendBootstrap();
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());

  const personalId = activeTeam?.id ?? "personal";

  // Teams the caller can edit (excluding the personal space, which is always
  // offered separately at the top).
  const editableTeams = useMemo(
    () =>
      availableTeams.filter((team) => !isPersonalTeamId(team.id) && team.id !== personalId && canEditTeamContent(team)),
    [availableTeams, personalId],
  );

  const filteredTeams = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return editableTeams;
    return editableTeams.filter((team) => team.name.toLowerCase().includes(q));
  }, [editableTeams, search]);

  useEffect(() => {
    if (open) {
      setSelected(new Set());
      setSearch("");
    }
  }, [open]);

  const toggle = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const renderRow = (id: string, name: string) => {
    const isOrigin = id === originTeamId;
    const status = statusByTeamId?.[id];
    const disabled = isOrigin || !!status?.disabledReason;
    return (
      <label key={id} className={styles.row} data-disabled={disabled || undefined}>
        {/* The origin is checked because it already holds the item — an empty
            disabled box states the opposite. It is never added to `selected`. */}
        <Checkbox checked={isOrigin || selected.has(id)} disabled={disabled} onChange={() => toggle(id)} />
        <span className={styles.rowLabel}>{name}</span>
        {isOrigin ? (
          <span className={styles.originTag}>{t("rework.copyToTeams.originTeam")}</span>
        ) : status?.disabledReason ? (
          <span className={styles.disabledReason}>{status.disabledReason}</span>
        ) : (
          status?.warning && (
            <Tooltip content={status.warning.detail}>
              <span className={styles.warning}>
                <Icon category="outlined" type="warning" />
                {status.warning.label}
              </span>
            </Tooltip>
          )
        )}
      </label>
    );
  };

  return (
    <Dialog
      open={open}
      title={title}
      titleAddon={
        titleInfo && (
          <Tooltip content={titleInfo}>
            <span className={styles.titleInfo}>
              <Icon category="outlined" type="info" accessibleName={t("rework.copyToTeams.infoLabel")} />
            </span>
          </Tooltip>
        )
      }
      confirmLabel={confirmLabel}
      confirmDisabled={selected.size === 0 || isSubmitting}
      onConfirm={() => onConfirm([...selected])}
      onCancel={onClose}
    >
      <div className={styles.container}>
        <p className={styles.subtitle}>{subtitle}</p>
        {explanation && <p className={styles.explanation}>{explanation}</p>}

        {/* Personal space is always available (the caller is its editor). */}
        {renderRow(personalId, t("rework.copyToTeams.personalSpace"))}

        {editableTeams.length > 0 ? (
          <>
            <div className={styles.searchBar}>
              <SearchInput
                value={search}
                onChange={setSearch}
                placeholder={t("rework.copyToTeams.searchPlaceholder")}
                clearAriaLabel={t("rework.copyToTeams.clearSearch")}
                size="xs"
              />
            </div>
            <div className={styles.teamList}>
              {filteredTeams.map((team) => renderRow(team.id, team.name))}
              {filteredTeams.length === 0 && <p className={styles.empty}>{t("rework.copyToTeams.noTeams")}</p>}
            </div>
          </>
        ) : (
          <p className={styles.empty}>{noEditableTeamsLabel}</p>
        )}
      </div>
    </Dialog>
  );
}
