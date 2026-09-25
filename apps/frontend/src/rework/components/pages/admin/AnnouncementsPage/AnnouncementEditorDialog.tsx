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

import { useContext, useState } from "react";
import { useTranslation } from "react-i18next";
import { markdownShortcutPlugin, MDXEditor, toolbarPlugin } from "@mdxeditor/editor";
import "@mdxeditor/editor/style.css";
import { BoldItalicUnderlineToggles, CreateLink, Separator, UndoRedo } from "@mdxeditor/editor";
import ButtonGroup from "@shared/atoms/ButtonGroup/ButtonGroup";
import TextInput from "@shared/atoms/TextInput/TextInput";
import Switch from "@shared/atoms/Switch/Switch";
import { Dialog } from "@shared/molecules/Dialog/Dialog";
import { ProseToolbarButtons, proseMdxPlugins } from "@shared/organisms/ProseMdxEditor/ProseMdxEditor";
import { ApplicationContext } from "../../../../../app/ApplicationContextProvider";
import type { Announcement, AnnouncementWriteRequest } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import styles from "./AnnouncementEditorDialog.module.css";

const LOCALES = ["fr", "en"] as const;
type Locale = (typeof LOCALES)[number];

const SEVERITIES = ["info", "warning", "error", "success"] as const;

type LocaleMap = Record<string, string>;

interface AnnouncementEditorDialogProps {
  open: boolean;
  /** `null` composes a new announcement; otherwise the one being edited. */
  announcement: Announcement | null;
  saving: boolean;
  serverError?: string;
  onSave: (payload: AnnouncementWriteRequest) => void;
  onCancel: () => void;
}

function withLocale(map: LocaleMap, locale: Locale, value: string): LocaleMap {
  return { ...map, [locale]: value };
}

/** Blank locales never reach the server; the backend drops them anyway. */
function pruned(map: LocaleMap): LocaleMap {
  return Object.fromEntries(Object.entries(map).filter(([, text]) => text.trim()));
}

/**
 * Compose or edit one announcement.
 *
 * The three texts are per-locale, so the form carries a language switch rather
 * than six stacked fields: an admin writes one language at a time, and the
 * switch makes "I have not written the English yet" visible instead of
 * silently shipping a half-translated banner.
 */
export default function AnnouncementEditorDialog({
  open,
  announcement,
  saving,
  serverError,
  onSave,
  onCancel,
}: AnnouncementEditorDialogProps) {
  const { t } = useTranslation();
  const { darkMode } = useContext(ApplicationContext);
  const [locale, setLocale] = useState<Locale>("fr");
  const [severity, setSeverity] = useState<string>(announcement?.severity ?? "info");
  const [title, setTitle] = useState<LocaleMap>(announcement?.title ?? {});
  const [short, setShort] = useState<LocaleMap>(announcement?.description_short ?? {});
  const [long, setLong] = useState<LocaleMap>(announcement?.description_long ?? {});
  const [dismissible, setDismissible] = useState(announcement?.dismissible ?? true);

  // Mirrors the backend's own refusal so the admin sees it before submitting:
  // a banner with no title or no short text in any locale renders as an empty
  // strip.
  const missingTitle = Object.keys(pruned(title)).length === 0;
  const missingShort = Object.keys(pruned(short)).length === 0;
  const canSave = !missingTitle && !missingShort && !saving;

  return (
    <Dialog
      open={open}
      title={announcement ? t("rework.announcements.editor.editTitle") : t("rework.announcements.editor.createTitle")}
      confirmLabel={t("rework.save")}
      confirmDisabled={!canSave}
      onConfirm={() =>
        onSave({
          severity: severity as AnnouncementWriteRequest["severity"],
          title: pruned(title),
          description_short: pruned(short),
          description_long: pruned(long),
          // Composing never publishes: an admin enables from the list once the
          // wording is right.
          enabled: announcement?.enabled ?? false,
          dismissible,
        })
      }
      onCancel={onCancel}
      cancelLabel={t("rework.cancel")}
      maxWidth={880}
    >
      <div className={styles.form}>
        <div className={styles.row}>
          <ButtonGroup
            variant="radio"
            size="small"
            color="primary"
            aria-label={t("rework.announcements.editor.severityGroup")}
            items={SEVERITIES.map((value) => ({
              label: t(`rework.announcements.severity.${value}`),
            }))}
            selectedIndex={SEVERITIES.indexOf(severity as (typeof SEVERITIES)[number])}
            onSelectedIndexChange={(index) => setSeverity(SEVERITIES[index])}
          />
          <label className={styles.toggle}>
            <Switch checked={dismissible} onChange={(event) => setDismissible(event.target.checked)} />
            {t("rework.announcements.editor.dismissible")}
          </label>
        </div>

        <ButtonGroup
          variant="tabs"
          size="small"
          color="primary"
          aria-label={t("rework.announcements.editor.localeGroup")}
          items={LOCALES.map((value) => ({ label: t(`rework.announcements.locale.${value}`) }))}
          selectedIndex={LOCALES.indexOf(locale)}
          onSelectedIndexChange={(index) => setLocale(LOCALES[index])}
        />

        <TextInput
          label={t("rework.announcements.editor.title")}
          value={title[locale] ?? ""}
          onChange={(event) => setTitle(withLocale(title, locale, event.target.value))}
          error={missingTitle ? t("rework.announcements.editor.titleRequired") : undefined}
        />

        <div className={styles.field}>
          <span className={styles.label}>{t("rework.announcements.editor.descriptionShort")}</span>
          <span className={styles.explanation}>{t("rework.announcements.editor.descriptionShortHint")}</span>
          <div className={styles.editor}>
            <MDXEditor
              // Remount per locale: MDXEditor reads `markdown` only at mount,
              // so switching language on a live instance would keep showing the
              // previous language's text while edits landed on the new one.
              // Same reason for the theme key as WikiEditor.
              key={`short-${locale}-${darkMode ? "dark" : "light"}`}
              markdown={short[locale] ?? ""}
              onChange={(value) => setShort(withLocale(short, locale, value))}
              className={darkMode ? "dark-theme dark-editor" : undefined}
              plugins={[
                ...proseMdxPlugins(),
                markdownShortcutPlugin(),
                // A reduced toolbar, not ProseToolbarButtons: headings, lists
                // and tables cannot render inside a one-line banner strip.
                toolbarPlugin({
                  toolbarContents: () => (
                    <>
                      <UndoRedo />
                      <Separator />
                      <BoldItalicUnderlineToggles />
                      <Separator />
                      <CreateLink />
                    </>
                  ),
                }),
              ]}
            />
          </div>
          {missingShort && <span className={styles.error}>{t("rework.announcements.editor.shortRequired")}</span>}
        </div>

        <div className={styles.field}>
          <span className={styles.label}>{t("rework.announcements.editor.descriptionLong")}</span>
          <span className={styles.explanation}>{t("rework.announcements.editor.descriptionLongHint")}</span>
          <div className={styles.editor}>
            <MDXEditor
              key={`long-${locale}-${darkMode ? "dark" : "light"}`}
              markdown={long[locale] ?? ""}
              onChange={(value) => setLong(withLocale(long, locale, value))}
              className={darkMode ? "dark-theme dark-editor" : undefined}
              plugins={[
                ...proseMdxPlugins(),
                markdownShortcutPlugin(),
                toolbarPlugin({ toolbarContents: () => <ProseToolbarButtons /> }),
              ]}
            />
          </div>
        </div>

        {serverError && <span className={styles.error}>{serverError}</span>}
      </div>
    </Dialog>
  );
}
