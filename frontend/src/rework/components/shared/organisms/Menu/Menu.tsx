import { memo, useRef, useEffect, ReactElement } from "react";
import styles from "./Menu.module.scss";
import { OptionModel } from "@models/Option.model.ts";
import MenuItem from "@shared/atoms/MenuItem/MenuItem.tsx";

interface MenuProps<T> {
  options: OptionModel<T>[];
  baseId: string;
  activeId?: string;
  selectedId?: T;
  noOptionsMessage?: string;
  onChange?: (selectedId: T) => void;
}

const MenuInternal = <T,>({
  options = [],
  baseId,
  activeId,
  selectedId,
  onChange,
  noOptionsMessage = "Aucune option disponible",
}: MenuProps<T>) => {
  const listRef = useRef<HTMLUListElement>(null);

  useEffect(() => {
    if (activeId && listRef.current) {
      const activeElement = listRef.current.querySelector(`#${activeId}`);
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
        const itemId = `${baseId}-opt-${option.value}`;
        const isFocused = activeId === itemId;

        const isSelected = Array.isArray(selectedId)
          ? (selectedId as any[]).includes(option.value)
          : selectedId === option.value;

        return (
          <MenuItem
            key={option.key}
            id={itemId}
            label={option.label}
            icon={option.icon}
            disabled={option.disabled}
            selected={isSelected}
            focused={isFocused}
            onClick={() => {
              if (option.disabled) return;
              onChange(option.value);
            }}
          />
        );
      })}
    </ul>
  );
};

export const Menu = memo(MenuInternal) as <T>(props: MenuProps<T>) => ReactElement;

export default Menu;
