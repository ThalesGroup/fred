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
import Switch from "@shared/atoms/Switch/Switch.tsx";
import { Tooltip } from "@shared/atoms/Tooltip/Tooltip.tsx";
import PageHeader from "@shared/molecules/PageHeader/PageHeader.tsx";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import { userDisplayName } from "@core/utils/userDisplayName.ts";
import { normalizeApiError } from "@core/errors/normalizeApiError.ts";
import { availableUiThemes, offeredUiThemes, uiThemeBase, uiThemeLabel } from "../../../../../app/uiThemes.ts";
import {
  usePlatformUiSettingsQuery,
  useSetPlatformUiSettingsMutation,
  useUsersByIdsQuery,
} from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import styles from "./UiSettingsPage.module.css";

const SWATCHES = ["primary", "secondary", "tertiary"] as const;
const MODES = ["light", "dark"] as const;

type StoredSettings = { default_theme?: string | null; hidden_themes?: string[] };

// Every shipped theme hidden (API or another version): users get them all, so show them offered.
function storedHidden(stored: StoredSettings): string[] {
  const hidden = stored.hidden_themes ?? [];
  const offered = offeredUiThemes(stored);
  return hidden.filter((id) => !(offered as string[]).includes(id));
}

// No default saved: shown as the first offered theme, which is what users get.
function storedDefault(stored: StoredSettings): string {
  return stored.default_theme ?? offeredUiThemes(stored)[0];
}

/**
 * Platform UI theme settings: one tile per theme to offer it to users and pick
 * the platform default. The default is always offered, and at least one theme
 * stays offered. Each change is saved at once and applies at each user's next
 * load of the application.
 */
export default function UiSettingsPage() {
  const { t } = useTranslation();
  const { showError } = useToast();
  const { data, isLoading, isFetching, isError } = usePlatformUiSettingsQuery();
  const [save, { isLoading: isSaving }] = useSetPlatformUiSettingsMutation();

  const auditUids = data?.updated_by ? [data.updated_by] : [];
  const { data: auditUsers = [] } = useUsersByIdsQuery({ ids: auditUids }, { skip: auditUids.length === 0 });

  const [defaultTheme, setDefaultTheme] = useState<string>(availableUiThemes()[0]);
  const [hidden, setHidden] = useState<string[]>([]);
  const [serverError, setServerError] = useState<string | undefined>();
  useEffect(() => {
    if (!data) return;
    setDefaultTheme(storedDefault(data));
    setHidden(storedHidden(data));
  }, [data]);

  // Ids stored by another frontend version: kept as they are on save.
  const unknownIds = [...new Set([...hidden, defaultTheme])].filter((id) => !availableUiThemes().includes(id));
  const offered = availableUiThemes().filter((theme) => !hidden.includes(theme));
  // Also while refetching after a save: a revert must never use settings older than the server's.
  const locked = isLoading || isFetching || isSaving || isError;

  // Saved at once; on failure the tiles go back to what the server holds.
  const persist = async (nextDefault: string, nextHidden: string[]) => {
    setServerError(undefined);
    setDefaultTheme(nextDefault);
    setHidden(nextHidden);
    try {
      await save({
        setPlatformUiSettingsRequest: { default_theme: nextDefault, hidden_themes: nextHidden },
      }).unwrap();
    } catch (error: unknown) {
      if (data) {
        setDefaultTheme(storedDefault(data));
        setHidden(storedHidden(data));
      }
      setServerError(normalizeApiError(error).detail);
      showError({ summary: t("rework.uiSettings.saveFailed") });
    }
  };

  return (
    <div className={styles.page}>
      <PageHeader title={t("rework.uiSettings.title")} subtitle={t("rework.uiSettings.subtitle")} />

      {/* Without the stored settings the tiles would show defaults as if they were saved. */}
      {isError && (
        <p className={styles.error} role="alert">
          {t("rework.uiSettings.loadFailed")}
        </p>
      )}

      <p className={styles.hint}>{t("rework.uiSettings.hint")}</p>

      <ul className={styles.themes}>
        {availableUiThemes().map((theme) => {
          const label = uiThemeLabel(theme, t);
          const isOffered = !hidden.includes(theme);
          const isDefault = theme === defaultTheme;
          return (
            <li key={theme} className={styles.tile}>
              {/* A wrapper, so the hint also shows on a disabled switch. */}
              <Tooltip text={t("rework.uiSettings.offeredTooltip")}>
                <span className={styles.toggle}>
                  <Switch
                    size="small"
                    checked={isOffered}
                    // The default and the last offered theme cannot be withdrawn.
                    disabled={locked || isDefault || (isOffered && offered.length === 1)}
                    onChange={(event) =>
                      persist(
                        defaultTheme,
                        event.target.checked ? hidden.filter((id) => id !== theme) : [...hidden, theme],
                      )
                    }
                    aria-label={t("rework.uiSettings.offeredLabel", { theme: label })}
                  />
                </span>
              </Tooltip>
              {/* One preview, light half then dark half; the theme's own tokens resolve inside each half. */}
              <span className={styles.preview}>
                {MODES.map((mode) => (
                  <span
                    key={mode}
                    className={styles.swatches}
                    data-ui-theme={theme}
                    data-ui-base-theme={uiThemeBase(theme)}
                    data-theme={mode}
                  >
                    {SWATCHES.map((role) => (
                      <span key={role} className={styles.swatch} style={{ backgroundColor: `var(--${role})` }} />
                    ))}
                  </span>
                ))}
              </span>
              {/* Only the theme's font and shapes apply here; colors stay those of the page. */}
              <span className={styles.name} data-ui-theme={theme} data-ui-base-theme={uiThemeBase(theme)} title={label}>
                {label}
              </span>
              <Button
                color="primary"
                variant={isDefault ? "text" : "outlined"}
                size="small"
                icon={isDefault ? { category: "outlined", type: "check", filled: false } : undefined}
                disabled={locked || isDefault || !isOffered}
                onClick={() => persist(theme, hidden)}
              >
                {isDefault ? t("rework.uiSettings.isDefault") : t("rework.uiSettings.setDefault")}
              </Button>
            </li>
          );
        })}
      </ul>

      {unknownIds.length > 0 && (
        <p className={styles.hint}>{t("rework.uiSettings.unknown", { ids: unknownIds.join(", ") })}</p>
      )}

      {serverError && (
        <p className={styles.error} role="alert">
          {serverError}
        </p>
      )}

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
    </div>
  );
}
