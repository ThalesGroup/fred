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
import { useAcknowledgeTaskKnowledgeFlowV1TasksTaskIdAckPostMutation } from "../../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { taskBackendFor } from "./taskKinds";
import { taskAcknowledged } from "./taskSlice";

/**
 * Shared per-task acknowledgement — `POST /tasks/{id}/ack`
 * (TASK-EVENT-STREAM-RFC.md §2.10), a server-persisted record visible to
 * every other admin of that scope, replacing the old per-browser
 * `failuresAcknowledged` bulk flag. Used by every place a `TaskCard`/
 * `TaskDetailPopover` renders a dismiss affordance (`TaskTray`,
 * `MigrationPage`), so the call + local-store update happens exactly once.
 *
 * Routed by `taskBackendFor` (same map `useTaskSseManager` uses for its SSE
 * stream) — this used to always call control-plane regardless of which
 * backend actually owns the task, so a failed ingestion task's ack 404'd
 * and silently left the button visible (#2123 review).
 *
 * `localOnly` tasks (e.g. a chat-attachment fast-ingest failure — see
 * `useChatAttachments.addFiles`) never had a server-side task record created
 * for them in the first place (the fast-ingest route is synchronous and
 * registers no task), so POSTing an ack for one always 404s. Acknowledging
 * one is a purely local Redux update instead of a network call — same as
 * `useTaskSseManager` already excludes `localOnly` tasks from its SSE
 * subscription for the same underlying reason.
 */
export function useTaskAcknowledgement() {
  const dispatch = useDispatch();
  const [ackControlPlane] = useAcknowledgeTaskMutation();
  const [ackKnowledgeFlow] = useAcknowledgeTaskKnowledgeFlowV1TasksTaskIdAckPostMutation();
  const [pendingTaskId, setPendingTaskId] = useState<string | null>(null);

  const acknowledge = async (taskId: string, kind: string | null, localOnly?: boolean) => {
    if (localOnly) {
      dispatch(taskAcknowledged({ taskId, acknowledgedAt: new Date().toISOString() }));
      return;
    }
    const backend = taskBackendFor(kind);
    if (backend === "evaluation") {
      // No acknowledgement endpoint exists on the evaluation backend yet
      // (tracked separately, not part of #2123) — nothing to call; the
      // button stays visible rather than silently pretending to succeed.
      return;
    }
    setPendingTaskId(taskId);
    try {
      const result = await (
        backend === "control-plane" ? ackControlPlane({ taskId }) : ackKnowledgeFlow({ taskId })
      ).unwrap();
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
