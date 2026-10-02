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

import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button.tsx";
import Checkbox from "@shared/atoms/Checkbox/Checkbox.tsx";
import PageHeader from "@shared/molecules/PageHeader/PageHeader.tsx";
import Select from "@shared/molecules/Select/Select.tsx";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import { userDisplayName } from "@core/utils/userDisplayName.ts";
import { normalizeApiError } from "@core/errors/normalizeApiError.ts";
import { UI_THEME_LABEL_KEYS, UI_THEMES, type UiTheme } from "../../../../../app/uiThemes.ts";
import {
  usePlatformUiSettingsQuery,
  useSetPlatformUiSettingsMutation,
  useUsersByIdsQuery,
} from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import styles from "./UiSettingsPage.module.css";

// Select value for "no platform default": the first offered theme then applies.
const NO_DEFAULT = "";

/**
 * Platform UI theme settings: the theme users get when they have not chosen
 * one, and the themes withdrawn from their choice. Applies at each user's next
 * load of the application.
 */
export default function UiSettingsPage() {
  const { t } = useTranslation();
  const { showSuccess, showError } = useToast();
  const { data, isLoading, isError } = usePlatformUiSettingsQuery();
  const [save, { isLoading: isSaving }] = useSetPlatformUiSettingsMutation();

  const auditUids = data?.updated_by ? [data.updated_by] : [];
  const { data: auditUsers = [] } = useUsersByIdsQuery({ ids: auditUids }, { skip: auditUids.length === 0 });

  const [defaultTheme, setDefaultTheme] = useState<string>(NO_DEFAULT);
  const [hidden, setHidden] = useState<string[]>([]);
  const [serverError, setServerError] = useState<string | undefined>();
  useEffect(() => {
    if (!data) return;
    setDefaultTheme(data.default_theme ?? NO_DEFAULT);
    setHidden(data.hidden_themes ?? []);
  }, [data]);

  // Ids stored by another frontend version: kept as they are on save.
  const unknownIds = [...new Set([...hidden, ...(defaultTheme ? [defaultTheme] : [])])].filter(
    (id) => !(UI_THEMES as readonly string[]).includes(id),
  );
  const offeredCount = UI_THEMES.filter((theme) => !hidden.includes(theme)).length;
  const blocking =
    offeredCount === 0
      ? t("rework.uiSettings.errors.noneOffered")
      : defaultTheme && hidden.includes(defaultTheme)
        ? t("rework.uiSettings.errors.defaultHidden")
        : undefined;
  const isDirty =
    data !== undefined &&
    (defaultTheme !== (data.default_theme ?? NO_DEFAULT) ||
      [...hidden].sort().join() !== [...(data.hidden_themes ?? [])].sort().join());

  const toggleOffered = (theme: UiTheme, offered: boolean) => {
    setServerError(undefined);
    setHidden((current) => (offered ? current.filter((id) => id !== theme) : [...current, theme]));
  };

  const onSave = async () => {
    try {
      await save({
        setPlatformUiSettingsRequest: { default_theme: defaultTheme || null, hidden_themes: hidden },
      }).unwrap();
      setServerError(undefined);
      showSuccess({ summary: t("rework.uiSettings.saved") });
    } catch (error: unknown) {
      setServerError(normalizeApiError(error).detail);
      showError({ summary: t("rework.uiSettings.saveFailed") });
    }
  };

  const themeOptions = [
    { key: NO_DEFAULT, value: NO_DEFAULT, label: t("rework.uiSettings.default.none") },
    ...UI_THEMES.map((theme) => ({ key: theme, value: theme as string, label: t(UI_THEME_LABEL_KEYS[theme]) })),
    // A default saved by another frontend version stays visible instead of a blank trigger.
    ...(defaultTheme && !(UI_THEMES as readonly string[]).includes(defaultTheme)
      ? [{ key: defaultTheme, value: defaultTheme, label: defaultTheme, disabled: true }]
      : []),
  ];

  return (
    <div className={styles.page}>
      <PageHeader title={t("rework.uiSettings.title")} subtitle={t("rework.uiSettings.subtitle")} />

      {/* Without the stored settings the form would show defaults as if they were saved. */}
      {isError && (
        <p className={styles.error} role="alert">
          {t("rework.uiSettings.loadFailed")}
        </p>
      )}

      <section className={styles.card}>
        <div className={styles.field}>
          <h2 className={styles.fieldTitle}>{t("rework.uiSettings.default.title")}</h2>
          <p className={styles.fieldHint}>{t("rework.uiSettings.default.hint")}</p>
          <div className={styles.select}>
            <Select<string>
              size="xs"
              compact
              options={themeOptions}
              value={defaultTheme}
              onChange={(value) => {
                setServerError(undefined);
                setDefaultTheme(value);
              }}
              disabled={isLoading || isSaving || isError}
              ariaLabel={t("rework.uiSettings.default.title")}
            />
          </div>
        </div>

        <fieldset className={styles.field} disabled={isLoading || isSaving || isError}>
          <legend className={styles.fieldTitle}>{t("rework.uiSettings.offered.title")}</legend>
          <p className={styles.fieldHint}>{t("rework.uiSettings.offered.hint")}</p>
          <ul className={styles.themes}>
            {UI_THEMES.map((theme) => (
              <li key={theme}>
                <label className={styles.theme}>
                  <Checkbox
                    checked={!hidden.includes(theme)}
                    onChange={(event) => toggleOffered(theme, event.target.checked)}
                  />
                  {t(UI_THEME_LABEL_KEYS[theme])}
                </label>
              </li>
            ))}
          </ul>
          {unknownIds.length > 0 && (
            <p className={styles.fieldHint}>{t("rework.uiSettings.unknown", { ids: unknownIds.join(", ") })}</p>
          )}
        </fieldset>

        {(blocking ?? serverError) && (
          <p className={styles.error} role="alert">
            {blocking ?? serverError}
          </p>
        )}

        <div className={styles.footer}>
          {data?.updated_at && (
            <p className={styles.meta}>
              {t("rework.uiSettings.lastUpdated", {
                who: data.updated_by
                  ? userDisplayName(
                      data.updated_by,
                      auditUsers.find((user) => user.id === data.updated_by),
                    )
                  : t("rework.uiSettings.unknownAuthor"),
                when: new Date(data.updated_at).toLocaleString(),
              })}
            </p>
          )}
          <Button
            color="primary"
            variant="filled"
            size="small"
            icon={{ category: "outlined", type: "check", filled: false }}
            onClick={onSave}
            disabled={!isDirty || !!blocking || isSaving}
          >
            {isSaving ? t("rework.uiSettings.saving") : t("rework.uiSettings.save")}
          </Button>
        </div>
      </section>
    </div>
  );
}
