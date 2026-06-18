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
import { useTranslation } from "react-i18next";
import ButtonGroup from "@shared/atoms/ButtonGroup/ButtonGroup.tsx";
import UserAvatar from "@shared/atoms/UserAvatar/UserAvatar.tsx";
import { useContext } from "react";
import { ApplicationContext } from "../../../../app/ApplicationContextProvider.tsx";
import { KeyCloakService } from "../../../../security/KeycloakService.ts";
import { useFrontendProperties } from "../../../../hooks/useFrontendProperties.ts";
import { Link, useNavigate } from "react-router-dom";

export default function UserSettingsPage() {
  const navigate = useNavigate();
  const { siteTitle, siteSubtitle } = useFrontendProperties();
  const { t } = useTranslation();
  const { themeMode, setThemeMode } = useContext(ApplicationContext);
  const { i18n } = useTranslation();

  const userFullName = KeyCloakService.GetUserFullName();
  const username = KeyCloakService.GetUserName();
  const userEmail = KeyCloakService.GetUserMail();
  const userRoles = KeyCloakService.GetUserRoles();

  return (
    <div className={styles.userSettingsPageRoot}>
      <div className={styles.userSettingsPage}>
        <div className={styles.userSettingsHeader}>
          <Button
            color={"primary"}
            variant={"text"}
            size={"medium"}
            icon={{ category: "outlined", type: "arrow_back", filled: true }}
            onClick={() => navigate(-1)}
          >
            {t("rework.back")}
          </Button>
          <span className={styles.userSettingsHeaderTitle}>{t("rework.userSettings.title")}</span>
          <Button
            color={"error"}
            variant={"filled"}
            size={"medium"}
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
            {userRoles.includes("admin") && (
              <span className={styles.userSettingsIdentityRole}>{userRoles.join(", ")}</span>
            )}
          </div>
        </div>
        <div className={styles.userSettingsApplication}>
          <ButtonGroup
            defaultSelectedIndex={themeMode === "dark" ? 0 : themeMode === "system" ? 1 : 2}
            items={[
              {
                label: t("rework.userSettings.app.dark"),
                icon: { category: "outlined", type: "dark_mode" },
                onClick: () => setThemeMode("dark"),
              },
              {
                label: t("rework.userSettings.app.system"),
                icon: { category: "outlined", type: "desktop_windows" },
                onClick: () => setThemeMode("system"),
              },
              {
                label: t("rework.userSettings.app.light"),
                icon: { category: "outlined", type: "light_mode" },
                onClick: () => setThemeMode("light"),
              },
            ]}
            size={"medium"}
            color={"secondary"}
          ></ButtonGroup>
          <ButtonGroup
            defaultSelectedIndex={i18n.language === "fr" ? 0 : 1}
            items={[
              {
                label: t("rework.userSettings.app.french"),
                onClick: () => i18n.changeLanguage("fr"),
              },
              {
                label: t("rework.userSettings.app.english"),
                onClick: () => i18n.changeLanguage("en"),
              },
            ]}
            size={"medium"}
            color={"secondary"}
          ></ButtonGroup>
        </div>
        {/*  <div className={styles.userSettingsConversation}>
        <TextArea
          disabled={true}
          label={t("rework.userSettings.conversationProfile.title")}
          placeholder={t("rework.userSettings.conversationProfile.placeholder", { agentsNicknamePlural })}
          maxLength={300}
        ></TextArea>
      </div>*/}
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
