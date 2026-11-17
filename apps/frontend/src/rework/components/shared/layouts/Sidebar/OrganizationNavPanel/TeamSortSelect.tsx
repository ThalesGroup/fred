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

// Sort control of the team list: an icon button beside search that opens the
// shared `MenuPopover` as a listbox, the current order highlighted.

import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import IconButton from "@shared/atoms/IconButton/IconButton.tsx";
import MenuPopover from "@shared/molecules/MenuPopover/MenuPopover.tsx";
import styles from "./TeamSortSelect.module.scss";

export interface TeamSortOption<T extends string> {
  value: T;
  label: string;
}

interface TeamSortSelectProps<T extends string> {
  value: T;
  options: TeamSortOption<T>[];
  onChange: (value: T) => void;
  ariaLabel: string;
}

export default function TeamSortSelect<T extends string>({
  value,
  options,
  onChange,
  ariaLabel,
}: TeamSortSelectProps<T>) {
  const [open, setOpen] = useState(false);
  const [focusedIndex, setFocusedIndex] = useState(0);
  const wrapRef = useRef<HTMLDivElement>(null);
  const optionRefs = useRef<(HTMLButtonElement | null)[]>([]);

  // Close on outside click.
  useEffect(() => {
    if (!open) return;
    const handler = (event: MouseEvent) => {
      if (!wrapRef.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  // The selected option is the arrow-key anchor; MenuPopover moves focus onto it on open.
  useEffect(() => {
    if (!open) return;
    setFocusedIndex(
      Math.max(
        0,
        options.findIndex((option) => option.value === value),
      ),
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const moveFocus = (nextIndex: number) => {
    const clamped = ((nextIndex % options.length) + options.length) % options.length;
    setFocusedIndex(clamped);
    optionRefs.current[clamped]?.focus();
  };

  const selectOption = (optionValue: T) => {
    onChange(optionValue);
    setOpen(false);
  };

  const handleTriggerKeyDown = (event: KeyboardEvent<HTMLButtonElement>) => {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setOpen(true);
    } else if (event.key === "Escape") {
      setOpen(false);
    }
  };

  const handleOptionKeyDown = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    switch (event.key) {
      case "ArrowDown":
        event.preventDefault();
        moveFocus(index + 1);
        break;
      case "ArrowUp":
        event.preventDefault();
        moveFocus(index - 1);
        break;
      case "Home":
        event.preventDefault();
        moveFocus(0);
        break;
      case "End":
        event.preventDefault();
        moveFocus(options.length - 1);
        break;
      case "Escape":
        event.preventDefault();
        setOpen(false);
        break;
      default:
        break;
    }
  };

  return (
    <div ref={wrapRef} className={styles.wrap}>
      <IconButton
        size="small"
        variant="icon"
        icon={{ category: "outlined", type: "sort" }}
        aria-label={ariaLabel}
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => setOpen((prev) => !prev)}
        onKeyDown={handleTriggerKeyDown}
      />

      {open && (
        <div className={styles.menuAnchor}>
          <MenuPopover
            role="listbox"
            aria-label={ariaLabel}
            groups={[
              options.map((option, index) => {
                const isActive = option.value === value;
                return (
                  <button
                    key={option.value}
                    ref={(el) => {
                      optionRefs.current[index] = el;
                    }}
                    type="button"
                    role="option"
                    aria-selected={isActive}
                    data-selected={isActive}
                    className={styles.option}
                    tabIndex={index === focusedIndex ? 0 : -1}
                    onClick={() => selectOption(option.value)}
                    onKeyDown={(event) => handleOptionKeyDown(event, index)}
                  >
                    {option.label}
                  </button>
                );
              }),
            ]}
          />
        </div>
      )}
    </div>
  );
}
