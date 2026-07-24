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

import styles from "./ButtonGroup.module.scss";
import ButtonGroupItem, { ButtonGroupItemProps } from "@shared/atoms/ButtonGroup/ButtonGroupItem/ButtonGroupItem.tsx";
import { ComponentSize, ColorTheme } from "@shared/utils/Type.ts";
import { KeyboardEvent, MouseEvent, useRef, useState } from "react";

interface ButtonGroupProps {
  items: ButtonGroupItemProps[];
  size: ComponentSize;
  color: ColorTheme;
  /**
   * Semantic role: a mutually-exclusive filter/setting pick ("radio", e.g.
   * the capabilities kind filter) vs. a tab strip switching displayed
   * content ("tabs", e.g. the agent form's section strip). Required so every
   * call site states its intent — it drives both the ARIA role/state and
   * the keyboard behavior below.
   */
  variant: "radio" | "tabs";
  /** Accessible name for the group (radiogroup/tablist both need one). */
  "aria-label": string;
  /** Stretches the group and its items to fill the parent's width instead of the default fit-content pill. */
  fullWidth?: boolean;
  defaultSelectedIndex?: number;
  /** When provided, turns the component into a controlled tab strip. */
  selectedIndex?: number;
  onSelectedIndexChange?: (index: number) => void;
}

export default function ButtonGroup({
  items,
  size,
  color,
  variant,
  "aria-label": ariaLabel,
  fullWidth = false,
  defaultSelectedIndex = 0,
  selectedIndex,
  onSelectedIndexChange,
}: ButtonGroupProps) {
  const [internalIndex, setInternalIndex] = useState(defaultSelectedIndex);
  const resolvedIndex = selectedIndex !== undefined ? selectedIndex : internalIndex;
  const itemRefs = useRef<(HTMLButtonElement | null)[]>([]);

  const selectIndex = (index: number, event?: MouseEvent<HTMLButtonElement>) => {
    setInternalIndex(index);
    onSelectedIndexChange?.(index);
    const onClick = items[index]?.onClick;
    if (onClick && event) onClick(event);
  };

  // Roving focus: arrow keys move focus AND selection together — the native
  // radiogroup pattern, also used here for "tabs" (automatic activation,
  // matching the existing click-selects-immediately behavior). Disabled
  // items are skipped; if every item is disabled, focus doesn't move.
  // Focus + native .click() (rather than calling selectIndex directly) so
  // keyboard activation runs through the exact same onClick path — including
  // each item's own onClick — that a mouse click does, instead of only
  // updating the group-level selection.
  const focusAndSelect = (index: number) => {
    const el = itemRefs.current[index];
    el?.focus();
    el?.click();
  };

  const moveFocus = (fromIndex: number, delta: number) => {
    for (let i = 0, next = fromIndex; i < items.length; i++) {
      next = (next + delta + items.length) % items.length;
      if (!items[next]?.disabled) {
        focusAndSelect(next);
        return;
      }
    }
  };

  const focusFirst = () => {
    const index = items.findIndex((item) => !item.disabled);
    if (index >= 0) focusAndSelect(index);
  };

  const focusLast = () => {
    for (let i = items.length - 1; i >= 0; i--) {
      if (!items[i]?.disabled) {
        focusAndSelect(i);
        return;
      }
    }
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    switch (event.key) {
      case "ArrowRight":
      case "ArrowDown":
        event.preventDefault();
        moveFocus(index, 1);
        break;
      case "ArrowLeft":
      case "ArrowUp":
        event.preventDefault();
        moveFocus(index, -1);
        break;
      case "Home":
        event.preventDefault();
        focusFirst();
        break;
      case "End":
        event.preventDefault();
        focusLast();
        break;
      default:
        break;
    }
  };

  return (
    <div
      className={styles["button-group"]}
      data-full-width={fullWidth}
      role={variant === "radio" ? "radiogroup" : "tablist"}
      aria-label={ariaLabel}
    >
      {items.map((item, index) => (
        <ButtonGroupItem
          key={index}
          {...item}
          ref={(el) => {
            itemRefs.current[index] = el;
          }}
          size={size}
          color={item.color ?? color}
          variant={variant}
          fullWidth={fullWidth}
          selected={index === resolvedIndex}
          tabIndex={index === resolvedIndex ? 0 : -1}
          onClick={(e) => selectIndex(index, e)}
          onKeyDown={(e) => handleKeyDown(e, index)}
        />
      ))}
    </div>
  );
}
