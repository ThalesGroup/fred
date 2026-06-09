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
  label: string;
  icon: string; // Tabler icon name
  ramp: string;
  pillBg: string;
  pillFg: string;
}

export const TASK_KINDS: Record<string, TaskKindMeta> = {
  ingestion: {
    label: "Traitement",
    icon: "file-stack",
    ramp: "info",
    pillBg: "color-mix(in srgb, var(--info) 12%, transparent)",
    pillFg: "var(--info)",
  },
  deletion: {
    label: "Suppression",
    icon: "trash",
    ramp: "error",
    pillBg: "color-mix(in srgb, var(--error) 12%, transparent)",
    pillFg: "var(--error)",
  },
  migration: {
    label: "Migration",
    icon: "arrows-exchange",
    ramp: "warning",
    pillBg: "color-mix(in srgb, var(--warning) 12%, transparent)",
    pillFg: "var(--warning)",
  },
  reindex: {
    label: "Réindexation",
    icon: "database",
    ramp: "primary",
    pillBg: "color-mix(in srgb, var(--primary) 12%, transparent)",
    pillFg: "var(--primary)",
  },
};

export const DEFAULT_KIND_META: TaskKindMeta = {
  label: "Tâche",
  icon: "loader",
  ramp: "on-surface-retreat",
  pillBg: "color-mix(in srgb, var(--on-surface-retreat) 12%, transparent)",
  pillFg: "var(--on-surface-retreat)",
};

export function getKindMeta(kind: string | null): TaskKindMeta {
  return (kind && TASK_KINDS[kind]) || DEFAULT_KIND_META;
}
