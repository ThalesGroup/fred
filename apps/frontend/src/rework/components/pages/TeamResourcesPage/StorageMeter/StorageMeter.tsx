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
import { formatBytes } from "@shared/utils/formatBytes";
import styles from "./StorageMeter.module.css";

interface StorageMeterProps {
  /** Bytes currently consumed by the team's (or personal space's) resources. */
  used: number;
  /** Storage limit in bytes; `null`/`0`/undefined means unlimited (bar hidden). */
  max?: number | null;
}

// Storage consumption at a glance, sitting to the right of the "Files" title: a
// slim progress bar plus a "used / total" byte label. When the space is
// unlimited (no `max`), the bar is dropped and only the consumed amount shows.
const WARN_RATIO = 0.9;

export function StorageMeter({ used, max }: StorageMeterProps) {
  const { t, i18n } = useTranslation();
  const hasLimit = typeof max === "number" && max > 0;
  const ratio = hasLimit ? Math.min(1, Math.max(0, used / max)) : 0;
  const usedLabel = formatBytes(used, i18n.language);

  return (
    <div className={styles.meter}>
      {hasLimit && (
        <div
          className={styles.track}
          role="progressbar"
          aria-label={t("rework.resources.storage.aria")}
          aria-valuenow={Math.round(ratio * 100)}
          aria-valuemin={0}
          aria-valuemax={100}
        >
          <div
            className={styles.fill}
            data-warn={ratio >= WARN_RATIO || undefined}
            style={{ width: `${ratio * 100}%` }}
          />
        </div>
      )}
      <span className={styles.label}>
        {hasLimit
          ? t("rework.resources.storage.usedOfTotal", { used: usedLabel, total: formatBytes(max, i18n.language) })
          : t("rework.resources.storage.used", { used: usedLabel })}
      </span>
    </div>
  );
}
