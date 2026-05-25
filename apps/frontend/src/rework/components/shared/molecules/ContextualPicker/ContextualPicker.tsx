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

import { useEffect, useId, useRef, useState } from "react";
import styles from "./ContextualPicker.module.css";

export interface PickerOption<T extends string = string> {
  value: T;
  label: string;
  description?: string;
  icon?: string;
}

interface ContextualPickerProps<T extends string = string> {
  options: PickerOption<T>[];
  value: T;
  onChange: (value: T) => void;
  /** Short prefix shown before the current selection label in the trigger (e.g. "Mode:"). */
  triggerPrefix?: string;
  disabled?: boolean;
}

export function ContextualPicker<T extends string = string>({
  options,
  value,
  onChange,
  triggerPrefix,
  disabled = false,
}: ContextualPickerProps<T>) {
  const [open, setOpen] = useState(false);
  const wrapperRef = useRef<HTMLDivElement>(null);
  const listId = useId();

  const selected = options.find((o) => o.value === value) ?? options[0];

  useEffect(() => {
    if (!open) return;
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    const handleClick = (e: MouseEvent) => {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    window.addEventListener("keydown", handleKey);
    document.addEventListener("mousedown", handleClick);
    return () => {
      window.removeEventListener("keydown", handleKey);
      document.removeEventListener("mousedown", handleClick);
    };
  }, [open]);

  return (
    <div ref={wrapperRef} className={styles.wrapper}>
      <button
        type="button"
        className={styles.trigger}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={listId}
        disabled={disabled}
        onClick={() => setOpen((v) => !v)}
      >
        {selected?.icon && (
          <span className={`${styles.icon} material-symbols-outlined`} aria-hidden>
            {selected.icon}
          </span>
        )}
        <span className={styles.label}>
          {triggerPrefix && <span className={styles.prefix}>{triggerPrefix}</span>}
          {selected?.label}
        </span>
        <span className={`${styles.chevron} material-symbols-outlined`} data-open={open} aria-hidden>
          expand_more
        </span>
      </button>

      {open && (
        <ul id={listId} role="listbox" className={styles.popover} aria-label={triggerPrefix ?? "Options"}>
          {options.map((opt) => (
            <li
              key={opt.value}
              role="option"
              aria-selected={opt.value === value}
              className={styles.option}
              data-selected={opt.value === value}
              onClick={() => {
                onChange(opt.value);
                setOpen(false);
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  onChange(opt.value);
                  setOpen(false);
                }
              }}
              tabIndex={0}
            >
              {opt.icon && (
                <span className={`${styles.optIcon} material-symbols-outlined`} aria-hidden>
                  {opt.icon}
                </span>
              )}
              <span className={styles.optText}>
                <span className={styles.optLabel}>{opt.label}</span>
                {opt.description && <span className={styles.optDesc}>{opt.description}</span>}
              </span>
              {opt.value === value && (
                <span className={`${styles.check} material-symbols-outlined`} aria-hidden>
                  check
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
