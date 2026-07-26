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

import styles from "./Autocomplete.module.scss";
import TextInput, { TextInputProps } from "@shared/atoms/TextInput/TextInput.tsx";
import Menu from "@shared/molecules/Menu/Menu.tsx";
import { useEffect, useId, useState } from "react";
import { OptionModel } from "@models/Option.model.ts";

interface AutocompleteProps<T> {
  textInput: TextInputProps;
  options: OptionModel<T>[];
  onSelect: (value: T) => void;
  onFieldValueChange?: (value: string) => void;
  /** Characters (after trim) needed before the menu opens. Default 0 opens
   *  on focus, showing whatever `options` already holds — for fields meant
   *  to browse a full list. Set higher (e.g. 2) for fields backed by a
   *  server search that itself only queries past a minimum length, so the
   *  menu doesn't flash an empty "no options" state below that. */
  minQueryLength?: number;
}

export default function Autocomplete<T>({
  textInput,
  options,
  onSelect,
  onFieldValueChange,
  minQueryLength = 0,
}: AutocompleteProps<T>) {
  const [isFocused, setIsFocused] = useState(false);
  // True right after Escape or a selection — suppresses the menu until the
  // next focus or keystroke, even though the field stays focused (the
  // listbox's onMouseDown deliberately keeps focus on select, so "isFocused"
  // alone can't tell a fresh open from one that was just dismissed).
  const [dismissed, setDismissed] = useState(false);
  const [queryValue, setQueryValue] = useState("");
  const baseId = useId();

  const isOpen = isFocused && !dismissed && queryValue.trim().length >= minQueryLength;

  // Close on Escape.
  useEffect(() => {
    if (!isOpen) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") setDismissed(true);
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [isOpen]);

  useEffect(() => {
    onFieldValueChange?.(queryValue);
  }, [queryValue]);

  return (
    <div className={styles["autocomplete-container"]} data-open={isOpen}>
      <TextInput
        compact={true}
        {...textInput}
        onFocus={() => {
          setIsFocused(true);
          setDismissed(false);
        }}
        onBlur={() => setIsFocused(false)}
        onChange={(e) => {
          setQueryValue(e.target.value);
          setDismissed(false);
        }}
        value={queryValue}
      />
      <div id={`${baseId}-menu`} className={styles["menu-popover"]} role="presentation">
        <Menu
          options={options}
          baseId={baseId}
          onChange={(v) => {
            setDismissed(true);
            onSelect(v);
            setQueryValue("");
          }}
        />
      </div>
    </div>
  );
}
