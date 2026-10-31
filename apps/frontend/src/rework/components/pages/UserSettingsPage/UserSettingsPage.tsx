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

import styles from "./UserSettingsPage.module.scss";
import Button from "@shared/atoms/Button/Button.tsx";
import StatusBadge from "@shared/atoms/StatusBadge/StatusBadge.tsx";
import { useTranslation } from "react-i18next";
import ButtonGroup from "@shared/atoms/ButtonGroup/ButtonGroup.tsx";
import Select from "@shared/molecules/Select/Select.tsx";
import DataTable, { type DataTableColumn } from "@shared/molecules/DataTable/LocalizedDataTable.tsx";
import type { MySpace } from "../../../../slices/controlPlane/controlPlaneOpenApi.ts";
import UserAvatar from "@shared/atoms/UserAvatar/UserAvatar.tsx";
import { useContext, useRef } from "react";
import { useApiErrorToast } from "@core/hooks/useApiErrorToast.ts";
import { ApplicationContext } from "../../../../app/ApplicationContextProvider.tsx";
import { uiThemeLabel, type UiTheme } from "../../../../app/uiThemes.ts";
import { saveUserPreference, updateCurrentUserPreference } from "../../../../app/userPreferences.ts";
import { KeyCloakService } from "../../../../security/KeycloakService.ts";
import { useFrontendProperties } from "../../../../hooks/useFrontendProperties.ts";
import { Link, useNavigate } from "react-router-dom";
import { useMeQuery, useMySpacesQuery } from "../../../../slices/controlPlane/controlPlaneApiEnhancements.ts";
import { useRefetchOnWindowFocus } from "@core/hooks/crossSessionRefresh";
import { getConfig } from "../../../../common/config";

