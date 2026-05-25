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

import styles from "./IndicatorDot.module.css";

export type IndicatorStatus = "idle" | "active" | "streaming" | "error";

interface IndicatorDotProps {
  status: IndicatorStatus;
  /** Accessible label — screen readers announce this instead of the visual dot. */
  label?: string;
}

const STATUS_COLOR: Record<IndicatorStatus, string> = {
  idle: "var(--on-surface-retreat)",
  active: "var(--success)",
  streaming: "var(--primary)",
  error: "var(--error)",
};

export function IndicatorDot({ status, label }: IndicatorDotProps) {
  return (
    <span
      className={styles.dot}
      data-status={status}
      style={{ "--dot-color": STATUS_COLOR[status] } as React.CSSProperties}
      role="img"
      aria-label={label ?? status}
    />
  );
}
