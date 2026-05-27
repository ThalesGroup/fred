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
import { useEffect, useId, useRef, useState } from "react";
import Menu from "@shared/molecules/Menu/Menu.tsx";
import { OptionModel } from "@models/Option.model.ts";

interface IconButtonMenuProps<T> {
  iconButton: IconButtonProps;
  options: OptionModel<T>[];
  onSelect: (value: T) => void;
}

export default function IconButtonMenu<T>({ iconButton, options, onSelect }: IconButtonMenuProps<T>) {
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
    setIsOpen((prev) => !prev);
  };

  return (
    <div ref={containerRef} className={styles["container"]} data-open={isOpen}>
      <IconButton {...iconButton} onClick={toggleMenu} />
      <div id={`${baseId}-menu`} className={styles["menu-popover"]} role="presentation">
        <Menu
          options={options}
          baseId={baseId}
          onChange={(v) => {
            onSelect(v);
            setIsOpen(false);
          }}
        />
      </div>
    </div>
  );
}
