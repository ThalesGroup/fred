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

import { type PropsWithChildren } from "react";
import { Outlet, useLocation } from "react-router-dom";
import Sidebar from "@shared/layouts/Sidebar/Sidebar.tsx";
import TeamAdminCharterGate from "@shared/organisms/TeamAdminCharterGate/TeamAdminCharterGate";
import { useTaskPolling } from "../../../../features/tasks/useTaskPolling";
import { useTaskRehydration } from "../../../../features/tasks/useTaskRehydration";
import { useManagerPlatformAdmin } from "@core/hooks/useManagerPlatformAdmin";
import styles from "./MainLayout.module.css";

function AdmittedWorkspace() {
  useTaskRehydration();
  useTaskPolling();
  return (
    <TeamAdminCharterGate>
      <Outlet />
    </TeamAdminCharterGate>
  );
}

export default function MainLayout({ children, navigation = true }: PropsWithChildren<{ navigation?: boolean }>) {
  const { isAdmin } = useManagerPlatformAdmin(!navigation);
  const { pathname } = useLocation();
  const organizationArea = ["/admin/features", "/admin/supervision"].includes(pathname.replace(/\/$/, ""));
  return (
    <div className={styles.mainLayout}>
      <nav className={styles.sidebar}>
        <Sidebar
          navigation={navigation}
          platformArea={isAdmin && !organizationArea}
          organizationArea={organizationArea}
        />
      </nav>
      <main className={styles.content}>
        {navigation ? isAdmin || organizationArea ? <Outlet /> : <AdmittedWorkspace /> : children}
      </main>
    </div>
  );
}
