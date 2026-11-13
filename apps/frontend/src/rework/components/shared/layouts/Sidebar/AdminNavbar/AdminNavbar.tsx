import { getConfig } from "../../../../../../common/config";
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
import SpaceHeader from "@shared/molecules/SpaceHeader/SpaceHeader.tsx";
import type { NavigationMenuItemProps } from "@shared/molecules/NavigationMenu/NavigationMenuItem/NavigationMenuItem.tsx";
import { useTranslation } from "react-i18next";
import { useSelector } from "react-redux";
import { useLocation } from "react-router-dom";
import { useOrganizationSupervisionAccess } from "@core/hooks/useOrganizationSupervisionAccess";
import { useOrganizationOwner } from "@core/hooks/useOrganizationOwner";
import { useManagerPlatformAdmin } from "@core/hooks/useManagerPlatformAdmin";
import { useSelfTestAccess } from "@core/hooks/useSelfTestAccess";
import { useUserCapabilities } from "@hooks/useUserCapabilities.ts";
import { organizationOwnerPages } from "@core/guards/organizationOwnerPages";
import { selectActiveCount } from "../../../../../features/tasks/taskSlice";
import { useWorkingOrganization } from "@core/hooks/useWorkingOrganization";
import styles from "./AdminNavbar.module.css";

// One ordered list for the menu and the Admin landing: a page the caller cannot open is
// hidden rather than left as a link to `/unauthorized`.
function BusinessAdminNavbar() {
  const { t } = useTranslation();
  const activeTaskCount = useSelector(selectActiveCount);
  const { pathname } = useLocation();
  const capabilities = useUserCapabilities(
    ["/admin/features", "/admin/supervision"].includes(pathname.replace(/\/$/, "")),
  );
  const organization = useOrganizationOwner();
  const supervision = useOrganizationSupervisionAccess();
  const pages = organizationOwnerPages({
    capabilities: { ...capabilities, canManageFeatures: organization.isOwner },
    supervision: supervision.offered,
    platformAccessEnabled: !!getConfig()?.platform_access_enabled,
  });
  const navigationItems: NavigationMenuItemProps[] = pages.map((page) => ({
    type: "link",
    label: t(page.labelKey),
    icon: page.icon,
    linkProps: { to: page.to },
    badge: page.to === "/admin/tasks" && activeTaskCount > 0 ? activeTaskCount : undefined,
  }));
  return <NavigationMenu items={navigationItems} />;
}

/** Organization selection belongs to the profile; this link only changes admin area. */
export default function AdminNavbar({ platformArea = false }: { platformArea?: boolean }) {
  const { t } = useTranslation();
  const manager = useManagerPlatformAdmin();
  const { organization } = useWorkingOrganization();
  const supervision = useOrganizationSupervisionAccess();
  const owner = useOrganizationOwner();
  const canChangeArea = platformArea ? supervision.offered || owner.isOwner : manager.isAdmin;
  return (
    <div className={styles.adminNavbarContainer}>
      <SpaceHeader
        eyebrow={platformArea ? t("rework.sidebar.admin.platformTitle") : organization?.name}
        title={t("rework.sidebar.admin.title")}
      />
      {canChangeArea && (
        <NavigationMenu
          items={[
            {
              type: "link",
              label: platformArea
                ? (organization?.name ?? t("rework.sidebar.admin.title"))
                : t("rework.sidebar.admin.platformTitle"),
              icon: { category: "outlined", type: platformArea ? "groups" : "admin_panel_settings" },
              linkProps: { to: platformArea ? "/admin" : "/admin/organizations" },
            },
          ]}
        />
      )}
      {platformArea ? <PlatformAdminNavbar /> : <BusinessAdminNavbar />}
    </div>
  );
}

/** Platform pages only: organization pages are reached through the switcher. */
function PlatformAdminNavbar() {
  const { t } = useTranslation();
  const selfTest = useSelfTestAccess();
  return (
    <NavigationMenu
      items={[
        {
          type: "link",
          label: t("rework.organizations.title"),
          icon: { category: "outlined", type: "groups", filled: false },
          linkProps: { to: "/admin/organizations" },
        },
        {
          type: "link",
          label: t("rework.provisioning.title"),
          icon: { category: "outlined", type: "upload", filled: false },
          linkProps: { to: "/admin/provisioning" },
        },
        {
          type: "link",
          label: t("rework.monitor.title"),
          icon: { category: "outlined", type: "monitoring", filled: false },
          linkProps: { to: "/admin/monitor" },
        },
        ...(selfTest.allowed
          ? [
              {
                type: "link",
                label: t("rework.sidebar.admin.menu.selftest"),
                icon: { category: "outlined", type: "check_circle", filled: false },
                linkProps: { to: "/admin/self-test" },
              } satisfies NavigationMenuItemProps,
            ]
          : []),
      ]}
    />
  );
}
