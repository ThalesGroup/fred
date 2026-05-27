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

import styles from "./Select.module.scss";
import { useEffect, useId, useRef, useState } from "react";
import { OptionModel } from "@models/Option.model.ts";
import Menu from "@shared/molecules/Menu/Menu.tsx";
import Icon from "@shared/atoms/Icon/Icon.tsx";
import { ComponentSize } from "@shared/utils/Type.ts";

interface SelectProps<T> {
  options: OptionModel<T>[];
  value?: T;
  onChange: (value: T) => void;
  size: ComponentSize;
  placeholder?: string;
  label?: string;
  disabled?: boolean;
  error?: string;
  compact?: boolean;
}

export default function Select<T>({
  options = [],
  value,
  placeholder,
  label,
  disabled = false,
  error,
  onChange,
  compact = false,
  size,
}: SelectProps<T>) {
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const baseId = useId();

  // Close on outside click.
  useEffect(() => {
    if (!isOpen) return;
    const handler = (e: MouseEvent) => {
      if (!containerRef.current?.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [isOpen]);

  // Close on Escape.
  useEffect(() => {
    if (!isOpen) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") setIsOpen(false);
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [isOpen]);

  const toggleMenu = () => {
    if (disabled) return;
    setIsOpen((prev) => !prev);
  };

  const selectedOption = options.find((opt) => opt.value === value);

  return (
    <div
      className={styles["select-container"]}
      ref={containerRef}
      data-disabled={disabled}
      data-error={error != undefined}
      data-state={isOpen ? "open" : "closed"}
      data-compact={compact}
      data-size={size}
    >
      {label && (
        <label className={styles["label"]} id={`${baseId}-label`} htmlFor={`${baseId}-trigger`}>
          {label}
        </label>
      )}

      <button
        id={`${baseId}-trigger`}
        type="button"
        className={styles["trigger"]}
        onClick={toggleMenu}
        aria-haspopup="listbox"
        aria-expanded={isOpen}
        aria-controls={`${baseId}-menu`}
        disabled={disabled}
        data-error={error !== undefined}
      >
        <div className={styles["state-layer"]}>
          <span className={styles["value"]}>{selectedOption ? selectedOption.label : placeholder}</span>
          <span className={styles["icon"]} aria-hidden="true">
            <Icon category={"outlined"} type={"arrow_drop_down"} />
          </span>
        </div>
      </button>

      <div id={`${baseId}-menu`} className={styles["menu-popover"]} role="presentation">
        <Menu
          options={options}
          baseId={baseId}
          selectedId={value}
          onChange={(v) => {
            setIsOpen(false);
            onChange(v);
          }}
        />
      </div>

      <span className={styles["error-message"]} id={`${baseId}-error`}>
        {error && <>{error}</>}
      </span>
    </div>
  );
}
