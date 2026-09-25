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

import { useState } from "react";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button";
import { DeleteIconButton } from "@shared/atoms/DeleteIconButton/DeleteIconButton";
import IconButton from "@shared/atoms/IconButton/IconButton";
import Switch from "@shared/atoms/Switch/Switch";
import { Tooltip } from "@shared/atoms/Tooltip/Tooltip";
import PageEmptyState from "@shared/molecules/PageEmptyState/PageEmptyState";
import PageHeader from "@shared/molecules/PageHeader/PageHeader";
import AnnouncementBanner from "@shared/molecules/AnnouncementBanner/AnnouncementBanner";
import { useConfirmationDialog } from "@shared/molecules/ConfirmationDialog/ConfirmationDialogProvider";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import { normalizeApiError } from "@core/errors/normalizeApiError";
import { resolveAnnouncementText } from "../../../../features/announcements/announcementText";
import {
  useAnnouncementsQuery,
  useCreateAnnouncementMutation,
  useDeleteAnnouncementMutation,
  useSetAnnouncementEnabledMutation,
  useUpdateAnnouncementMutation,
} from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import type { Announcement, AnnouncementWriteRequest } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import AnnouncementEditorDialog from "./AnnouncementEditorDialog";
import styles from "./AnnouncementsPage.module.css";

/** `null` means "compose a new one"; `undefined` means the dialog is closed. */
type EditorTarget = Announcement | null | undefined;

/**
 * Platform announcements: the banners every user sees at the top of the app.
 *
 * The enabled count sits in the header rather than being left to be counted
 * from the rows: several announcements stack, and the number on screen is the
 * one thing an admin most easily loses track of.
 */
export default function AnnouncementsPage() {
  const { t, i18n } = useTranslation();
  const { showSuccess, showError } = useToast();
  const { showConfirmationDialog } = useConfirmationDialog();
  const { data: announcements = [], isLoading } = useAnnouncementsQuery();
  const [createAnnouncement, { isLoading: isCreating }] = useCreateAnnouncementMutation();
  const [updateAnnouncement, { isLoading: isUpdating }] = useUpdateAnnouncementMutation();
  const [setEnabled] = useSetAnnouncementEnabledMutation();
  const [deleteAnnouncement] = useDeleteAnnouncementMutation();

  const [editing, setEditing] = useState<EditorTarget>(undefined);
  const [serverError, setServerError] = useState<string | undefined>();

  const enabledCount = announcements.filter((announcement) => announcement.enabled).length;

  const onSave = async (payload: AnnouncementWriteRequest) => {
    try {
      if (editing) {
        await updateAnnouncement({
          announcementId: editing.id,
          announcementWriteRequest: payload,
        }).unwrap();
      } else {
        await createAnnouncement({ announcementWriteRequest: payload }).unwrap();
      }
      setEditing(undefined);
      setServerError(undefined);
      showSuccess({ summary: t("rework.announcements.saved") });
    } catch (error: unknown) {
      // A 422 names the field that was refused: it belongs in the form, where
      // the fix is. The toast only says the save did not happen.
      setServerError(normalizeApiError(error).detail);
      showError({ summary: t("rework.announcements.saveFailed") });
    }
  };

  const onToggle = async (announcement: Announcement, enabled: boolean) => {
    try {
      await setEnabled({
        announcementId: announcement.id,
        setAnnouncementEnabledRequest: { enabled },
      }).unwrap();
    } catch (error: unknown) {
      showError({
        summary: t("rework.announcements.toggleFailed"),
        detail: normalizeApiError(error).detail,
      });
    }
  };

  const onDelete = (announcement: Announcement) =>
    showConfirmationDialog({
      title: t("rework.announcements.delete.title"),
      message: t("rework.announcements.delete.message", {
        title: resolveAnnouncementText(announcement.title, i18n.language) ?? announcement.id,
      }),
      criticalAction: true,
      onConfirm: async () => {
        try {
          await deleteAnnouncement({ announcementId: announcement.id }).unwrap();
          showSuccess({ summary: t("rework.announcements.deleted") });
        } catch (error: unknown) {
          showError({
            summary: t("rework.announcements.deleteFailed"),
            detail: normalizeApiError(error).detail,
          });
        }
      },
    });

  return (
    <div className={styles.page}>
      <PageHeader
        title={t("rework.announcements.page.title")}
        subtitle={t("rework.announcements.page.subtitle", { count: enabledCount })}
        actions={
          <Button color="primary" variant="filled" size="medium" onClick={() => setEditing(null)}>
            {t("rework.announcements.page.create")}
          </Button>
        }
      />

      {!isLoading && announcements.length === 0 ? (
        <PageEmptyState
          icon="campaign"
          message={t("rework.announcements.page.empty")}
          action={{ label: t("rework.announcements.page.create"), onClick: () => setEditing(null) }}
        />
      ) : (
        <ul className={styles.list}>
          {announcements.map((announcement) => (
            <li key={announcement.id} className={styles.row}>
              {/* The real banner component, not a lookalike: an admin has to be
                  able to trust that what they see here is what users get. */}
              <div className={styles.preview}>
                <AnnouncementBanner announcement={announcement} preview />
              </div>
              <div className={styles.controls}>
                <Tooltip
                  text={
                    announcement.enabled
                      ? t("rework.announcements.row.disableHint")
                      : t("rework.announcements.row.enableHint")
                  }
                >
                  <Switch
                    size="small"
                    checked={announcement.enabled}
                    onChange={(event) => void onToggle(announcement, event.target.checked)}
                    aria-label={t("rework.announcements.row.enabled")}
                  />
                </Tooltip>
                <IconButton
                  size="small"
                  variant="icon"
                  icon={{ category: "outlined", type: "edit" }}
                  aria-label={t("rework.announcements.row.edit")}
                  onClick={() => setEditing(announcement)}
                />
                <DeleteIconButton
                  size="small"
                  aria-label={t("rework.announcements.row.delete")}
                  onClick={() => onDelete(announcement)}
                />
              </div>
            </li>
          ))}
        </ul>
      )}

      {editing !== undefined && (
        <AnnouncementEditorDialog
          // Remount per target so the form seeds from the announcement being
          // edited rather than keeping the previous one's state.
          key={editing?.id ?? "new"}
          open
          announcement={editing}
          saving={isCreating || isUpdating}
          serverError={serverError}
          onSave={onSave}
          onCancel={() => {
            setEditing(undefined);
            setServerError(undefined);
          }}
        />
      )}
    </div>
  );
}
