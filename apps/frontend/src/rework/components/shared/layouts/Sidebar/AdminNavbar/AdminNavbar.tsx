// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { useTranslation } from "react-i18next";
import NavigationMenu from "@shared/molecules/NavigationMenu/NavigationMenu";
import NavPanelHeader from "@shared/molecules/NavPanelHeader/NavPanelHeader";
import { useManagerPlatformAdmin } from "@core/hooks/useManagerPlatformAdmin";
import styles from "./AdminNavbar.module.css";

export default function AdminNavbar() {
  const { t } = useTranslation();
  const manager = useManagerPlatformAdmin();
  return (
    <div className={styles.adminNavbarContainer}>
      <NavPanelHeader title={t("rework.sidebar.admin.title")} />
      <NavigationMenu
        items={
          manager.isAdmin
            ? [
                {
                  type: "link",
                  label: t("rework.provisioning.title"),
                  icon: { category: "outlined", type: "upload", filled: false },
                  linkProps: { to: "/admin/provisioning" },
                },
              ]
            : []
        }
      />
    </div>
  );
}
