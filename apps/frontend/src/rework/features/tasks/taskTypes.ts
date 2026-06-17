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
export type { TaskState, TaskTarget };

export const TERMINAL_STATES: ReadonlySet<TaskState> = new Set(["succeeded", "failed", "cancelled"]);

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
  } | null;
}

export type AnyTaskEvent = IngestionTaskEvent | MigrationTaskEvent;

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
