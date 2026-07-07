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

// Platform admin activity view. It renders the one shared `TaskActivity` surface
// at platform scope — the exact same component a team admin sees at team scope
// (OPS-04 §3.4). The client's own in-flight tasks live in the floating task tray,
// not here, so both admin levels get an identical, scope-only-different view.

import TaskActivity from "@shared/organisms/TaskActivity/TaskActivity.tsx";
import styles from "./TasksPage.module.css";

export default function TasksPage() {
  return (
    <div className={styles.page}>
      <TaskActivity scope="platform" />
    </div>
  );
}
