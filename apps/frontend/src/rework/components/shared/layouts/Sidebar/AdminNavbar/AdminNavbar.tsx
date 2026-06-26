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

import NavigationMenu from "@shared/molecules/NavigationMenu/NavigationMenu.tsx";
import type { NavigationMenuItemProps } from "@shared/molecules/NavigationMenu/NavigationMenuItem/NavigationMenuItem.tsx";
import { useTranslation } from "react-i18next";
import { useSelector } from "react-redux";
import { selectActiveCount } from "../../../../../features/tasks/taskSlice";
import styles from "./AdminNavbar.module.css";

export default function AdminNavbar() {
  const { t } = useTranslation();
  const activeTaskCount = useSelector(selectActiveCount);

  const navigationItems: NavigationMenuItemProps[] = [
    {
      type: "link",
      label: t("rework.sidebar.admin.menu.teams"),
      icon: { category: "outlined", type: "groups", filled: true },
      linkProps: { to: "/admin/teams" },
    },
    {
      type: "link",
      label: t("rework.sidebar.admin.menu.tasks"),
      icon: { category: "outlined", type: "build", filled: false },
      linkProps: { to: "/admin/tasks" },
      badge: activeTaskCount > 0 ? activeTaskCount : undefined,
    },
    {
      type: "link",
      label: t("rework.sidebar.admin.menu.analytics"),
      icon: { category: "outlined", type: "analytics", filled: false },
      linkProps: { to: "/admin/analytics" },
    },
    {
      type: "link",
      label: t("rework.sidebar.admin.menu.migration"),
      icon: { category: "outlined", type: "sync_alt", filled: false },
      linkProps: { to: "/admin/migration" },
    },
    {
      type: "link",
      label: t("rework.sidebar.admin.menu.selftest"),
      icon: { category: "outlined", type: "check_circle", filled: false },
      linkProps: { to: "/admin/self-test" },
    },
  ];

  return (
    <div className={styles.adminNavbarContainer}>
      <div className={styles.adminNavbarTitle}>{t("rework.sidebar.admin.title")}</div>
      <NavigationMenu items={navigationItems} />
    </div>
  );
}
