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
import { DeleteIconButton } from "@shared/atoms/DeleteIconButton/DeleteIconButton";
import IconButton from "@shared/atoms/IconButton/IconButton";
import Switch from "@shared/atoms/Switch/Switch";
import { Tooltip } from "@shared/atoms/Tooltip/Tooltip";
import type { Announcement } from "../../../../../slices/controlPlane/controlPlaneOpenApi";

export interface RowControlsProps {
  announcement: Announcement;
  /** Its toggle (or save-and-show) is in flight: a second click would race it. */
  pending: boolean;
  onToggle: (enabled: boolean) => void;
  onEdit: () => void;
  onDelete: () => void;
}

const rowKeys = (announcement: Announcement) =>
  announcement.kind === "patch_note" ? "rework.announcements.patchNote.row" : "rework.announcements.row";

/** The delivery switch, with a hint saying which way it goes. */
export function RowSwitch({
  announcement,
  pending,
  onToggle,
}: Pick<RowControlsProps, "announcement" | "pending" | "onToggle">) {
  const { t } = useTranslation();
  const keys = rowKeys(announcement);
  return (
    <Tooltip text={announcement.enabled ? t(`${keys}.disableHint`) : t(`${keys}.enableHint`)}>
      <Switch
        size="small"
        checked={announcement.enabled}
        disabled={pending}
        onChange={(event) => onToggle(event.target.checked)}
        aria-label={t(`${keys}.enabled`)}
      />
    </Tooltip>
  );
}

/** Edit and Delete, worded for the row's kind. */
export function RowActions({
  announcement,
  onEdit,
  onDelete,
}: Pick<RowControlsProps, "announcement" | "onEdit" | "onDelete">) {
  const { t } = useTranslation();
  const keys = rowKeys(announcement);
  return (
    <>
      <IconButton
        size="small"
        variant="icon"
        icon={{ category: "outlined", type: "edit" }}
        aria-label={t(`${keys}.edit`)}
        onClick={onEdit}
      />
      <DeleteIconButton size="small" aria-label={t(`${keys}.delete`)} onClick={onDelete} />
    </>
  );
}

/** Switch, Edit and Delete side by side: a banner row's controls. */
export default function RowControls(props: RowControlsProps) {
  return (
    <>
      <RowSwitch {...props} />
      <RowActions {...props} />
    </>
  );
}
