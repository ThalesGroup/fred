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

import TeamSelectionNavbar from "@shared/organisms/Sidebar/TeamSelectionNavbar/TeamSelectionNavbar.tsx";
import TeamContentNavbar from "@shared/organisms/Sidebar/TeamContentNavbar/TeamContentNavbar.tsx";
import styles from "./Sidebar.module.scss";
import UserProfile from "@shared/molecules/UserProfile/UserProfile.tsx";
import { useLocation } from "react-router-dom";
import MarketplaceNavbar from "@shared/organisms/Sidebar/MarketplaceNavbar/MarketplaceNavbar.tsx";

export default function Sidebar() {
  const { pathname } = useLocation();

  const sidebarMode: SidebarMode = pathname.startsWith("/marketplace") ? "MARKETPLACE" : "TEAM";

  return (
    <div className={styles["sidebar-container"]}>
      <div className={styles["team-selection-container"]}>
        <TeamSelectionNavbar />
      </div>
      {sidebarMode === "TEAM" && <TeamContentNavbar />}
      {sidebarMode === "MARKETPLACE" && <MarketplaceNavbar />}
      <div className={styles["user-profile-container"]}>
        <UserProfile />
      </div>
    </div>
  );
}

type SidebarMode = "TEAM" | "MARKETPLACE";
