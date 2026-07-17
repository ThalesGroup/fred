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
import { CSSProperties, useCallback, useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { OptionModel } from "@models/Option.model.ts";
import Menu from "@shared/molecules/Menu/Menu.tsx";
import Icon from "@shared/atoms/Icon/Icon.tsx";
import { ComponentSize } from "@shared/utils/Type.ts";

// Gap between the trigger and the popover (matches --spacing-3xs).
const MENU_GAP = 4;
// Vertical room (px) required below the trigger before the menu flips upward.
const MIN_MENU_SPACE = 240;

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
  const [popoverStyle, setPopoverStyle] = useState<CSSProperties>({});
  const containerRef = useRef<HTMLDivElement>(null);
  const popoverRef = useRef<HTMLDivElement>(null);
  const baseId = useId();

  // Position the portaled popover relative to the trigger. The menu is
  // rendered into document.body so it escapes a scrollable ancestor's
  // `overflow: auto` (e.g. a form modal body) — otherwise the options past
  // the visible scroll area are clipped instead of shown. Flips upward when
  // there is not enough room below.
  const updatePosition = useCallback(() => {
    const anchor = containerRef.current;
    if (!anchor) return;
    const rect = anchor.getBoundingClientRect();
    const spaceBelow = window.innerHeight - rect.bottom;
    const openUp = spaceBelow < MIN_MENU_SPACE && rect.top > spaceBelow;
    setPopoverStyle({
      position: "fixed",
      left: rect.left,
      width: rect.width,
      ...(openUp ? { bottom: window.innerHeight - rect.top + MENU_GAP } : { top: rect.bottom + MENU_GAP }),
    });
  }, []);

  useLayoutEffect(() => {
    if (isOpen) updatePosition();
  }, [isOpen, updatePosition]);

  // Reposition on scroll (capture: also fires for scrollable ancestors) and
  // on resize.
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

  // Close on outside click (the popover lives in a portal, so check it too).
  useEffect(() => {
    if (!isOpen) return;
    const handler = (e: MouseEvent) => {
      const target = e.target as Node;
      if (!containerRef.current?.contains(target) && !popoverRef.current?.contains(target)) {
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

      {isOpen &&
        createPortal(
          <div
            ref={popoverRef}
            id={`${baseId}-menu`}
            className={styles["menu-popover"]}
            role="presentation"
            style={popoverStyle}
          >
            <Menu
              options={options}
              baseId={baseId}
              selectedId={value}
              onChange={(v) => {
                setIsOpen(false);
                onChange(v);
              }}
            />
          </div>,
          document.body,
        )}

      <span className={styles["error-message"]} id={`${baseId}-error`}>
        {error && <>{error}</>}
      </span>
    </div>
  );
}
