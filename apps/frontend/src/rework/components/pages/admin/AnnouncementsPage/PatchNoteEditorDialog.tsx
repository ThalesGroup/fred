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
import { ConfirmationDialog } from "@shared/molecules/ConfirmationDialog/ConfirmationDialog";
import { Dialog } from "@shared/molecules/Dialog/Dialog";
import { PatchNoteBody } from "@shared/molecules/PatchNoteDialog/PatchNoteBody";
import { PatchNoteDialog } from "@shared/molecules/PatchNoteDialog/PatchNoteDialog";
import TextInput from "@shared/atoms/TextInput/TextInput";
import { PromptEditor } from "@shared/molecules/PromptEditor/PromptEditor";
import { resolveAnnouncementText } from "../../../../features/announcements/announcementText";
import type { Announcement, AnnouncementWriteRequest } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import styles from "./PatchNoteEditorDialog.module.css";

const LOCALES = ["fr", "en"] as const;
type Locale = (typeof LOCALES)[number];

// Mirror MAX_TITLE_CHARS / MAX_DESCRIPTION_LONG_CHARS in the backend's announcement_models.py.
const MAX_TITLE = 200;
const MAX_BODY = 20_000;
const EDITOR_ROWS = 24;

type LocaleMap = Record<string, string>;

interface PatchNoteEditorDialogProps {
  open: boolean;
  /** `null` composes a new patch note; otherwise the one being edited. */
  announcement: Announcement | null;
  saving: boolean;
  serverError?: string;
  /** `activate` asks to switch the note on right after saving it. */
  onSave: (payload: AnnouncementWriteRequest, activate: boolean) => void;
  onCancel: () => void;
  /** Title of the active patch note that activating this one would switch off. */
  replacesTitle?: string;
}

function pruned(map: LocaleMap): LocaleMap {
  return Object.fromEntries(Object.entries(map).filter(([, text]) => text.trim()));
}

const sameText = (a: LocaleMap, b: LocaleMap) => JSON.stringify(pruned(a)) === JSON.stringify(pruned(b));

/**
 * Compose or edit a patch note: one plain-text title and one markdown body per locale, a live preview
 * beside the editor, and the real user dialog one click away.
 */
