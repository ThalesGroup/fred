import { Outlet } from "react-router-dom";
import Sidebar from "@shared/organisms/Sidebar/Sidebar.tsx";
import { CssBaseline } from "@mui/material";
import MigrationBanner from "src/migration/MigrationBanner.tsx"; // KEA-MIGRATION (throwaway)
import styles from "./MainLayout.module.css";

export default function MainLayout() {
  return (
    <>
      <CssBaseline enableColorScheme />
      <div className={styles.mainLayout}>
        <nav className={styles.sidebar}>
          <Sidebar />
        </nav>
        <div className={styles.contentArea}>
          <MigrationBanner /> {/* KEA-MIGRATION (throwaway) */}
          <main className={styles.content}>
            <Outlet />
          </main>
        </div>
      </div>
    </>
  );
}
