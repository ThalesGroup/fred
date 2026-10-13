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
import type { Announcement, AnnouncementWriteRequest } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import ActivationHistory from "./ActivationHistory";
import AnnouncementEditorDialog from "./AnnouncementEditorDialog";
import PatchNoteAnnouncer from "./PatchNoteAnnouncer";
import PatchNoteEditorDialog from "./PatchNoteEditorDialog";
import PatchNoteList from "./PatchNoteList";
import RowControls from "./RowControls";
import styles from "./AnnouncementsPage.module.css";

type AnnouncementKind = NonNullable<Announcement["kind"]>;

const VIEWS = ["banners", "patchNotes", "history"] as const;
type View = (typeof VIEWS)[number];

/** What each list tab creates, and the words around it. */
const LISTS = {
  banners: { kind: "banner", icon: "campaign", create: "createBanner", empty: "emptyBanners" },
  patchNotes: { kind: "patch_note", icon: "new_releases", create: "createPatchNote", empty: "emptyPatchNotes" },
} as const;

/** `announcement: null` composes a new one of that kind; `undefined` means the editor is closed. */
type EditorTarget = { kind: AnnouncementKind; announcement: Announcement | null } | undefined;

/** What names an announcement in a sentence. */
function announcementName(announcement: Announcement, language: string): string {
  return resolveAnnouncementText(announcement.title, language) || announcement.id;
}

/**
 * Platform announcements, one tab per kind: banners at the top of the app, and
 * patch notes users browse in "What's new". The live banner count sits in the
 * header, the number an admin most easily loses track of; the activation
 * history is the third tab.
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

  // Not remembered: no admin page keeps its view in the URL or in storage.
  const [view, setView] = useState<View>("banners");
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

  // One read, split by kind; the server already returns patch notes in the administrator's order.
  const banners = announcements.filter((a) => a.kind !== "patch_note");
  const patchNotes = announcements.filter((a) => a.kind === "patch_note");
  const enabledCount = banners.filter((a) => a.enabled).length;
  const list = view === "history" ? undefined : LISTS[view];

  const closeEditor = () => {
    setEditing(undefined);
    setServerError(undefined);
  };

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

  const onDelete = (announcement: Announcement) => {
    const keys =
      announcement.kind === "patch_note" ? "rework.announcements.patchNote" : ("rework.announcements" as const);
    showConfirmationDialog({
      title: t(`${keys}.delete.title`),
      message: t(`${keys}.delete.message`, { title: announcementName(announcement, i18n.language) }),
      criticalAction: true,
      onConfirm: async () => {
        try {
          await deleteAnnouncement({ announcementId: announcement.id }).unwrap();
          showSuccess({ summary: t(`${keys}.deleted`) });
        } catch (error: unknown) {
          showError({
            summary: t("rework.announcements.deleteFailed"),
            detail: normalizeApiError(error).detail,
          });
        }
      },
    });
  };

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

  return (
    <div className={styles.page}>
      <PageHeader
        title={t("rework.announcements.page.title")}
        subtitle={t("rework.announcements.page.subtitle", { count: enabledCount })}
        actions={
          // Each list tab creates its own kind; the history has nothing to add.
          list && (
            <Button
              color="primary"
              variant="filled"
              size="medium"
              icon={{ category: "outlined", type: "add" }}
              onClick={() => setEditing({ kind: list.kind, announcement: null })}
            >
              {t(`rework.announcements.page.${list.create}`)}
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

      {!list ? (
        <ActivationHistory />
      ) : (
        <div className={styles.main}>
          {!isLoading && (view === "banners" ? banners : patchNotes).length === 0 ? (
            // No action of its own: the header button is always there.
            <PageEmptyState icon={list.icon} message={t(`rework.announcements.page.${list.empty}`)} />
          ) : view === "banners" ? (
            <ul className={styles.list}>
              {banners.map((announcement) => (
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
                      onToggle={(enabled) => void toggle(announcement, enabled)}
                      onEdit={() => setEditing({ kind: "banner", announcement })}
                      onDelete={() => onDelete(announcement)}
                    />
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <>
              <PatchNoteAnnouncer visibleNotes={patchNotes.filter((a) => a.enabled)} />
              <PatchNoteList
                notes={patchNotes}
                pendingIds={pendingIds}
                onPreview={setPreviewing}
                onToggle={(note, enabled) => void toggle(note, enabled)}
                onEdit={(announcement) => setEditing({ kind: "patch_note", announcement })}
                onDelete={onDelete}
              />
            </>
          )}
        </div>
      )}

      {editorProps &&
        (editing.kind === "patch_note" ? (
          <PatchNoteEditorDialog
            key={editorKey}
            {...editorProps}
            onSave={(payload, activate) => void onSave(payload, activate)}
          />
        ) : (
          <AnnouncementEditorDialog key={editorKey} {...editorProps} onSave={(payload) => void onSave(payload)} />
        ))}

      {/* The users' dialog itself, with this single note; closing a preview records nothing. */}
      <PatchNoteDialog
        open={previewing !== null}
        notes={
          previewing
            ? [
                {
                  id: previewing.id,
                  title: announcementName(previewing, i18n.language),
                  markdown: resolveAnnouncementText(previewing.description_long, i18n.language) ?? "",
                },
              ]
            : []
        }
        onClose={() => setPreviewing(null)}
      />
    </div>
  );
}
