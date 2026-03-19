import TeamSelectionNavbar from "@shared/organisms/Sidebar/TeamSelectionNavbar/TeamSelectionNavbar.tsx";
import TeamContentNavbar from "@shared/organisms/Sidebar/TeamContentNavbar/TeamContentNavbar.tsx";
import styles from "./Sidebar.module.scss";
import UserProfile from "@shared/molecules/UserProfile/UserProfile.tsx";
import { useLocation } from "react-router-dom";

export default function Sidebar() {
  const { pathname } = useLocation();

  const smallNavbar = pathname.startsWith("/teams");

  return (
    <div className={`${styles["sidebar-container"]} ${smallNavbar ? styles["small"] : ""}`}>
      <div className={styles["team-selection-container"]}>
        <TeamSelectionNavbar />
      </div>
      {!smallNavbar && (
        <>
          <TeamContentNavbar />
          <div className={styles["user-profile-container"]}>
            <UserProfile />
          </div>
        </>
      )}
    </div>
  );
}
