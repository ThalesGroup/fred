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

import type { TFunction } from "i18next";
import type { TaskState } from "./taskTypes";

/**
 * Single source of truth for the task feature's presentation strings.
 * Every label goes through i18n — nothing here is hardcoded in a human
 * language. Shared by TaskStateBadge, TaskIndicator, TaskCard, the popover
 * and the tray so the same task never renders two different wordings.
 */

/** task-state → CSS color token. */
export const STATE_COLOR: Record<TaskState, string> = {
  pending: "var(--on-surface-retreat)",
  running: "var(--info)",
  cancelling: "var(--warning)",
  succeeded: "var(--success)",
  failed: "var(--error)",
  cancelled: "var(--on-surface-retreat)",
};

/** Localized task-state label (e.g. "Pending" / "En attente"). */
export const stateLabel = (state: TaskState, t: TFunction): string => t(`rework.tasks.state.${state}`);

/** Localized "time ago" string shared by the card, popover and tray. */
export function relativeTime(ms: number, t: TFunction, now = Date.now()): string {
  const diffS = Math.floor((now - ms) / 1000);
  if (diffS < 60) return t("rework.tasks.time.justNow");
  const diffM = Math.floor(diffS / 60);
  if (diffM < 60) return t("rework.tasks.time.minAgo", { count: diffM });
  const diffH = Math.floor(diffM / 60);
  return t("rework.tasks.time.hoursAgo", { count: diffH });
}

/** Localized "due in …" hint for a future timestamp (erasure schedule view).
 *  A non-positive delta reads as imminent — the window has effectively elapsed
 *  and the next worker tick will erase. */
export function dueRelative(ms: number, t: TFunction, now = Date.now()): string {
  const diffS = Math.floor((ms - now) / 1000);
  if (diffS <= 0) return t("rework.tasks.due.imminent");
  const diffD = Math.floor(diffS / 86400);
  if (diffD >= 1) return t("rework.tasks.due.inDays", { count: diffD });
  const diffH = Math.floor(diffS / 3600);
  if (diffH >= 1) return t("rework.tasks.due.inHours", { count: diffH });
  const diffM = Math.max(1, Math.floor(diffS / 60));
  return t("rework.tasks.due.inMinutes", { count: diffM });
}
