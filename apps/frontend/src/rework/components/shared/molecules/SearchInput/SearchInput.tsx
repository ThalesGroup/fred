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

import TextInput from "@shared/atoms/TextInput/TextInput.tsx";
import IconButton from "@shared/atoms/IconButton/IconButton.tsx";
import type { ComponentSize } from "@shared/utils/Type.ts";
import { useRef, type FocusEventHandler } from "react";
import styles from "./SearchInput.module.scss";

export interface SearchInputProps {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  ariaLabel?: string;
  clearAriaLabel?: string;
  autoFocus?: boolean;
  /** Forwarded to the underlying input — e.g. for an auto-collapsing search
   * field that closes when it loses focus. */
  onBlur?: FocusEventHandler<HTMLInputElement>;
  size?: ComponentSize;
}

/** Compact `TextInput`-based search field (search icon + inline clear button),
 * originally inlined in TeamSettingsMembers — extracted so team prompts (and
 * any future list search) reuse the same component instead of duplicating it. */
export default function SearchInput({
  value,
  onChange,
  placeholder,
  ariaLabel,
  clearAriaLabel,
  autoFocus = false,
  onBlur,
  size,
}: SearchInputProps) {
  const inputRef = useRef<HTMLInputElement>(null);

  // On the compact field tiers (`xs` = 32px, `2xs` = 24px) a 32px clear button
  // would overflow the field, so it shrinks to the 24px `2xs` icon button and
  // the reserved right padding shrinks to match. Every other size keeps the
  // original 32px clear + 2rem reserve — existing call sites are unchanged.
  const compact = size === "xs" || size === "2xs";
  const clearSize: ComponentSize = compact ? "2xs" : "small";
  const clearReserve = compact ? "1.5rem" : "2rem";

  return (
    <div className={styles.wrapper}>
      <TextInput
        ref={inputRef}
        compact
        size={size}
        autoFocus={autoFocus}
        onBlur={onBlur}
        icon={{ category: "outlined", type: "search" }}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        aria-label={ariaLabel}
        style={value ? { paddingRight: `calc(var(--spacing-2xs) + ${clearReserve} + var(--spacing-xs))` } : undefined}
      />
      {value && (
        <span className={styles.clear}>
          <IconButton
            type="button"
            size={clearSize}
            color="on-surface-retreat"
            variant="icon"
            icon={{ category: "outlined", type: "close" }}
            aria-label={clearAriaLabel}
            onClick={() => {
              onChange("");
              inputRef.current?.focus();
            }}
          />
        </span>
      )}
    </div>
  );
}
