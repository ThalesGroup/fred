import styles from "./Select.module.scss";
import React, { useEffect, useId, useRef, useState } from "react";
import { OptionModel } from "@models/Option.model.ts";
import Menu from "@shared/organisms/Menu/Menu.tsx";
import Icon from "@shared/atoms/Icon/Icon.tsx";
import { ComponentSize } from "@shared/utils/Type.ts";

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
  const popoverRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const baseId = useId();

  const safeAnchorId = `--anchor-${baseId.replace(/:/g, "")}`;

  useEffect(() => {
    const popover = popoverRef.current;
    if (!popover) return;

    const handleNativeToggle = (e: any) => {
      const nextState = e.newState === "open";
      setIsOpen(nextState);
    };

    popover.addEventListener("toggle", handleNativeToggle);

    return () => {
      popover.removeEventListener("toggle", handleNativeToggle);
    };
  }, []);

  useEffect(() => {
    const popover = popoverRef.current;
    if (!popover) return;
    const isActuallyOpen = popover.matches(":popover-open");

    if (isOpen && !isActuallyOpen) {
      popover.showPopover();
    } else if (!isOpen && isActuallyOpen) {
      try {
        popover.hidePopover();
      } catch (e) {}
    }
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
        style={{ anchorName: safeAnchorId } as React.CSSProperties}
      >
        <div className={styles["state-layer"]}>
          <span className={styles["value"]}>{selectedOption ? selectedOption.label : placeholder}</span>
          <span className={styles["icon"]} aria-hidden="true">
            <Icon category={"outlined"} type={"arrow_drop_down"} />
          </span>
        </div>
      </button>

      <div
        id={`${baseId}-menu`}
        ref={popoverRef}
        popover="auto"
        className={styles["menu-popover"]}
        style={{ positionAnchor: safeAnchorId } as React.CSSProperties}
      >
        <Menu
          options={options}
          baseId={baseId}
          selectedId={value}
          onChange={(v) => {
            toggleMenu();
            onChange(v);
          }}
        />
      </div>

      <span className={styles["error-message"]} id={`${baseId}-error`}>
        {error && <>{error}</>}
      </span>
    </div>
  );
}
