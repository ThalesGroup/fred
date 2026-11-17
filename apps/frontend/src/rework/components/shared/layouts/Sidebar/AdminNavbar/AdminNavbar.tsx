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
import SpaceHeader, { type SpaceHeaderProps } from "@shared/molecules/SpaceHeader/SpaceHeader.tsx";
import type { NavigationMenuItemProps } from "@shared/molecules/NavigationMenu/NavigationMenuItem/NavigationMenuItem.tsx";
import { useTranslation } from "react-i18next";
import { useSelector } from "react-redux";
import { useLocation, useNavigate } from "react-router-dom";
import { useWorkingOrganization } from "@core/hooks/useWorkingOrganization";
import { isOrganizationAdminRoute } from "@core/utils/adminRoutes";
import SpaceUpLink from "../SpaceUpLink/SpaceUpLink.tsx";
import { useOrganizationSupervisionAccess } from "@core/hooks/useOrganizationSupervisionAccess";
import { useOrganizationOwner } from "@core/hooks/useOrganizationOwner";
import { useManagerPlatformAdmin } from "@core/hooks/useManagerPlatformAdmin";
import { useSelfTestAccess } from "@core/hooks/useSelfTestAccess";
import { useUserCapabilities } from "@hooks/useUserCapabilities.ts";
import { organizationOwnerPages } from "@core/guards/organizationOwnerPages";
import { selectActiveCount } from "../../../../../features/tasks/taskSlice";
import AdminSpaceSwitcher, { type AdminSpace } from "./AdminSpaceSwitcher";
import styles from "./AdminNavbar.module.css";

// One ordered list for the menu and the Admin landing: a page the caller cannot open is
// hidden rather than left as a link to `/unauthorized`.
function BusinessAdminNavbar() {
  const { t } = useTranslation();
  const activeTaskCount = useSelector(selectActiveCount);
  const { pathname } = useLocation();
  const capabilities = useUserCapabilities(isOrganizationAdminRoute(pathname));
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

/** One header for both spaces, so the switcher keeps focus across a space change. */
export default function AdminNavbar({ platformArea = false }: { platformArea?: boolean }) {
  return (
    <div className={styles.adminNavbarContainer}>
      <BackToOrganization />
      <AdminSpaceHeader current={platformArea ? "platform" : "organization"} />
      {platformArea ? <PlatformAdminNavbar /> : <BusinessAdminNavbar />}
    </div>
  );
}

/** Without a rail, the console leaves through the working organization's panel. */
function BackToOrganization() {
  const navigate = useNavigate();
  const { organization } = useWorkingOrganization();
  return organization ? (
    <SpaceUpLink name={organization.name} kind="organization" onClick={() => navigate("/home")} />
  ) : null;
}

/** One available context stays read-only; several also enable switching. */
function AdminSpaceHeader({ current }: { current: AdminSpace }) {
  const { t } = useTranslation();
  const manager = useManagerPlatformAdmin();
  const { organization, organizations, selectOrganization } = useOrganizationSupervisionAccess();
  // Small line: the section; big line: whose administration.
  const identity: SpaceHeaderProps = {
    eyebrow: t("rework.sidebar.admin.title"),
    title: current === "platform" ? t("rework.sidebar.admin.platformTitle") : (organization?.name ?? ""),
  };
  if (organizations.length + Number(manager.isAdmin) > 1)
    return (
      <AdminSpaceSwitcher
        current={current}
        identity={identity}
        organizations={organizations}
        organizationId={organization?.id}
        onSelectOrganization={selectOrganization}
        platformAdmin={manager.isAdmin}
      />
    );
  return <SpaceHeader {...identity} />;
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
