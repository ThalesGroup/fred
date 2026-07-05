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

export interface TaskKindMeta {
  /** i18n key for the kind label (resolve with t(meta.labelKey)) — never a literal. */
  labelKey: string;
}

// Only the label is consumed today (TaskIndicator renders `t(meta.labelKey)`).
// Earlier icon/ramp/pill fields were never rendered and were removed to avoid
// dead, drifting metadata; add a field back here only when something reads it.
export const TASK_KINDS: Record<string, TaskKindMeta> = {
  ingestion: { labelKey: "rework.tasks.kind.ingestion" },
  erasure: { labelKey: "rework.tasks.kind.erasure" },
  migration: { labelKey: "rework.tasks.kind.migration" },
  evaluation: { labelKey: "rework.tasks.kind.evaluation" },
  reindex: { labelKey: "rework.tasks.kind.reindex" },
};

export const DEFAULT_KIND_META: TaskKindMeta = {
  labelKey: "rework.tasks.kind.default",
};

export function getKindMeta(kind: string | null): TaskKindMeta {
  return (kind && TASK_KINDS[kind]) || DEFAULT_KIND_META;
}
