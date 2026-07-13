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

import TeamSelectionNavbar from "./TeamSelectionNavbar/TeamSelectionNavbar.tsx";
import TeamContentNavbar from "./TeamContentNavbar/TeamContentNavbar.tsx";
import styles from "./Sidebar.module.scss";
import UserProfile from "@shared/molecules/UserProfile/UserProfile.tsx";
import { useLocation } from "react-router-dom";
import MarketplaceNavbar from "./MarketplaceNavbar/MarketplaceNavbar.tsx";
import AdminNavbar from "./AdminNavbar/AdminNavbar.tsx";
export default function Sidebar() {
  const { pathname } = useLocation();

  const getSidebarMode = (): SidebarMode => {
    if (pathname.startsWith("/marketplace")) return "MARKETPLACE";
    if (pathname.startsWith("/admin")) return "ADMIN";
    return "TEAM";
  };
  const sidebarMode: SidebarMode = getSidebarMode();

  // In team settings the user is locked to one team; dim (and disable) the team
  // rail so attention lands on the coloured banner that names the team being
  // configured, instead of jumping to a plain-text settings page.
  const inTeamSettings = /^\/team\/[^/]+\/settings(\/|$)/.test(pathname);

  return (
    <div className={styles["sidebar-container"]}>
      <div className={styles["team-selection-container"]} data-dimmed={inTeamSettings}>
        <TeamSelectionNavbar />
      </div>
      {sidebarMode === "TEAM" && <TeamContentNavbar />}
      {sidebarMode === "MARKETPLACE" && <MarketplaceNavbar />}
      {sidebarMode === "ADMIN" && <AdminNavbar />}
      <div className={styles["user-profile-container"]}>
        <UserProfile />
      </div>
    </div>
  );
}

type SidebarMode = "TEAM" | "MARKETPLACE" | "ADMIN";
