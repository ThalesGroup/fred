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

import type { TaskState, TaskTarget } from "../../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import type { MigrationResult } from "../../../slices/controlPlane/controlPlaneOpenApi";
export type { TaskState, TaskTarget };

export const TERMINAL_STATES: ReadonlySet<TaskState> = new Set(["succeeded", "failed", "cancelled"]);

// ─────────────────────────────────────────────────────────────────────────────
// HAND-MAINTAINED ADAPTER — keep in sync with the backend by hand.
//
// The RFC (docs/swift/rfc/TASK-EVENT-STREAM-RFC.md §"generated union") wants this
// task-event union generated from OpenAPI. It is not, yet: the events are SSE
// payloads typed `any` in the generated clients, so there is no schema to generate
// from. Until TaskEvent is exposed as an OpenAPI component (tracked in
// FRONTEND-BACKLOG — "generate TaskEvent union"), these interfaces MIRROR the
// canonical Pydantic models in libs/fred-core/fred_core/tasks/models.py and must be
// updated together with them. Adding a backend kind means adding it here too (and
// to taskEventsBasePath + taskKinds).
//
// `TaskLogEvent` (kind "log") is intentionally omitted: log tasks are an internal
// diagnostic kind and are never surfaced in this UI, so the union covers only the
// user-facing progress kinds.
// ─────────────────────────────────────────────────────────────────────────────

export interface IngestionTaskEvent {
  kind: "ingestion";
  task_id: string;
  state: TaskState;
  seq: number;
  timestamp: string;
  progress: number | null;
  step: string | null;
  error: string | null;
  target?: TaskTarget | null;
  owner?: string | null;
  detail: {
    processed: number;
    total: number;
    failed: number;
    preview: number;
    vectorized: number;
    sql_indexed: number;
  } | null;
}

export interface MigrationTaskEvent {
  kind: "migration";
  task_id: string;
  state: TaskState;
  seq: number;
  timestamp: string;
  progress: number | null;
  step: string | null;
  error: string | null;
  target?: TaskTarget | null;
  owner?: string | null;
  detail: {
    step_id: string;
    processed: number;
    total: number;
    failed: number;
    // Reuses the generated `MigrationResult` (controlPlaneOpenApi.ts) — this one
    // field IS on the OpenAPI schema (`MigrationDetail.result`), so it is imported,
    // never hand-mirrored like the rest of this file's SSE-only detail shapes.
    result?: MigrationResult | null;
  } | null;
}

export interface EvaluationTaskEvent {
  kind: "evaluation";
  task_id: string;
  state: TaskState;
  seq: number;
  timestamp: string;
  progress: number | null;
  step: string | null;
  error: string | null;
  target?: TaskTarget | null;
  owner?: string | null;
  detail: {
    campaign_id: string;
    completed: number;
    total: number;
    passed: number;
    failed: number;
    execution_errors: number;
    scoring_errors: number;
  } | null;
}

export interface ErasureTaskEvent {
  kind: "erasure";
  task_id: string;
  state: TaskState;
  seq: number;
  timestamp: string;
  progress: number | null;
  step: string | null;
  error: string | null;
  target?: TaskTarget | null;
  owner?: string | null;
  // Governance view (never conversation content): why it is being erased and how
  // far the store fan-out has got. `reason` is set on the scheduling event only.
  // `attempts` counts erase retries — past the backend stall threshold the task's
  // `step` becomes "stalled" while still running (RGPD: erasure never auto-fails).
  detail: {
    reason: "user_deleted" | "member_removed" | "idle_expired" | null;
    stores_ok: number;
    stores_total: number;
    attempts: number;
  } | null;
}

export type AnyTaskEvent = IngestionTaskEvent | MigrationTaskEvent | EvaluationTaskEvent | ErasureTaskEvent;

export interface TaskViewModel {
  taskId: string;
  kind: string | null;
  target: TaskTarget | null;
  owner: string | null;
  localOnly: boolean;
  state: TaskState;
  progress: number | null;
  step: string | null;
  error: string | null;
  lastSeq: number;
  registeredAt: number;
  terminalAt: number | null;
  acknowledgedAt: number | null;
}
