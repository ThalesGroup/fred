import { Outlet } from "react-router-dom";
import Sidebar from "@shared/organisms/Sidebar/Sidebar.tsx";
import { CssBaseline } from "@mui/material";
import styles from "./MainLayout.module.css";

export default function MainLayout() {
  return (
    <>
      <CssBaseline enableColorScheme />
      <div className={styles.mainLayout}>
        <nav className={styles.sidebar}>
          <Sidebar />
        </nav>
        <main className={styles.content}>
          <Outlet />
        </main>
      </div>
    </>
  );
}
