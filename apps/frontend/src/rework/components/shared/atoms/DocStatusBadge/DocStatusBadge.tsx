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

import { useTranslation } from "react-i18next";
import Icon from "@shared/atoms/Icon/Icon.tsx";
import styles from "./DocStatusBadge.module.css";

/**
 * The four synthetic states a document can be in, from the user's point of view.
 * This deliberately collapses the internal pipeline sub-steps (raw / vectorized /
 * sql / metadata) into a single answer to "is this document usable?".
 * `raw` is a legitimate choice (stored, not processed), NOT an error.
 */
export type DocStatus = "ready" | "processing" | "failed" | "raw";

/** status → CSS color token. Same family as the task system (taskLabels.STATE_COLOR). */
const STATUS_COLOR: Record<DocStatus, string> = {
  ready: "var(--success)",
  processing: "var(--info)",
  failed: "var(--error)",
  raw: "var(--on-surface-retreat)",
};

const RING_RADIUS = 6;
const RING_CIRCUMFERENCE = 2 * Math.PI * RING_RADIUS;

interface DocStatusBadgeProps {
  status: DocStatus;
  /** 0.0–1.0 when status === "processing"; drives the ring offset. null => indeterminate. */
  progress?: number | null;
}

export function DocStatusBadge({ status, progress = null }: DocStatusBadgeProps) {
  const { t } = useTranslation();
  const label = t(`rework.resources.status.${status}`);
  const color = STATUS_COLOR[status];

  return (
    <span className={styles.badge}>
      <Indicator status={status} progress={progress} label={label} />
      <span className={styles.label} style={{ color }}>
        {label}
      </span>
    </span>
  );
}

function Indicator({ status, progress, label }: { status: DocStatus; progress: number | null; label: string }) {
  if (status === "processing") {
    const indeterminate = progress === null;
    const offset = indeterminate ? RING_CIRCUMFERENCE * 0.7 : RING_CIRCUMFERENCE * (1 - clamp01(progress));
    return (
      <svg className={styles.ring} data-indeterminate={indeterminate} viewBox="0 0 16 16" role="img" aria-label={label}>
        <circle className={styles.ringTrack} cx="8" cy="8" r={RING_RADIUS} />
        <circle
          className={styles.ringFill}
          cx="8"
          cy="8"
          r={RING_RADIUS}
          style={{ strokeDasharray: RING_CIRCUMFERENCE, strokeDashoffset: offset }}
        />
      </svg>
    );
  }

  if (status === "failed") {
    return (
      <span className={styles.failedIcon} role="img" aria-label={label}>
        <Icon category="outlined" type="warning" />
      </span>
    );
  }

  // ready / raw — a plain coloured dot.
  return (
    <span
      className={styles.dot}
      style={{ "--badge-color": STATUS_COLOR[status] } as React.CSSProperties}
      role="img"
      aria-label={label}
    />
  );
}

function clamp01(value: number): number {
  return Math.min(1, Math.max(0, value));
}
