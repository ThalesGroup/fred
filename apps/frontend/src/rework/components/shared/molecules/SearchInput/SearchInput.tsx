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
import { useRef } from "react";
import styles from "./SearchInput.module.scss";

export interface SearchInputProps {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  ariaLabel?: string;
  clearAriaLabel?: string;
  autoFocus?: boolean;
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
  size,
}: SearchInputProps) {
  const inputRef = useRef<HTMLInputElement>(null);

  return (
    <div className={styles.wrapper}>
      <TextInput
        ref={inputRef}
        compact
        size={size}
        autoFocus={autoFocus}
        icon={{ category: "outlined", type: "search" }}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        aria-label={ariaLabel}
        style={value ? { paddingRight: "calc(var(--spacing-2xs) + 2rem + var(--spacing-xs))" } : undefined}
      />
      {value && (
        <span className={styles.clear}>
          <IconButton
            type="button"
            size="small"
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
