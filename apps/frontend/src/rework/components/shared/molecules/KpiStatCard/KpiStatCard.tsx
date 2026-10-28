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

import type { ReactNode } from "react";
import type { StatusBadgeTone } from "../../atoms/StatusBadge/StatusBadge.tsx";
import { MaterialIcon } from "../../atoms/Icon/Icon.tsx";
import IconButton from "../../atoms/IconButton/IconButton.tsx";
import { Tooltip } from "../../atoms/Tooltip/Tooltip.tsx";
import styles from "./KpiStatCard.module.scss";

export interface KpiStatCardProps {
  label: string;
  /** Definition shown in an info bubble beside the label: a string wraps as prose, a node brings
   *  its own layout (the bubble is then named after the label). */
  hint?: ReactNode;
  /** A "show trend" button beside the hint; its label is the tooltip, and with the card's label its name. */
  trendAction?: { label: string; onClick: () => void };
  /** Fixed number of decimals, e.g. 4 for a cost; locale default when unset. */
  fractionDigits?: number;
  tone?: StatusBadgeTone;
  loadingLabel?: string;
  errorLabel?: string;
  noDataLabel?: string;
  value?: number | null;
  /** Secondary line under the value, shown only when the value is. */
  caption?: string;
  /** Preformatted value (unit, percent, currency); replaces the locale number. */
  displayValue?: string;
  delta?: number | null;
  /** Preformatted change, e.g. "+12 % vs previous period"; `deltaTone` colors it. */
  deltaLabel?: string;
  deltaTone?: "positive" | "negative" | "neutral";
  /** Direction of a preformatted change, shown as ▲/▼ so it reads without colour. */
  deltaDirection?: "up" | "down";
  /** Value type: medium (headline-small) by default, large (headline-medium) for headline figures. */
  size?: "medium" | "large";
  unavailable?: boolean;
  /** Inside a card of its own (a dashboard section): second surface, smaller radius. */
  nested?: boolean;
  isLoading: boolean;
  isError: boolean;
}

export default function KpiStatCard({
  label,
  hint,
  trendAction,
  fractionDigits,
  tone = "neutral",
  value,
  caption,
  displayValue,
  delta,
  deltaLabel: deltaText,
  deltaTone,
  deltaDirection,
  size = "medium",
  unavailable,
  nested,
  isLoading,
  isError,
  loadingLabel = "Loading",
  errorLabel = "Loading error",
  noDataLabel = "No data",
}: KpiStatCardProps) {
  const changeTone =
    deltaText !== undefined
      ? (deltaTone ?? "neutral")
      : delta == null || delta === 0
        ? "neutral"
        : delta > 0
          ? "positive"
          : "negative";
  const deltaClass =
    changeTone === "positive"
      ? styles.deltaPositive
      : changeTone === "negative"
        ? styles.deltaNegative
        : styles.deltaNeutral;

  const deltaLabel =
    deltaText ?? (delta == null ? undefined : delta > 0 ? `+${delta.toLocaleString()}` : delta.toLocaleString());
  const direction =
    deltaText !== undefined ? deltaDirection : delta == null || delta === 0 ? undefined : delta > 0 ? "up" : "down";

  const isUnavailable = !isLoading && !isError && !!unavailable;
  const hasValue = !isLoading && !isError && !unavailable && value != null;

  return (
    <section
      className={styles.card}
      data-tone={tone}
      data-nested={nested || undefined}
      data-size={size}
      data-hint={hint ? true : undefined}
      data-action={trendAction ? true : undefined}
    >
      <span className={styles.label}>{label}</span>
      {(hint || trendAction) && (
        <span className={styles.hintCorner}>
          {trendAction && (
            <Tooltip text={trendAction.label}>
              <IconButton
                className={styles.action}
                variant="icon"
                size="medium"
                color="on-surface-retreat"
                iconSize="2xs"
                icon={{ category: "outlined", type: "show_chart" }}
                aria-label={`${trendAction.label} - ${label}`}
                onClick={trendAction.onClick}
              />
            </Tooltip>
          )}
          {hint && (
            <Tooltip content={hint}>
              <span className={styles.hint} tabIndex={0} aria-label={typeof hint === "string" ? hint : label}>
                <MaterialIcon type="info" />
              </span>
            </Tooltip>
          )}
        </span>
      )}
      {isLoading && <span className={styles.state}>{loadingLabel}</span>}
      {isError && <span className={styles.stateError}>{errorLabel}</span>}
      {isUnavailable && <span className={styles.state}>{noDataLabel}</span>}
      {hasValue && (
        <span className={styles.value}>
          {displayValue ??
            value!.toLocaleString(undefined, {
              minimumFractionDigits: fractionDigits,
              maximumFractionDigits: fractionDigits,
            })}
        </span>
      )}
      {hasValue && deltaLabel !== undefined && (
        <span className={deltaClass}>
          {direction && <span aria-hidden>{direction === "up" ? "▲ " : "▼ "}</span>}
          {deltaLabel}
        </span>
      )}
      {hasValue && caption && <span className={styles.caption}>{caption}</span>}
    </section>
  );
}