export default function PatchNoteEditorDialog({
  open,
  announcement,
  saving,
  serverError,
  onSave,
  onCancel,
  replacesTitle,
}: PatchNoteEditorDialogProps) {
  const { t, i18n } = useTranslation();
  const formatNumber = (n: number) => new Intl.NumberFormat(i18n.language).format(n);
  const savedTitle = announcement?.title ?? {};
  const savedBody = announcement?.description_long ?? {};
  const [locale, setLocale] = useState<Locale>(() => LOCALES.find((l) => savedBody[l]?.trim()) ?? "fr");
  const [title, setTitle] = useState<LocaleMap>(savedTitle);
  const [body, setBody] = useState<LocaleMap>(savedBody);
  const [titleTouched, setTitleTouched] = useState(false);
  const [touched, setTouched] = useState(false);
  const [previewing, setPreviewing] = useState(false);
  const [confirming, setConfirming] = useState<"discard" | "activate" | null>(null);

  const titles = pruned(title);
  const bodies = pruned(body);
  const current = body[locale] ?? "";
  // The backend wants a title and a body in exactly the same languages.
  const incomplete = LOCALES.filter((l) => !titles[l] !== !bodies[l]);
  const missingBody = Object.keys(bodies).length === 0;
  const tooLong = Object.values(body).some((text) => text.length > MAX_BODY);
  const canSave = !missingBody && incomplete.length === 0 && !tooLong && !saving;
  const dirty = !sameText(title, savedTitle) || !sameText(body, savedBody);

  const titleError =
    titleTouched && !titles[locale] && (bodies[locale] || Object.keys(titles).length === 0)
      ? t("rework.announcements.patchNote.editor.titleRequired")
      : undefined;
  const fieldError = tooLong
    ? t("rework.announcements.patchNote.editor.tooLong", { max: formatNumber(MAX_BODY) })
    : touched && !bodies[locale] && (titles[locale] || missingBody)
      ? t("rework.announcements.patchNote.editor.bodyRequired")
      : undefined;
  const otherIncomplete = incomplete.find((l) => l !== locale);

  const payload = (): AnnouncementWriteRequest => ({
    kind: "patch_note",
    title: titles,
    description_long: bodies,
    // Placeholders the backend normalizes for a patch note.
    severity: "info",
    description_short: {},
    dismissible: true,
    enabled: announcement?.enabled ?? false,
  });
  const requestClose = () => (dirty ? setConfirming("discard") : onCancel());
  const saveAndActivate = () => (replacesTitle ? setConfirming("activate") : onSave(payload(), true));

  return (
    <>
      {/* Hidden, not stacked, while another dialog is shown: two open dialogs
          would both answer Escape and fight over the focus trap. */}
      <Dialog
        open={open && !previewing && !confirming}
        title={
          announcement
            ? t("rework.announcements.patchNote.editor.editTitle")
            : t("rework.announcements.patchNote.editor.createTitle")
        }
        confirmLabel={t("rework.save")}
        confirmDisabled={!canSave}
        onConfirm={() => onSave(payload(), false)}
        // Escape, the scrim and Cancel all land here.
        onCancel={requestClose}
        cancelLabel={t("rework.cancel")}
        maxWidth={1200}
        actionsAddon={
          !announcement?.enabled && (
            <Button
              type="button"
              color="primary"
              variant="outlined"
              size="medium"
              disabled={!canSave}
              onClick={saveAndActivate}
            >
              {t("rework.announcements.patchNote.editor.saveAndActivate")}
            </Button>
          )
        }
      >
        <div className={styles.form}>
          <div className={styles.toolbar}>
            <ButtonGroup
              variant="tabs"
              size="small"
              color="primary"
              aria-label={t("rework.announcements.editor.localeGroup")}
              items={LOCALES.map((value) => ({ label: t(`rework.announcements.locale.${value}`) }))}
              selectedIndex={LOCALES.indexOf(locale)}
              onSelectedIndexChange={(index) => setLocale(LOCALES[index])}
            />
            <span className={styles.spacer} />
            <Button
              type="button"
              color="primary"
              variant="outlined"
              size="small"
              icon={{ category: "outlined", type: "visibility" }}
              disabled={!titles[locale] || !bodies[locale]}
              onClick={() => setPreviewing(true)}
            >
              {t("rework.announcements.patchNote.editor.previewAsUsers")}
            </Button>
          </div>

          <TextInput
            label={t("rework.announcements.patchNote.editor.title")}
            maxLength={MAX_TITLE}
            value={title[locale] ?? ""}
            onChange={(event) => setTitle((map) => ({ ...map, [locale]: event.target.value }))}
            onBlur={() => setTitleTouched(true)}
            error={titleError}
          />

          <div className={styles.split}>
            {/* React's onBlur bubbles (focusout), which PromptEditor does not expose itself. */}
            <div className={styles.editorColumn} onBlur={() => setTouched(true)}>
              <PromptEditor
                label={t("rework.announcements.patchNote.editor.body")}
                value={current}
                onChange={(value) => setBody((map) => ({ ...map, [locale]: value }))}
                placeholder={t("rework.announcements.patchNote.editor.placeholder")}
                rows={EDITOR_ROWS}
                error={fieldError}
              />
              <div className={styles.editorFooter}>
                <p className={styles.hint}>{t("rework.announcements.patchNote.editor.hint")}</p>
                <p className={`${styles.counter} ${current.length > MAX_BODY ? styles.counterOver : ""}`}>
                  {formatNumber(current.length)} / {formatNumber(MAX_BODY)}
                </p>
              </div>
            </div>

            <section className={styles.previewColumn} aria-label={t("rework.announcements.patchNote.editor.preview")}>
              <p className={styles.previewLabel}>{t("rework.announcements.patchNote.editor.preview")}</p>
              <div className={styles.previewBody} data-testid="patch-note-inline-preview">
                {current.trim() ? (
                  <PatchNoteBody markdown={current} />
                ) : (
                  <p className={styles.previewEmpty}>{t("rework.announcements.patchNote.editor.previewEmpty")}</p>
                )}
              </div>
            </section>
          </div>

          {otherIncomplete && (
            <span className={styles.error}>
              {t("rework.announcements.patchNote.editor.incomplete", {
                language: t(`rework.announcements.locale.${otherIncomplete}`),
              })}
            </span>
          )}
          {serverError && <span className={styles.error}>{serverError}</span>}
        </div>
      </Dialog>

      <PatchNoteDialog
        open={open && previewing}
        title={resolveAnnouncementText(titles, locale) ?? ""}
        markdown={current}
        onClose={() => setPreviewing(false)}
      />

      <ConfirmationDialog
        open={open && confirming === "discard"}
        title={t("rework.announcements.patchNote.discard.title")}
        message={t("rework.announcements.patchNote.discard.message")}
        confirmLabel={t("rework.announcements.patchNote.discard.confirm")}
        cancelLabel={t("rework.announcements.patchNote.discard.cancel")}
        criticalAction
        onConfirm={onCancel}
        onCancel={() => setConfirming(null)}
      />
      <ConfirmationDialog
        open={open && confirming === "activate"}
        title={t("rework.announcements.patchNote.activate.title")}
        message={t("rework.announcements.patchNote.activate.message", { title: replacesTitle })}
        confirmLabel={t("rework.announcements.patchNote.activate.confirm")}
        cancelLabel={t("rework.cancel")}
        onConfirm={() => {
          setConfirming(null);
          onSave(payload(), true);
        }}
        onCancel={() => setConfirming(null)}
      />
    </>
  );
}
