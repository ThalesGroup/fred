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

// A select built on `TextInput` (rather than the `Select` molecule) so its
// resting border and content font match the sibling search field exactly — the
// `Select` trigger uses different neutral-outline/font tokens at the compact
// `xs` tier. The trigger is a read-only `TextInput`; the listbox reuses the
// shared `MenuPopover` shell, anchored just below (same pattern as
// `EnumSelectRow`, minus its side-anchoring).

import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import Icon from "@shared/atoms/Icon/Icon.tsx";
import TextInput from "@shared/atoms/TextInput/TextInput.tsx";
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
  const [triggerFocused, setTriggerFocused] = useState(false);
  const [focusedIndex, setFocusedIndex] = useState(0);
  const wrapRef = useRef<HTMLDivElement>(null);
  const optionRefs = useRef<(HTMLButtonElement | null)[]>([]);
  // Whether the pending open was keyboard-driven — only then do we pull DOM
  // focus onto the selected option (so arrow keys work). A mouse open leaves
  // the list unfocused, so no option shows a focus ring on first click.
  const focusOptionOnOpenRef = useRef(false);
  const selected = options.find((option) => option.value === value) ?? options[0];

  const focusTrigger = () => wrapRef.current?.querySelector("input")?.focus();

  // Close on outside click.
  useEffect(() => {
    if (!open) return;
    const handler = (event: MouseEvent) => {
      if (!wrapRef.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  // Track the selected option as the arrow-key anchor when the list opens, and
  // — only for a keyboard open — pull DOM focus onto it. A mouse open leaves the
  // list unfocused so nothing shows a focus ring until the user arrows into it.
  useEffect(() => {
    if (!open) return;
    const initial = Math.max(
      0,
      options.findIndex((option) => option.value === value),
    );
    setFocusedIndex(initial);
    if (focusOptionOnOpenRef.current) optionRefs.current[initial]?.focus();
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
    focusTrigger();
  };

  const handleTriggerKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "ArrowDown" || event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      focusOptionOnOpenRef.current = true;
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
        focusTrigger();
        break;
      default:
        break;
    }
  };

  return (
    <div ref={wrapRef} className={styles.wrap}>
      <div className={styles.triggerWrap}>
        <TextInput
          size="xs"
          value={selected?.label ?? ""}
          readOnly
          // Drop the empty hint/counter row below the field — this trigger never
          // shows one.
          compact
          role="combobox"
          aria-haspopup="listbox"
          aria-expanded={open}
          aria-label={ariaLabel}
          onClick={() =>
            setOpen((prev) => {
              // Mouse open: don't steal focus into the list.
              if (!prev) focusOptionOnOpenRef.current = false;
              return !prev;
            })
          }
          // `user-select: none` is ignored on form controls, so block the mouse
          // from starting a selection / placing the caret at the source. The
          // click still toggles, and keyboard focus is unaffected.
          onMouseDown={(event) => event.preventDefault()}
          onKeyDown={handleTriggerKeyDown}
          onFocus={() => setTriggerFocused(true)}
          onBlur={() => setTriggerFocused(false)}
          // Inline (beats TextInput's own compound selectors) to: reserve room
          // for the chevron; kill the caret + text selection; and drive the
          // active look ourselves. The primary outline is 1px here (not the
          // component-wide 2px focus ring) and shows while open OR focused — the
          // trigger loses focus to the listbox while open, so a plain :focus
          // style wouldn't cover the open state.
          style={{
            cursor: "pointer",
            caretColor: "transparent",
            userSelect: "none",
            WebkitUserSelect: "none",
            paddingRight: "calc(var(--spacing-xs) + 1.25rem)",
            ...(open || triggerFocused ? { outline: "1px solid var(--primary)", borderColor: "transparent" } : {}),
          }}
        />
        <span className={styles.chevron} aria-hidden="true">
          <Icon category="outlined" type={open ? "expand_less" : "expand_more"} />
        </span>
      </div>

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
