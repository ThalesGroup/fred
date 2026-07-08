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

import styles from "./IconButtonMenu.module.scss";
import IconButton, { IconButtonProps } from "@shared/atoms/IconButton/IconButton.tsx";
import { CSSProperties, useCallback, useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import Menu from "@shared/molecules/Menu/Menu.tsx";
import { OptionModel } from "@models/Option.model.ts";

// Gap between the button and the popover (matches --spacing-3xs).
const MENU_GAP = 4;
// Vertical room (px) required below the button before the menu flips upward.
const MIN_MENU_SPACE = 240;

interface IconButtonMenuProps<T> {
  iconButton: IconButtonProps;
  options: OptionModel<T>[];
  onSelect: (value: T) => void;
}

export default function IconButtonMenu<T>({ iconButton, options, onSelect }: IconButtonMenuProps<T>) {
  const [isOpen, setIsOpen] = useState(false);
  const [popoverStyle, setPopoverStyle] = useState<CSSProperties>({});
  const containerRef = useRef<HTMLDivElement>(null);
  const popoverRef = useRef<HTMLDivElement>(null);
  const baseId = useId();

  // Position the portaled popover relative to the button. The menu is rendered
  // into document.body so it escapes the table's `overflow: auto` scroll
  // container (which otherwise clips it — showing a scrollbar instead of the
  // menu for the last row). It flips upward when there is not enough room below.
  const updatePosition = useCallback(() => {
    const anchor = containerRef.current;
    if (!anchor) return;
    const rect = anchor.getBoundingClientRect();
    const spaceBelow = window.innerHeight - rect.bottom;
    const openUp = spaceBelow < MIN_MENU_SPACE && rect.top > spaceBelow;
    setPopoverStyle({
      position: "fixed",
      right: window.innerWidth - rect.right,
      ...(openUp ? { bottom: window.innerHeight - rect.top + MENU_GAP } : { top: rect.bottom + MENU_GAP }),
    });
  }, []);

  useLayoutEffect(() => {
    if (isOpen) updatePosition();
  }, [isOpen, updatePosition]);

  // Reposition on scroll (capture: also fires for scrollable ancestors such as
  // the table container) and on resize.
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
    setIsOpen((prev) => !prev);
  };

  return (
    <div ref={containerRef} className={styles["container"]} data-open={isOpen}>
      <IconButton {...iconButton} onClick={toggleMenu} />
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
              onChange={(v) => {
                onSelect(v);
                setIsOpen(false);
              }}
            />
          </div>,
          document.body,
        )}
    </div>
  );
}
