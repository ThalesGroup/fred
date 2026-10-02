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

import styles from "./StatusBadge.module.css";

export type StatusBadgeTone = "success" | "error" | "warning" | "info" | "neutral";

export interface StatusBadgeProps {
  label: string;
  tone: StatusBadgeTone;
}

const toneClass: Record<StatusBadgeTone, string> = {
  success: styles.toneSuccess,
  error: styles.toneError,
  warning: styles.toneWarning,
  info: styles.toneInfo,
  neutral: styles.toneNeutral,
};

export default function StatusBadge({ label, tone }: StatusBadgeProps) {
  return <span className={`${styles.badge} ${toneClass[tone]}`}>{label}</span>;
}
