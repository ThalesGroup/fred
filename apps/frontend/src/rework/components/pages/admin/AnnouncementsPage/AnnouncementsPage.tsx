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
import ButtonGroup from "@shared/atoms/ButtonGroup/ButtonGroup";
import { DeleteIconButton } from "@shared/atoms/DeleteIconButton/DeleteIconButton";
import Icon from "@shared/atoms/Icon/Icon";
import IconButton from "@shared/atoms/IconButton/IconButton";
import Switch from "@shared/atoms/Switch/Switch";
import { Tooltip } from "@shared/atoms/Tooltip/Tooltip";
import PageEmptyState from "@shared/molecules/PageEmptyState/PageEmptyState";
import PageHeader from "@shared/molecules/PageHeader/PageHeader";
import AnnouncementBanner from "@shared/molecules/AnnouncementBanner/AnnouncementBanner";
import { PatchNoteDialog } from "@shared/molecules/PatchNoteDialog/PatchNoteDialog";
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
import type {
  AdminAnnouncement,
  Announcement,
  AnnouncementWriteRequest,
} from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import ActivationHistory from "./ActivationHistory";
import AnnouncementEditorDialog from "./AnnouncementEditorDialog";
import AnnouncementKindChooser from "./AnnouncementKindChooser";
import PatchNoteEditorDialog from "./PatchNoteEditorDialog";
import styles from "./AnnouncementsPage.module.css";

type AnnouncementKind = NonNullable<Announcement["kind"]>;

const VIEWS = ["announcements", "history"] as const;
type View = (typeof VIEWS)[number];

/** `announcement: null` composes a new one of that kind; `undefined` means the editor is closed. */
type EditorTarget = { kind: AnnouncementKind; announcement: Announcement | null } | undefined;

/** What names an announcement in a sentence, and a patch note in its row. */
function announcementName(announcement: Announcement, language: string): string {
  return resolveAnnouncementText(announcement.title, language) || announcement.id;
}

interface RowControlsProps {
  announcement: Announcement;
  /** Its toggle (or save-and-activate) is in flight: a second click would race it. */
  pending: boolean;
  onToggle: (enabled: boolean) => void;
  onEdit: () => void;
  onDelete: () => void;
}

/** Switch, Edit and Delete: the controls every row carries, whatever its kind. */
function RowControls({ announcement, pending, onToggle, onEdit, onDelete }: RowControlsProps) {
  const { t } = useTranslation();
  return (
    <>
      <Tooltip
        text={
          announcement.enabled ? t("rework.announcements.row.disableHint") : t("rework.announcements.row.enableHint")
        }
      >
        <Switch
          size="small"
          checked={announcement.enabled}
          disabled={pending}
          onChange={(event) => onToggle(event.target.checked)}
          aria-label={t("rework.announcements.row.enabled")}
        />
      </Tooltip>
      <IconButton
        size="small"
        variant="icon"
        icon={{ category: "outlined", type: "edit" }}
        aria-label={t("rework.announcements.row.edit")}
        onClick={onEdit}
      />
      <DeleteIconButton size="small" aria-label={t("rework.announcements.row.delete")} onClick={onDelete} />
    </>
  );
}

interface PatchNoteRowProps extends RowControlsProps {
  announcement: AdminAnnouncement;
  onPreview: () => void;
}

/** A patch note has no banner to show, so its row is a neutral card naming it by its title. */
function PatchNoteRow({ announcement, onPreview, ...controls }: PatchNoteRowProps) {
  const { t, i18n } = useTranslation();
  return (
    <li className={styles.row} data-kind="patch_note">
      <div className={styles.patchNote}>
        <span className={styles.patchNoteIcon} aria-hidden="true">
          <Icon category="outlined" type="new_releases" />
        </span>
        <div className={styles.patchNoteText}>
          <span className={styles.patchNoteKind}>{t("rework.announcements.kind.patch_note")}</span>
          <span className={styles.patchNoteTitle}>{announcementName(announcement, i18n.language)}</span>
          <span className={styles.patchNoteDismissals}>
            {t("rework.announcements.patchNote.dismissalCount", { count: announcement.dismissal_count ?? 0 })}
          </span>
        </div>
      </div>
      <div className={styles.controls}>
        {/* Before the switch, so the three shared controls line up with the banner rows'. */}
        <IconButton
          size="small"
          variant="icon"
          icon={{ category: "outlined", type: "visibility" }}
          aria-label={t("rework.announcements.row.preview")}
          onClick={onPreview}
        />
        <RowControls announcement={announcement} {...controls} />
      </div>
    </li>
  );
}

