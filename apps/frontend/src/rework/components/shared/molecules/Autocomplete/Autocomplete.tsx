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
}

export default function Autocomplete<T>({ textInput, options, onSelect, onFieldValueChange }: AutocompleteProps<T>) {
  const [isOpen, setIsOpen] = useState(false);
  const [queryValue, setQueryValue] = useState("");
  const baseId = useId();

  // Close on Escape.
  useEffect(() => {
    if (!isOpen) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") setIsOpen(false);
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
        onFocus={() => setIsOpen(true)}
        onBlur={() => setIsOpen(false)}
        onChange={(e) => setQueryValue(e.target.value)}
        value={queryValue}
      />
      <div id={`${baseId}-menu`} className={styles["menu-popover"]} role="presentation">
        <Menu
          options={options}
          baseId={baseId}
          onChange={(v) => {
            setIsOpen(false);
            onSelect(v);
            setQueryValue("");
          }}
        />
      </div>
    </div>
  );
}
