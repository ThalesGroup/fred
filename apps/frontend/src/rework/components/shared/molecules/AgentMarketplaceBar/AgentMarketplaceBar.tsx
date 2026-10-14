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

// Bottom bar of an agent card for its marketplace side: the team card shows its
// publication state here, the marketplace card its Like and Import actions.
// Full rationale: COMPONENT-UX.md, "AgentMarketplaceBar".

import Icon from "@shared/atoms/Icon/Icon.tsx";
import type { MaterialIconType } from "@shared/utils/Type.ts";
import type { ReactNode } from "react";
import styles from "./AgentMarketplaceBar.module.scss";

export type AgentMarketplaceBarTone = "neutral" | "warning";

interface AgentMarketplaceBarProps {
  /** Leading content (a state label), then counters and trailing text. */
  children: ReactNode;
  tone?: AgentMarketplaceBarTone;
  "aria-label"?: string;
  /** Per-card layout tweaks (the marketplace card's tighter bar). */
  className?: string;
}

export default function AgentMarketplaceBar({
  children,
  tone = "neutral",
  "aria-label": ariaLabel,
  className,
}: AgentMarketplaceBarProps) {
  return (
    <div
      className={className ? `${styles.bar} ${className}` : styles.bar}
      data-tone={tone}
      role="group"
      aria-label={ariaLabel}
    >
      {children}
    </div>
  );
}

interface MarketplaceCounterProps {
  icon: MaterialIconType;
  count: number;
  /** Full sentence for assistive tech, e.g. "12 likes". */
  label: string;
  /** Turns the counter into a toggle button (marketplace card's Like). */
  onClick?: () => void;
  pressed?: boolean;
  disabled?: boolean;
}

export function MarketplaceCounter({ icon, count, label, onClick, pressed, disabled }: MarketplaceCounterProps) {
  const content = (
    <>
      <Icon category="outlined" type={icon} filled={pressed} />
      <span aria-hidden="true">{count}</span>
    </>
  );
  if (!onClick) {
    return (
      <span className={styles.counter} aria-label={label} role="img">
        {content}
      </span>
    );
  }
  return (
    <button
      type="button"
      className={`${styles.counter} ${styles.counterButton}`}
      aria-label={label}
      aria-pressed={pressed}
      // aria-disabled, not disabled: a disabled button drops keyboard focus.
      aria-disabled={disabled || undefined}
      onClick={disabled ? undefined : onClick}
    >
      {content}
    </button>
  );
}

/** Long locale date ("12 October 2026" / "12 octobre 2026"). */
export function formatMarketplaceDate(iso: string | null | undefined, language: string): string {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat(language, { dateStyle: "long" }).format(date);
}
