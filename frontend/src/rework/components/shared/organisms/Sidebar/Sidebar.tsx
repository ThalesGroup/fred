import TeamSelectionNavbar from "@shared/organisms/Sidebar/TeamSelectionNavbar/TeamSelectionNavbar.tsx";
import TeamContentNavbar from "@shared/organisms/Sidebar/TeamContentNavbar/TeamContentNavbar.tsx";
import styles from "./Sidebar.module.scss";
import UserProfile from "@shared/molecules/UserProfile/UserProfile.tsx";
import { useLocation } from "react-router-dom";
import MarketplaceNavbar from "@shared/organisms/Sidebar/MarketplaceNavbar/MarketplaceNavbar.tsx";

export default function Sidebar() {
  const { pathname } = useLocation();

  const sidebarMode = pathname.startsWith("/marketplace") ? SidebarMode.MARKETPLACE : SidebarMode.TEAM;

  return (
    <div className={styles["sidebar-container"]}>
      <div className={styles["team-selection-container"]}>
        <TeamSelectionNavbar />
      </div>
      {sidebarMode === SidebarMode.TEAM && <TeamContentNavbar />}
      {sidebarMode === SidebarMode.MARKETPLACE && <MarketplaceNavbar />}
      <div className={styles["user-profile-container"]}>
        <UserProfile />
      </div>
    </div>
  );
}

enum SidebarMode {
  TEAM,
  MARKETPLACE,
}
