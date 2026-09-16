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

import { memo, useRef, useEffect, ReactElement } from "react";
import styles from "./Menu.module.scss";
import { type SelectOption } from "../Select/Select.tsx";
import MenuItem from "../../atoms/MenuItem/MenuItem.tsx";

interface MenuProps<T> {
  options: SelectOption<T>[];
  baseId: string;
  activeId?: string;
  selectedId?: T;
  noOptionsMessage?: string;
  noEnabledOptionsMessage?: string;
  onChange?: (selectedId: T) => void;
}

const MenuInternal = <T,>({
  options = [],
  baseId,
  activeId,
  selectedId,
  onChange,
  noOptionsMessage = "Aucune option disponible",
  noEnabledOptionsMessage,
}: MenuProps<T>) => {
  const listRef = useRef<HTMLUListElement>(null);

  useEffect(() => {
    if (activeId && listRef.current) {
      const activeElement = Array.from(listRef.current.children).find((item) => item.id === activeId);
      if (activeElement) {
        activeElement.scrollIntoView({
          block: "nearest",
          behavior: "smooth",
        });
      }
    }
  }, [activeId]);

  if (options.length === 0) {
    return (
      <div className={`${styles["menu"]} ${styles["menu-empty"]}`} role="status">
        {noOptionsMessage}
      </div>
    );
  }

  return (
    <>
      {noEnabledOptionsMessage && options.every((option) => option.disabled) && (
        <div className={`${styles["menu"]} ${styles["menu-empty"]}`} role="status">
          {noEnabledOptionsMessage}
        </div>
      )}
      <ul
        ref={listRef}
        id={`${baseId}-listbox`}
        className={styles["menu"]}
        role="listbox"
        aria-activedescendant={activeId}
        tabIndex={-1}
        onMouseDown={(e) => e.preventDefault()}
      >
        {options.map((option) => {
          // The unique key also keeps IDs stable when values are objects.
          // Treat the resulting ID as opaque, including punctuation in keys.
          const itemId = `${baseId}-opt-${option.key}`;
          const isFocused = activeId === itemId;

          const isSelected = Array.isArray(selectedId)
            ? (selectedId as unknown[]).includes(option.value)
            : selectedId === option.value;

          return (
            <MenuItem
              key={option.key}
              id={itemId}
              label={option.label}
              description={option.description}
              title={option.tooltip}
              icon={option.icon}
              disabled={option.disabled}
              destructive={option.destructive}
              selected={isSelected}
              focused={isFocused}
              onClick={() => {
                if (option.disabled) return;
                onChange?.(option.value);
              }}
            />
          );
        })}
      </ul>
    </>
  );
};

export const Menu = memo(MenuInternal) as <T>(props: MenuProps<T>) => ReactElement;

export default Menu;
