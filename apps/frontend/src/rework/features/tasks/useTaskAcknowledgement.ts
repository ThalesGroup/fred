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

import { useState } from "react";
import { useDispatch } from "react-redux";
import { useAcknowledgeTaskMutation } from "../../../slices/controlPlane/controlPlaneApiEnhancements";
import { taskAcknowledged } from "./taskSlice";

/**
 * Shared per-task acknowledgement — `POST /tasks/{id}/ack`
 * (TASK-EVENT-STREAM-RFC.md §2.10), a server-persisted record visible to
 * every other admin of that scope, replacing the old per-browser
 * `failuresAcknowledged` bulk flag. Used by every place a `TaskCard`/
 * `TaskDetailPopover` renders a dismiss affordance (`TaskTray`,
 * `MigrationPage`), so the call + local-store update happens exactly once.
 */
export function useTaskAcknowledgement() {
  const dispatch = useDispatch();
  const [ackTask] = useAcknowledgeTaskMutation();
  const [pendingTaskId, setPendingTaskId] = useState<string | null>(null);

  const acknowledge = async (taskId: string) => {
    setPendingTaskId(taskId);
    try {
      const result = await ackTask({ taskId }).unwrap();
      dispatch(taskAcknowledged({ taskId, acknowledgedAt: result.acknowledged_at }));
    } catch {
      // 409 (already acknowledged, e.g. by another admin) or a transient
      // network error — nothing actionable beyond letting the user retry;
      // the button simply stays visible.
    } finally {
      setPendingTaskId(null);
    }
  };

  const isAcknowledging = (taskId: string) => pendingTaskId === taskId;

  return { acknowledge, isAcknowledging };
}
