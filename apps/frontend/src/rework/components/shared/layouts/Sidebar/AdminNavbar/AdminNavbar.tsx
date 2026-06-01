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

import styles from "./AdminNavbar.module.css";
import { useTranslation } from "react-i18next";
import NavigationMenu from "@shared/molecules/NavigationMenu/NavigationMenu.tsx";
import type { NavigationMenuItemProps } from "@shared/molecules/NavigationMenu/NavigationMenuItem/NavigationMenuItem.tsx";

export default function AdminNavbar() {
  const { t } = useTranslation();

  const navigationItems: NavigationMenuItemProps[] = [
    {
      type: "link",
      label: t("rework.sidebar.admin.menu.teams"),
      icon: { category: "outlined", type: "groups", filled: true },
      linkProps: { to: "/admin/teams" },
    },
  ];

  return (
    <div className={styles.adminNavbarContainer}>
      <div className={styles.adminNavbarTitle}>{t("rework.sidebar.admin.title")}</div>
      <NavigationMenu items={navigationItems} />
    </div>
  );
}
