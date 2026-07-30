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

import styles from "./Spinner.module.css";

interface SpinnerProps {
  /** Diameter in px. */
  size?: number;
  /** Stroke color — defaults to the current text color so it drops into any
   *  colored context (e.g. a `--on-surface-retreat` loading label) unchanged. */
  color?: string;
  /** Set when a host already exposes its own accessible label/live region for
   *  this loading state (e.g. TaskIndicator's own aria-label'd trigger button) —
   *  drops this spinner's own `role="status"`/`aria-label` so screen readers
   *  don't announce "Loading" a second time per instance, which gets noisy
   *  fast with several concurrent spinners (e.g. an activity list). */
  decorative?: boolean;
}

/** Indeterminate circular progress ring — the M3 loading affordance for "work
 *  is happening, no known duration". Extracted from TaskIndicator's inline
 *  SpinningRing so page-level loading states can reuse the same visual. */
export function Spinner({ size = 20, color = "currentColor", decorative = false }: SpinnerProps) {
  const strokeWidth = 2;
  const r = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * r;
  const cx = size / 2;

  return (
    <svg
      width={size}
      height={size}
      viewBox={`0 0 ${size} ${size}`}
      className={styles.ring}
      style={{ flexShrink: 0 }}
      role={decorative ? undefined : "status"}
      aria-label={decorative ? undefined : "Loading"}
      aria-hidden={decorative ? "true" : undefined}
    >
      <circle cx={cx} cy={cx} r={r} fill="none" stroke={color} strokeWidth={strokeWidth} opacity={0.18} />
      <circle
        cx={cx}
        cy={cx}
        r={r}
        fill="none"
        stroke={color}
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        strokeDasharray={`${circumference * 0.75} ${circumference * 0.25}`}
      />
    </svg>
  );
}
