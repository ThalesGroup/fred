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

import WorkingOrganizationRoute from "@core/guards/WorkingOrganizationRoute";
import { useUserCapabilities } from "@hooks/useUserCapabilities.ts";
import { skipsBusinessBootstrap } from "@core/utils/adminRoutes";
import OrganizationNavPanel from "./OrganizationNavPanel/OrganizationNavPanel.tsx";
import TeamContentNavbar from "./TeamContentNavbar/TeamContentNavbar.tsx";
import { isChatRoute, useChatNavPanel } from "@core/hooks/useChatNavPanel";
import { isWeaverContentRoute } from "@core/utils/weaverContentRoute";
import { isOrganizationRoute, isSpaceSettingsRoute } from "@core/utils/organizationRoute";
import { useWorkingOrganization } from "@core/hooks/useWorkingOrganization";
import styles from "./Sidebar.module.scss";
import UserProfile from "@shared/molecules/UserProfile/UserProfile.tsx";
import { useLocation } from "react-router-dom";
import MarketplaceNavbar from "./MarketplaceNavbar/MarketplaceNavbar.tsx";
import AdminNavbar from "./AdminNavbar/AdminNavbar.tsx";
export default function Sidebar({
  navigation = true,
  platformArea = false,
  platformOnly = false,
  organizationArea = false,
}: {
  navigation?: boolean;
  /** The page belongs to the platform admin space. */
  platformArea?: boolean;
  /** A platform admin with no organization membership. */
  platformOnly?: boolean;
  organizationArea?: boolean;
}) {
  const { pathname } = useLocation();
  const { collapsed } = useChatNavPanel();

  return (
    <div className={styles["sidebar-container"]}>
      {navigation && !platformOnly && <BootstrapSubscription />}
      <div className={styles["nav-panel-card"]} hidden={collapsed && isChatRoute(pathname)}>
        {navigation && (
          <WorkingOrganizationRoute silent>
            <div className={styles["nav-panel-body"]}>
              <NavPanel platformArea={platformArea} />
            </div>
          </WorkingOrganizationRoute>
        )}
        <div className={styles["user-profile-container"]}>
          <UserProfile
            agentManagement={isWeaverContentRoute(pathname)}
            admitted={navigation}
            platformArea={platformArea}
            organizationArea={organizationArea}
            platformOnly={platformOnly}
          />
        </div>
      </div>
    </div>
  );
}

/** Keeps the frontend bootstrap subscribed across routes, so admin gating stays current. */
function BootstrapSubscription() {
  const { pathname } = useLocation();
  useUserCapabilities(skipsBusinessBootstrap(pathname));
  return null;
}

type SidebarMode = "ORGANIZATION" | "TEAM" | "MARKETPLACE" | "ADMIN";

// Reads the working organization here, not in Sidebar: onboarding renders the sidebar before its provider.
function NavPanel({ platformArea }: { platformArea: boolean }) {
  const { pathname } = useLocation();
  const { organizationId } = useWorkingOrganization();
  const getSidebarMode = (): SidebarMode => {
    if (platformArea) return "ADMIN";
    // The organization's settings keep the space settings menu of TeamContentNavbar.
    if (isOrganizationRoute(pathname, organizationId) && !isSpaceSettingsRoute(pathname)) return "ORGANIZATION";
    if (pathname.startsWith("/marketplace")) return "MARKETPLACE";
    if (pathname.startsWith("/admin")) return "ADMIN";
    return "TEAM";
  };
  const sidebarMode = getSidebarMode();
  return (
    <>
      {sidebarMode === "ORGANIZATION" && <OrganizationNavPanel />}
      {sidebarMode === "TEAM" && <TeamContentNavbar />}
      {sidebarMode === "MARKETPLACE" && <MarketplaceNavbar />}
      {sidebarMode === "ADMIN" && <AdminNavbar platformArea={platformArea} />}
    </>
  );
}
