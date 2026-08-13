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

// A compact pill chip that shows a closed-set option's current value and
// opens a popover of alternatives above the chip on click — the composer's
// "search mode" / "scope" chips (Gemini's "Deep Search" chip is the visual
// reference). Self-contained open state (click-outside/Escape close), unlike
// EnumSelectRow's externally-coordinated `open`/`onToggle`: chips sit side by
// side rather than stacked in a single popover, so each only needs to close
// itself when a click lands outside it — no shared "one open at a time" key
// required (clicking a sibling chip already lands outside this one).

import { useEffect, useRef, useState, type KeyboardEvent as ReactKeyboardEvent } from "react";
import Icon, { type IconProps } from "@shared/atoms/Icon/Icon.tsx";
import MenuPopover from "@shared/molecules/MenuPopover/MenuPopover.tsx";
import MenuPopoverItem from "@shared/molecules/MenuPopover/MenuPopoverItem.tsx";
import { Tooltip } from "@shared/atoms/Tooltip/Tooltip.tsx";
import styles from "./ContextualPicker.module.css";

export interface ContextualPickerOption<T extends string> {
  value: T;
  label: string;
}

export interface ContextualPickerProps<T extends string> {
  icon: IconProps;
  /** Setting name, used for the trigger's accessible name ("Recherche: Hybride"). Not shown visually — the chip only shows the current value. */
  title: string;
  value: T;
  options: ContextualPickerOption<T>[];
  onChange: (value: T) => void;
  /** Blocks opening (e.g. while a response streams) — mirrors the composer menus. */
  disabled?: boolean;
  /** Renders the chip in its active (primary/selected) colors — for pickers
   *  whose current value is a "something is on" state, e.g. reasoning effort. */
  accent?: boolean;
  /**
   * Chip text override — when the visible chip label is richer than the bare
   * option label (e.g. "Mistral Small · Élevé" while the option is "Élevé").
   * The accessible name keeps using `title` + the option label.
   */
  valueLabel?: string;
  /** Muted explainer rendered as the options menu's header (e.g. "higher
   *  effort takes longer"). */
  description?: string;
}

export function ContextualPicker<T extends string>({
  icon,
  title,
  value,
  options,
  onChange,
  disabled = false,
  accent = false,
  valueLabel,
  description,
}: ContextualPickerProps<T>) {
  const [open, setOpen] = useState(false);
  const [focusedIndex, setFocusedIndex] = useState(0);
  const containerRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const optionRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const selected = options.find((option) => option.value === value) ?? options[0];

  useEffect(() => {
    if (!open) return;
    const initial = Math.max(
      0,
      options.findIndex((option) => option.value === value),
    );
    setFocusedIndex(initial);
    optionRefs.current[initial]?.focus();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const handleMouseDown = (event: MouseEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
        triggerRef.current?.focus();
      }
    };
    document.addEventListener("mousedown", handleMouseDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handleMouseDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [open]);

  const moveFocus = (nextIndex: number) => {
    const clamped = ((nextIndex % options.length) + options.length) % options.length;
    setFocusedIndex(clamped);
    optionRefs.current[clamped]?.focus();
  };

  const selectOption = (optionValue: T) => {
    onChange(optionValue);
    setOpen(false);
    triggerRef.current?.focus();
  };

  const handleOptionKeyDown = (event: ReactKeyboardEvent<HTMLButtonElement>, index: number) => {
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
      default:
        break;
    }
  };

  return (
    <div ref={containerRef} className={styles.wrap}>
      {/* Tooltip carries the setting's name ("Recherche") — the chip itself only
          shows its current value ("Hybride"). Kept wrapping the trigger
          unconditionally (not gated on `open`) so the button stays a stable DOM
          node across open/close — swapping it in and out would remount the
          button and drop the focus that `triggerRef.current?.focus()` restores
          after Escape/selection. The popover's own z-index (see .menu) sits
          above the tooltip's, so it always wins if both are briefly visible at
          once (e.g. right after a click, before the pointer moves off the chip). */}
      <Tooltip text={title}>
        <button
          ref={triggerRef}
          type="button"
          className={styles.chip}
          data-open={open}
          data-accent={accent || undefined}
          disabled={disabled}
          aria-haspopup="listbox"
          aria-expanded={open}
          aria-label={`${title}: ${selected.label}`}
          onClick={() => setOpen((current) => !current)}
        >
          <span className={styles.icon}>
            <Icon {...icon} />
          </span>
          <span className={styles.value}>{valueLabel ?? selected.label}</span>
        </button>
      </Tooltip>

      {open && (
        <div className={styles.menu}>
          <MenuPopover
            role="listbox"
            aria-label={title}
            header={description ? <div className={styles.description}>{description}</div> : undefined}
            groups={[
              options.map((option, index) => (
                <MenuPopoverItem
                  key={option.value}
                  ref={(el) => {
                    optionRefs.current[index] = el;
                  }}
                  role="option"
                  label={option.label}
                  selected={option.value === value}
                  accentSelected
                  trailingIcon={option.value === value ? "check_circle" : undefined}
                  tabIndex={index === focusedIndex ? 0 : -1}
                  onClick={() => selectOption(option.value)}
                  onKeyDown={(event) => handleOptionKeyDown(event, index)}
                />
              )),
            ]}
          />
        </div>
      )}
    </div>
  );
}