export default function UserSettingsPage() {
  const navigate = useNavigate();
  const { siteTitle, siteSubtitle } = useFrontendProperties();
  const { t } = useTranslation();
  const { themeMode, setThemeMode, uiTheme, setUiTheme, offeredUiThemes } = useContext(ApplicationContext);
  const { i18n } = useTranslation();
  const confirmedLanguage = useRef(i18n.language);
  const languageChange = useRef(0);

  const userId = KeyCloakService.GetUserId();
  // Manager uses its fixed mock subject when user authentication is disabled.
  const managerUserId = getConfig().user_auth.enabled ? userId : "admin";
  const userFullName = KeyCloakService.GetUserFullName() || KeyCloakService.GetUserName() || userId;
  const username = KeyCloakService.GetUserName();
  const userEmail = KeyCloakService.GetUserMail();
  const me = useMeQuery(undefined, { refetchOnMountOrArgChange: 60 });
  useRefetchOnWindowFocus(me.refetch, false);
  const memberships = useMySpacesQuery(undefined, { refetchOnMountOrArgChange: true });
  useRefetchOnWindowFocus(memberships.refetch, false);
  const spacesById = new Map(memberships.currentData?.map((space) => [space.id, space]));
  const { notifyApiError } = useApiErrorToast();
  const spaceColumns: DataTableColumn<MySpace>[] = [
    {
      label: t("rework.userSettings.spaceColumn"),
      size: "minmax(12rem, 1fr)",
      cellRenderer: (space) => {
        const path = (space.kind === "personal" ? [space.organization_id, ...space.path] : space.path)
          .map((id) => spacesById.get(id))
          .filter((ancestor) => ancestor !== undefined)
          .map((ancestor) => (ancestor.kind === "personal" ? t("rework.userSettings.personalSpace") : ancestor.name))
          .join(" / ");
        return `${t(`rework.userSettings.spaceKinds.${space.kind}`)} : ${path}`;
      },
    },
    {
      label: t("rework.userSettings.rolesColumn"),
      size: "minmax(14rem, 1fr)",
      cellRenderer: (space) => (
        <div className={styles.userSettingsCardRow}>
          {space.roles.map((role) => (
            <StatusBadge key={role} label={t(`rework.supervision.roleNames.${role}`)} tone="neutral" />
          ))}
        </div>
      ),
    },
  ];

  const notifyPreferenceError = (error: unknown) =>
    notifyApiError(error, {
      summary: t("rework.userSettings.app.saveFailed"),
      fallbackDetail: t("rework.userSettings.app.saveFailedDetail"),
    });

  const changeLanguage = (language: "fr" | "en") => {
    const change = ++languageChange.current;
    void i18n.changeLanguage(language);
    void saveUserPreference({ language })
      .then(() => {
        confirmedLanguage.current = language;
        updateCurrentUserPreference({ language });
      })
      .catch((error) => {
        if (change === languageChange.current) {
          void i18n.changeLanguage(confirmedLanguage.current);
          notifyPreferenceError(error);
        }
      });
  };

  return (
    <div className={styles.userSettingsPageRoot}>
      <div className={styles.userSettingsPage}>
        <div className={styles.userSettingsHeader}>
          <Button
            color={"primary"}
            variant={"text"}
            size={"small"}
            icon={{ category: "outlined", type: "arrow_back", filled: true }}
            onClick={() => navigate(-1)}
          >
            {t("rework.back")}
          </Button>
          <span className={styles.userSettingsHeaderTitle}>{t("rework.userSettings.title")}</span>
          <Button
            color={"error"}
            variant={"filled"}
            size={"small"}
            icon={{ category: "outlined", type: "logout", filled: true }}
            onClick={KeyCloakService.CallLogout}
          >
            {t("rework.userSettings.disconnect")}
          </Button>
        </div>
        <div className={styles.userSettingsDescription}>
          <UserAvatar name={userFullName} size={"large"} />
          <div className={styles.userSettingsIdentity}>
            <span className={styles.userSettingsIdentityName}>{username}</span>
            <span className={styles.userSettingsIdentityFullname}>{userFullName}</span>
            <span className={styles.userSettingsIdentityEmail}>{userEmail}</span>
          </div>
        </div>
        <section className={styles.userSettingsCard} aria-labelledby="profile-access-title">
          <h2 id="profile-access-title" className={styles.userSettingsCardTitle}>
            {t("rework.userSettings.accessTitle")}
          </h2>
          {me.isLoading || me.isFetching ? (
            <span role="status" className={styles.userSettingsIdentityRole}>
              {t("common.loading")}
            </span>
          ) : me.isError || me.data?.user_id !== managerUserId ? (
            <div role="alert" className={styles.userSettingsIdentityRole}>
              <span>{t("rework.manager.unavailable")}</span>
              <Button color="primary" variant="text" size="small" onClick={() => void me.refetch()}>
                {t("rework.provisioning.retryAuthority")}
              </Button>
            </div>
          ) : (
            <div className={styles.userSettingsCardRow}>
              <span className={styles.userSettingsIdentityRole}>
                {t("rework.userSettings.platformRoles", {
                  roles: me.data.platform_roles.length ? "" : t("rework.userSettings.noPlatformRoles"),
                })}
              </span>
              {me.data.platform_roles.map((role) => (
                <StatusBadge key={role} label={t(`rework.platformRoles.roles.${role}`)} tone="neutral" />
              ))}
            </div>
          )}
          {!me.isError &&
            !me.isLoading &&
            !me.isFetching &&
            me.data?.user_id === managerUserId &&
            (memberships.isLoading || memberships.isFetching ? (
              <span role="status" className={styles.userSettingsIdentityRole}>
                {t("common.loading")}
              </span>
            ) : memberships.isError ? (
              <div role="alert" className={styles.userSettingsIdentityRole}>
                <span>{t("rework.manager.unavailable")}</span>
                <Button color="primary" variant="text" size="small" onClick={() => void memberships.refetch()}>
                  {t("rework.provisioning.retryAuthority")}
                </Button>
              </div>
            ) : memberships.currentData?.length ? (
              <DataTable
                columns={spaceColumns}
                data={memberships.currentData}
                rowKey={(space) => space.id}
                size="small"
              />
            ) : (
              <div className={styles.userSettingsIdentityRole}>{t("rework.userSettings.noSpaces")}</div>
            ))}
        </section>
        <section className={styles.userSettingsCard}>
          <h2 className={styles.userSettingsCardTitle}>{t("rework.userSettings.app.interfaceTitle")}</h2>
          <div className={styles.userSettingsCardRow}>
            {/* Nothing to choose when the platform offers a single theme. */}
            {offeredUiThemes.length > 1 && (
              <div className={styles.userSettingsThemeSelect}>
                <Select<UiTheme>
                  size="xs"
                  compact
                  options={offeredUiThemes.map((theme) => ({
                    key: theme,
                    value: theme,
                    label: uiThemeLabel(theme, t),
                  }))}
                  value={uiTheme}
                  onChange={(theme) => setUiTheme(theme, notifyPreferenceError)}
                  ariaLabel={t("rework.userSettings.app.uiThemeAria")}
                />
              </div>
            )}
            <ButtonGroup
              variant="radio"
              aria-label={t("rework.userSettings.app.themeAria")}
              selectedIndex={themeMode === "light" ? 0 : themeMode === "dark" ? 1 : 2}
              items={[
                {
                  label: t("rework.userSettings.app.light"),
                  icon: { category: "outlined", type: "light_mode" },
                  onClick: () => setThemeMode("light", notifyPreferenceError),
                },
                {
                  label: t("rework.userSettings.app.dark"),
                  icon: { category: "outlined", type: "dark_mode" },
                  onClick: () => setThemeMode("dark", notifyPreferenceError),
                },
                {
                  label: t("rework.userSettings.app.system"),
                  icon: { category: "outlined", type: "desktop_windows" },
                  onClick: () => setThemeMode("system", notifyPreferenceError),
                },
              ]}
              size={"small"}
              color={"secondary"}
              surface="surface-container-lowest"
            ></ButtonGroup>
          </div>
        </section>
        <div className={styles.userSettingsApplication}>
          <ButtonGroup
            variant="radio"
            aria-label={t("rework.userSettings.app.languageAria")}
            selectedIndex={i18n.language === "fr" ? 0 : 1}
            items={[
              {
                label: t("rework.userSettings.app.french"),
                onClick: () => changeLanguage("fr"),
              },
              {
                label: t("rework.userSettings.app.english"),
                onClick: () => changeLanguage("en"),
              },
            ]}
            size={"small"}
            color={"secondary"}
          ></ButtonGroup>
        </div>
        <div className={styles.userSettingsLegals}>
          <Link to={"/gdpr"}>
            <Button color={"primary"} variant={"text"} size={"medium"}>
              {t("rework.userSettings.accessGdpr", { siteTitle, siteSubtitle })}
            </Button>
          </Link>
          <Link to={"/gcu"}>
            <Button color={"primary"} variant={"text"} size={"medium"}>
              {t("rework.userSettings.accessGcu")}
            </Button>
          </Link>
          <Link to={"/release-notes"}>
            <Button color={"primary"} variant={"text"} size={"medium"}>
              {t("rework.userSettings.accessReleaseNotes")}
            </Button>
          </Link>
        </div>
      </div>
    </div>
  );
}
