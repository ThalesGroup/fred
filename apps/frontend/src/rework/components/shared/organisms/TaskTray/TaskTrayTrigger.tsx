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

import { useSelector } from "react-redux";
import { useTranslation } from "react-i18next";
import { selectActiveCount, selectUnacknowledgedFailures } from "../../../../features/tasks/taskSlice";
import styles from "./TaskTray.module.css";

interface TaskTrayTriggerProps {
  isOpen: boolean;
  onClick: () => void;
}

export function TaskTrayTrigger({ isOpen, onClick }: TaskTrayTriggerProps) {
  const { t } = useTranslation();
  const activeCount = useSelector(selectActiveCount);
  const unacknowledgedFailures = useSelector(selectUnacknowledgedFailures);

  const hasActivity = activeCount > 0 || unacknowledgedFailures > 0;
  const badgeCount = activeCount > 0 ? activeCount : unacknowledgedFailures;

  return (
    <button
      type="button"
      className={styles.trigger}
      data-open={isOpen}
      data-active={hasActivity}
      onClick={onClick}
      aria-label={t("rework.tasks.tray.progress")}
      aria-expanded={isOpen}
    >
      <span className={styles.triggerIcon}>
        {/* SVG ring showing aggregate progress or neutral icon */}
        <svg width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden="true">
          <circle cx="9" cy="9" r="7" stroke="var(--on-surface-retreat)" strokeWidth="1.5" />
          {activeCount > 0 && (
            <circle
              cx="9"
              cy="9"
              r="7"
              stroke="var(--info)"
              strokeWidth="1.5"
              strokeDasharray="43.98"
              strokeDashoffset="43.98"
              className={styles.ringProgress}
            />
          )}
        </svg>
        {hasActivity && (
          <span className={styles.badge} data-error={unacknowledgedFailures > 0 && activeCount === 0}>
            {badgeCount}
          </span>
        )}
      </span>
      <span className={styles.triggerLabel}>{t("rework.tasks.tray.trigger")}</span>
    </button>
  );
}
