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
import {
  CSSProperties,
  KeyboardEvent as ReactKeyboardEvent,
  useCallback,
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
} from "react";
import { createPortal } from "react-dom";
import { OptionModel } from "@models/Option.model.ts";
import { uiPortalRoot } from "@shared/utils/Portal.tsx";
import { viewportHeight } from "@shared/utils/viewport.ts";

// Gap between the field and the popover (matches --spacing-3xs).
const MENU_GAP = 4;
// Vertical room (px) required below the field before the menu flips upward.
const MIN_MENU_SPACE = 240;

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
  /** Replaces the menu's default empty text, e.g. to tell "searching" from "no match". */
  noOptionsMessage?: string;
}

export default function Autocomplete<T>({
  textInput,
  options,
  onSelect,
  onFieldValueChange,
  minQueryLength = 0,
  noOptionsMessage,
}: AutocompleteProps<T>) {
  const [isFocused, setIsFocused] = useState(false);
  // True right after Escape or a selection — suppresses the menu until the
  // next focus or keystroke, even though the field stays focused (the
  // listbox's onMouseDown deliberately keeps focus on select, so "isFocused"
  // alone can't tell a fresh open from one that was just dismissed).
  const [dismissed, setDismissed] = useState(false);
  const [queryValue, setQueryValue] = useState("");
  // Virtual focus (aria-activedescendant pattern, same as Select): DOM focus
  // stays on the input, arrow keys move this index and Enter selects it.
  // Reset on every keystroke/focus rather than reactively on `options`
  // itself — `options` is a brand new array reference on nearly every
  // parent render (a `.filter()`/`.map()` result), not just when the
  // candidate list actually changes, and resetting off of it would keep
  // stomping on the user's own up/down navigation mid-browse.
  const [activeIndex, setActiveIndex] = useState(0);
  const baseId = useId();
  const [popoverStyle, setPopoverStyle] = useState<CSSProperties>({});
  const containerRef = useRef<HTMLDivElement>(null);

  const isOpen = isFocused && !dismissed && queryValue.trim().length >= minQueryLength;

  // The menu is portaled (like Select's) so a scrollable ancestor such as a
  // Dialog body cannot clip it; it is anchored to the field with `fixed`.
  const updatePosition = useCallback(() => {
    const anchor = containerRef.current;
    if (!anchor) return;
    const rect = anchor.getBoundingClientRect();
    const spaceBelow = viewportHeight() - rect.bottom;
    const openUp = spaceBelow < MIN_MENU_SPACE && rect.top > spaceBelow;
    setPopoverStyle({
      position: "fixed",
      left: rect.left,
      minWidth: rect.width,
      ...(openUp ? { bottom: viewportHeight() - rect.top + MENU_GAP } : { top: rect.bottom + MENU_GAP }),
    });
  }, []);

  useLayoutEffect(() => {
    if (isOpen) updatePosition();
  }, [isOpen, updatePosition]);

  // Follow the field when any ancestor scrolls (capture) or the window resizes.
  useEffect(() => {
    if (!isOpen) return;
    const handler = () => updatePosition();
    window.addEventListener("scroll", handler, true);
    window.addEventListener("resize", handler);
    return () => {
      window.removeEventListener("scroll", handler, true);
      window.removeEventListener("resize", handler);
    };
  }, [isOpen, updatePosition]);

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

  // Walks past disabled options in `delta`'s direction; if every option is
  // disabled, the active index doesn't move.
  const moveActive = (delta: number) => {
    if (options.length === 0) return;
    setActiveIndex((prev) => {
      const base = prev < 0 ? 0 : prev;
      let next = base;
      for (let i = 0; i < options.length; i++) {
        next = (next + delta + options.length) % options.length;
        if (!options[next]?.disabled) return next;
      }
      return prev;
    });
  };

  const selectOption = (value: T) => {
    setDismissed(true);
    onSelect(value);
    setQueryValue("");
  };

  const handleKeyDown = (e: ReactKeyboardEvent<HTMLInputElement>) => {
    if (!isOpen) return;
    switch (e.key) {
      case "ArrowDown":
        e.preventDefault();
        moveActive(1);
        break;
      case "ArrowUp":
        e.preventDefault();
        moveActive(-1);
        break;
      case "Enter": {
        const option = options[activeIndex];
        if (option && !option.disabled) {
          e.preventDefault();
          selectOption(option.value);
        }
        break;
      }
      default:
        break;
    }
  };

  const activeOption = isOpen ? options[activeIndex] : undefined;
  const activeOptionId = activeOption ? `${baseId}-opt-${activeOption.key}` : undefined;

  return (
    <div className={styles["autocomplete-container"]} ref={containerRef} data-open={isOpen}>
      <TextInput
        compact={true}
        {...textInput}
        onFocus={() => {
          setIsFocused(true);
          setDismissed(false);
          setActiveIndex(0);
        }}
        onBlur={() => setIsFocused(false)}
        onChange={(e) => {
          setQueryValue(e.target.value);
          setDismissed(false);
          setActiveIndex(0);
        }}
        onKeyDown={handleKeyDown}
        aria-expanded={isOpen}
        aria-activedescendant={activeOptionId}
        value={queryValue}
      />
      {isOpen &&
        createPortal(
          <div id={`${baseId}-menu`} className={styles["menu-popover"]} role="presentation" style={popoverStyle}>
            <Menu
              options={options}
              baseId={baseId}
              activeId={activeOptionId}
              noOptionsMessage={noOptionsMessage}
              onChange={(v) => selectOption(v)}
            />
          </div>,
          uiPortalRoot(containerRef.current),
        )}
    </div>
  );
}
