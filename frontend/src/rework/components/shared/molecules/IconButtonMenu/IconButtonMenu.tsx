import styles from "./IconButtonMenu.module.scss";
import IconButton, { IconButtonProps } from "@shared/atoms/IconButton/IconButton.tsx";
import React, { useEffect, useId, useRef, useState } from "react";
import Menu from "@shared/organisms/Menu/Menu.tsx";
import { OptionModel } from "@models/Option.model.ts";

interface IconButtonMenuProps<T> {
  iconButton: IconButtonProps;
  options: OptionModel<T>[];
  onSelect: (value: T) => void;
}

export default function IconButtonMenu<T>({ iconButton, options, onSelect }: IconButtonMenuProps<T>) {
  const [isOpen, setIsOpen] = useState(false);
  const popoverRef = useRef<HTMLDivElement>(null);
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
    setIsOpen((prev) => !prev);
  };

  return (
    <>
      <div style={{ anchorName: safeAnchorId } as React.CSSProperties}>
        <IconButton {...iconButton} onClick={toggleMenu} />
      </div>
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
          onChange={(v) => {
            onSelect(v);
            toggleMenu();
          }}
        />
      </div>
    </>
  );
}
