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
import type { DocStatus } from "@shared/atoms/DocStatusBadge/DocStatusBadge.tsx";
import Icon from "@shared/atoms/Icon/Icon.tsx";
import { Spinner } from "@shared/atoms/Spinner/Spinner.tsx";
import styles from "./StatusChip.module.css";

interface StatusChipProps {
  status: DocStatus;
}

const ICON_SIZE = 12;

/**
 * Resources dashboard v2's status cell (RFC §13.3): silence for the common
 * "ready" case (no chip, not a green checkmark) — a chip only appears for a
 * state that needs the user's attention. Deliberately a new piece rather than
 * a `DocStatusBadge` prop toggle, so the existing always-visible dot+label
 * rendering used elsewhere is untouched.
 */
export function StatusChip({ status }: StatusChipProps) {
  const { t } = useTranslation();
  if (status === "ready") return null;

  const variant = status === "raw" ? "pending" : status;
  return (
    <span className={styles.chip} data-variant={variant}>
      {variant === "processing" ? (
        <Spinner size={ICON_SIZE} />
      ) : variant === "pending" ? (
        <span className={styles.breathingIcon}>
          <Icon category="outlined" type="sync" />
        </span>
      ) : (
        <Icon category="outlined" type="error_outline" />
      )}
      {t(`rework.resources.status.${status}`)}
    </span>
  );
}
