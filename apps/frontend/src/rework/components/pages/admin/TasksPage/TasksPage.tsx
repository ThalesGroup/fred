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

// Platform and team admins share `TaskActivity` with different scopes.
// Personal document imports are shown in the resources import panel.

import TaskActivity from "@shared/organisms/TaskActivity/TaskActivity.tsx";
import styles from "./TasksPage.module.css";

export default function TasksPage() {
  return (
    <div className={styles.page}>
      <TaskActivity scope="platform" />
    </div>
  );
}
