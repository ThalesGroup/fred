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

import { useEffect } from "react";
import { useDispatch } from "react-redux";
import { KeyCloakService } from "../../../security/KeycloakService";
import { personalTeamId } from "@shared/utils/teamId";
import { taskRegistered } from "./taskSlice";
import type { TaskListResponse } from "../../../slices/knowledgeFlow/knowledgeFlowOpenApi";

// Task events are served by the backend that runs the task, so rehydration is
// multi-source: each producer exposes the same canonical `GET /tasks?scope=user`.
const TASK_SOURCES = ["/knowledge-flow/v1", "/evaluation/v1", "/control-plane/v1"];

/**
 * On mount, fetches the current user's non-terminal tasks from every task
 * producer and registers each one in Redux so useTaskSseManager opens SSE
 * connections. SSE replay from seq=0 restores full task state including target.
 * Called once from MainLayout — runs on every page reload. Each source is
 * best-effort: a producer being down or lacking the endpoint is not fatal.
 */
export function useTaskRehydration(): void {
  const dispatch = useDispatch();

  useEffect(() => {
    const token = KeyCloakService.GetToken();
    // This listing is scope=user, so every task in it is this user's own. A
    // personal-space tag resolves to a user, never a team, so the server
    // leaves team_id empty for it — which is the personal space, not "no
    // team". Saying so here is what lets the import panel find these again
    // after a reload.
    const uid = KeyCloakService.GetUserId();
    const personalScope = uid ? personalTeamId(uid) : null;
    if (!token) return;

    for (const base of TASK_SOURCES) {
      fetch(`${base}/tasks?scope=user`, {
        headers: { Authorization: `Bearer ${token}` },
      })
        .then((res) => {
          if (!res.ok) return null;
          return res.json() as Promise<TaskListResponse>;
        })
        .then((body) => {
          if (!body) return;
          for (const task of body.tasks) {
            dispatch(
              taskRegistered({
                taskId: task.task_id,
                kind: task.kind,
                target: task.target ?? null,
                // Carried so the import panel, which belongs to one team's
                // page, can tell its own imports from another team's.
                teamId: task.team_id ?? personalScope,
              }),
            );
          }
        })
        .catch(() => {
          // Rehydration is best-effort — a failure here is not fatal.
        });
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
}
