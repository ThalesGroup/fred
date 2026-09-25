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
import ButtonGroup from "@shared/atoms/ButtonGroup/ButtonGroup";
import TextArea from "@shared/atoms/TextArea/TextArea";
import TextInput from "@shared/atoms/TextInput/TextInput";
import Switch from "@shared/atoms/Switch/Switch";
import { Dialog } from "@shared/molecules/Dialog/Dialog";
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
 *
 * The descriptions are plain textareas. The banner still renders them through
 * MarkdownRenderer, so emphasis and links typed by hand keep working — what
 * went is the WYSIWYG toolbar, not the markdown.
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
          {/* Redefining the pair the atom reads for its selected item, rather
              than out-specifying it: this group IS the colour picker, so the
              active segment has to show the banner's own colours. */}
          <div className={styles.severityGroup} data-severity={severity}>
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
          </div>
          <label className={styles.toggle}>
            <Switch size="small" checked={dismissible} onChange={(event) => setDismissible(event.target.checked)} />
            {t("rework.announcements.editor.dismissible")}
          </label>
          <span className={styles.rowSpacer} />
          <ButtonGroup
            variant="tabs"
            size="small"
            color="primary"
            aria-label={t("rework.announcements.editor.localeGroup")}
            items={LOCALES.map((value) => ({ label: t(`rework.announcements.locale.${value}`) }))}
            selectedIndex={LOCALES.indexOf(locale)}
            onSelectedIndexChange={(index) => setLocale(LOCALES[index])}
          />
        </div>

        <TextInput
          label={t("rework.announcements.editor.title")}
          value={title[locale] ?? ""}
          onChange={(event) => setTitle(withLocale(title, locale, event.target.value))}
          error={missingTitle ? t("rework.announcements.editor.titleRequired") : undefined}
        />

        <TextArea
          label={t("rework.announcements.editor.descriptionShort")}
          explanation={t("rework.announcements.editor.descriptionShortHint")}
          error={missingShort ? t("rework.announcements.editor.shortRequired") : undefined}
          rows={2}
          value={short[locale] ?? ""}
          onChange={(event) => setShort(withLocale(short, locale, event.target.value))}
        />

        <TextArea
          label={t("rework.announcements.editor.descriptionLong")}
          explanation={t("rework.announcements.editor.descriptionLongHint")}
          rows={4}
          value={long[locale] ?? ""}
          onChange={(event) => setLong(withLocale(long, locale, event.target.value))}
        />

        {serverError && <span className={styles.error}>{serverError}</span>}
      </div>
    </Dialog>
  );
}
