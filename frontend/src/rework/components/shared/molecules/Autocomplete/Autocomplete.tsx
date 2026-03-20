import styles from "./Autocomplete.module.scss";
import TextInput, { TextInputProps } from "@shared/atoms/TextInput/TextInput.tsx";
import Menu from "@shared/organisms/Menu/Menu.tsx";
import React, { useEffect, useId, useRef, useState } from "react";
import { OptionModel } from "@models/Option.model.ts";

interface AutocompleteProps<T> {
  textInput: TextInputProps;
  options: OptionModel<T>[];
  onSelect: (value: T) => void;
  onFieldValueChange?: (value: string) => void;
}

export default function Autocomplete<T>({ textInput, options, onSelect, onFieldValueChange }: AutocompleteProps<T>) {
  const [isOpen, setIsOpen] = useState(false);
  const [queryValue, setQueryValue] = useState("");
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

  useEffect(() => {
    onFieldValueChange(queryValue);
  }, [queryValue]);

  const toggleMenu = () => {
    setIsOpen((prev) => !prev);
  };

  return (
    <div className={styles["autocomplete-container"]} style={{ anchorName: safeAnchorId } as React.CSSProperties}>
      <TextInput
        compact={true}
        {...textInput}
        onFocus={() => {
          setIsOpen(true);
        }}
        onBlur={() => {
          setIsOpen(false);
        }}
        onChange={(e) => {
          setQueryValue(e.target.value);
        }}
        value={queryValue}
      />
      <div
        id={`${baseId}-menu`}
        ref={popoverRef}
        popover="manual"
        className={styles["menu-popover"]}
        style={{ positionAnchor: safeAnchorId } as React.CSSProperties}
      >
        <Menu
          options={options}
          baseId={baseId}
          onChange={(v) => {
            toggleMenu();
            onSelect(v);
            setQueryValue("");
          }}
        />
      </div>
    </div>
  );
}
