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

import { Outlet } from "react-router-dom";
import Sidebar from "@shared/layouts/Sidebar/Sidebar.tsx";
import { useTaskSseManager } from "../../../../features/tasks/useTaskSseManager.ts";
import { useTaskRehydration } from "../../../../features/tasks/useTaskRehydration.ts";
import styles from "./MainLayout.module.css";

export default function MainLayout() {
  useTaskRehydration();
  useTaskSseManager();
  return (
    <div className={styles.mainLayout}>
      <nav className={styles.sidebar}>
        <Sidebar />
      </nav>
      <main className={styles.content}>
        <Outlet />
      </main>
    </div>
  );
}