/**
 * Platform announcements: banners at the top of the app and patch notes shown
 * once at load. The live banner count sits in the header, the number an admin
 * most easily loses track of; the activation history is a second view.
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

  const [choosingKind, setChoosingKind] = useState(false);
  // Not remembered: no admin page keeps its view in the URL or in storage.
  const [view, setView] = useState<View>("announcements");
  const [editing, setEditing] = useState<EditorTarget>(undefined);
  const [previewing, setPreviewing] = useState<Announcement | null>(null);
  const [serverError, setServerError] = useState<string | undefined>();
  const [pendingIds, setPendingIds] = useState<ReadonlySet<string>>(() => new Set());

  const setPending = (id: string, pending: boolean) =>
    setPendingIds((previous) => {
      const next = new Set(previous);
      if (pending) next.add(id);
      else next.delete(id);
      return next;
    });

  // Banners only: an active patch note is not "shown to every user" (some dismissed it).
  const enabledCount = announcements.filter((a) => a.enabled && a.kind !== "patch_note").length;
  const isEmpty = !isLoading && announcements.length === 0;

  const closeEditor = () => {
    setEditing(undefined);
    setServerError(undefined);
  };

  /** The patch note that enabling `target` would switch off, if any: only one can be active. */
  const activePatchNoteOtherThan = (target: Announcement | null) =>
    announcements.find((a) => a.kind === "patch_note" && a.enabled && a.id !== target?.id);

  const onSave = async (payload: AnnouncementWriteRequest, activate = false) => {
    const target = editing?.announcement;
    const activating = activate && target ? target.id : undefined;
    if (activating) setPending(activating, true);
    try {
      if (target) {
        await updateAnnouncement({ announcementId: target.id, announcementWriteRequest: payload }).unwrap();
        if (activate) {
          await setEnabled({ announcementId: target.id, setAnnouncementEnabledRequest: { enabled: true } }).unwrap();
        }
      } else {
        await createAnnouncement({ announcementWriteRequest: { ...payload, enabled: activate } }).unwrap();
      }
      closeEditor();
      const live = activate || (target?.enabled ?? false);
      showSuccess({
        summary:
          payload.kind !== "patch_note"
            ? t("rework.announcements.saved")
            : live
              ? t("rework.announcements.patchNote.savedActive")
              : t("rework.announcements.patchNote.savedInactive"),
      });
    } catch (error: unknown) {
      // A 422 names the field that was refused: it belongs in the form, where
      // the fix is. The toast only says the save did not happen.
      setServerError(normalizeApiError(error).detail);
      showError({ summary: t("rework.announcements.saveFailed") });
    } finally {
      if (activating) setPending(activating, false);
    }
  };

  const toggle = async (announcement: Announcement, enabled: boolean) => {
    setPending(announcement.id, true);
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
    } finally {
      setPending(announcement.id, false);
    }
  };

  // Enabling a patch note silently switches the active one off: say which, first.
  const onToggle = (announcement: Announcement, enabled: boolean) => {
    const replaced = enabled && announcement.kind === "patch_note" && activePatchNoteOtherThan(announcement);
    if (!replaced) return void toggle(announcement, enabled);
    setPending(announcement.id, true);
    showConfirmationDialog({
      title: t("rework.announcements.patchNote.activate.title"),
      message: t("rework.announcements.patchNote.activate.message", {
        title: announcementName(replaced, i18n.language),
      }),
      confirmButtonLabel: t("rework.announcements.patchNote.activate.confirm"),
      onConfirm: () => void toggle(announcement, enabled),
      onCancel: () => setPending(announcement.id, false),
    });
  };

  const onDelete = (announcement: Announcement) =>
    showConfirmationDialog({
      title: t("rework.announcements.delete.title"),
      message: t("rework.announcements.delete.message", { title: announcementName(announcement, i18n.language) }),
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

  // Remount per target so the form seeds from the announcement being edited
  // rather than keeping the previous one's state.
  const editorKey = editing && `${editing.kind}:${editing.announcement?.id ?? "new"}`;
  const editorProps = editing && {
    open: true,
    announcement: editing.announcement,
    saving: isCreating || isUpdating,
    serverError,
    onCancel: closeEditor,
  };
  const replacedByEditor = editing?.kind === "patch_note" ? activePatchNoteOtherThan(editing.announcement) : undefined;

  return (
    <div className={styles.page}>
      <PageHeader
        title={t("rework.announcements.page.title")}
        subtitle={t("rework.announcements.page.subtitle", { count: enabledCount })}
        actions={
          // Creating belongs to the list; the history view has nothing to add.
          view === "announcements" && (
            <Button
              color="primary"
              variant="filled"
              size="medium"
              icon={{ category: "outlined", type: "campaign" }}
              onClick={() => setChoosingKind(true)}
            >
              {t("rework.announcements.page.create")}
            </Button>
          )
        }
        tabs={
          <ButtonGroup
            variant="tabs"
            size="small"
            color="secondary"
            aria-label={t("rework.announcements.view.group")}
            items={VIEWS.map((value) => ({ label: t(`rework.announcements.view.${value}`) }))}
            selectedIndex={VIEWS.indexOf(view)}
            onSelectedIndexChange={(index) => setView(VIEWS[index])}
          />
        }
      />

      {view === "history" ? (
        <ActivationHistory />
      ) : (
        <div className={styles.main}>
          {isEmpty ? (
            // No action of its own: the header button is always there.
            <PageEmptyState icon="campaign" message={t("rework.announcements.page.empty")} />
          ) : (
            <ul className={styles.list}>
              {announcements.map((announcement) =>
                announcement.kind === "patch_note" ? (
                  <PatchNoteRow
                    key={announcement.id}
                    announcement={announcement}
                    pending={pendingIds.has(announcement.id)}
                    onPreview={() => setPreviewing(announcement)}
                    onToggle={(enabled) => onToggle(announcement, enabled)}
                    onEdit={() => setEditing({ kind: "patch_note", announcement })}
                    onDelete={() => onDelete(announcement)}
                  />
                ) : (
                  <li key={announcement.id} className={styles.row}>
                    {/* The real banner component, not a lookalike: an admin has to be
                        able to trust that what they see here is what users get. */}
                    <div className={styles.preview}>
                      <AnnouncementBanner announcement={announcement} preview />
                    </div>
                    <div className={styles.controls}>
                      <RowControls
                        announcement={announcement}
                        pending={pendingIds.has(announcement.id)}
                        onToggle={(enabled) => onToggle(announcement, enabled)}
                        onEdit={() => setEditing({ kind: "banner", announcement })}
                        onDelete={() => onDelete(announcement)}
                      />
                    </div>
                  </li>
                ),
              )}
            </ul>
          )}
        </div>
      )}

      <AnnouncementKindChooser
        open={choosingKind}
        onChoose={(kind) => {
          setChoosingKind(false);
          setEditing({ kind, announcement: null });
        }}
        onCancel={() => setChoosingKind(false)}
      />

      {editorProps &&
        (editing.kind === "patch_note" ? (
          <PatchNoteEditorDialog
            key={editorKey}
            {...editorProps}
            onSave={(payload, activate) => void onSave(payload, activate)}
            replacesTitle={replacedByEditor && announcementName(replacedByEditor, i18n.language)}
          />
        ) : (
          <AnnouncementEditorDialog key={editorKey} {...editorProps} onSave={(payload) => void onSave(payload)} />
        ))}

      {/* The users' dialog itself; closing a preview records nothing. */}
      <PatchNoteDialog
        open={previewing !== null}
        title={previewing ? announcementName(previewing, i18n.language) : ""}
        markdown={previewing ? (resolveAnnouncementText(previewing.description_long, i18n.language) ?? "") : ""}
        onClose={() => setPreviewing(null)}
      />
    </div>
  );
}
