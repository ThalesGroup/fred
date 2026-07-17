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

import Icon from "@shared/atoms/Icon/Icon.tsx";
import IconButton from "@shared/atoms/IconButton/IconButton.tsx";
import { useRef } from "react";
import styles from "./SearchField.module.scss";

export interface SearchFieldProps {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  clearAriaLabel?: string;
  autoFocus?: boolean;
}

export default function SearchField({
  value,
  onChange,
  placeholder,
  clearAriaLabel = "Clear",
  autoFocus = false,
}: SearchFieldProps) {
  const inputRef = useRef<HTMLInputElement>(null);

  return (
    <div className={styles.wrapper} onClick={() => inputRef.current?.focus()}>
      <span className={styles.searchIcon} aria-hidden="true">
        <Icon category="outlined" type="search" />
      </span>
      <input
        ref={inputRef}
        className={styles.input}
        type="text"
        autoComplete="off"
        autoFocus={autoFocus}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
      />
      {value && (
        <IconButton
          size="small"
          color="on-surface"
          variant="icon"
          icon={{ category: "outlined", type: "close" }}
          onClick={(e) => {
            e.stopPropagation();
            onChange("");
            inputRef.current?.focus();
          }}
          type="button"
          aria-label={clearAriaLabel}
        />
      )}
    </div>
  );
}
