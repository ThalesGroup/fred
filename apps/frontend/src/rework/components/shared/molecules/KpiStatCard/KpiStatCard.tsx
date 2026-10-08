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

import type { StatusBadgeTone } from "../../atoms/StatusBadge/StatusBadge.tsx";
import styles from "./KpiStatCard.module.scss";

export interface KpiStatCardProps {
  label: string;
  tone?: StatusBadgeTone;
  loadingLabel?: string;
  errorLabel?: string;
  noDataLabel?: string;
  value?: number | null;
  /** Secondary line under the value, shown only when the value is. */
  caption?: string;
  delta?: number | null;
  unavailable?: boolean;
  isLoading: boolean;
  isError: boolean;
}

export default function KpiStatCard({
  label,
  tone = "neutral",
  value,
  caption,
  delta,
  unavailable,
  isLoading,
  isError,
  loadingLabel = "Loading",
  errorLabel = "Loading error",
  noDataLabel = "No data",
}: KpiStatCardProps) {
  const deltaClass =
    delta == null
      ? undefined
      : delta > 0
        ? styles.deltaPositive
        : delta < 0
          ? styles.deltaNegative
          : styles.deltaNeutral;

  const deltaLabel = delta == null ? undefined : delta > 0 ? `+${delta.toLocaleString()}` : delta.toLocaleString();

  const isUnavailable = !isLoading && !isError && !!unavailable;
  const hasValue = !isLoading && !isError && !unavailable && value != null;

  return (
    <section className={styles.card} data-tone={tone}>
      <span className={styles.label}>{label}</span>
      {isLoading && <span className={styles.state}>{loadingLabel}</span>}
      {isError && <span className={styles.stateError}>{errorLabel}</span>}
      {isUnavailable && <span className={styles.state}>{noDataLabel}</span>}
      {hasValue && (
        <div className={styles.valueRow}>
          <span className={styles.value}>{value!.toLocaleString()}</span>
          {deltaLabel !== undefined && <span className={deltaClass}>{deltaLabel}</span>}
        </div>
      )}
      {hasValue && caption && <span className={styles.caption}>{caption}</span>}
    </section>
  );
}
