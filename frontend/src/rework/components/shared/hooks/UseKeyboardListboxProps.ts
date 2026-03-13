import { useState, useCallback, KeyboardEvent } from "react";

interface UseKeyboardListboxProps<T> {
  items: T[];
  onSelect: (item: T) => void;
  onClose: () => void;
}

export function useKeyboardListbox<T>({ items, onSelect, onClose }: UseKeyboardListboxProps<T>) {
  const [activeIndex, setActiveIndex] = useState(-1);

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (items.length === 0) return;

      switch (e.key) {
        case "ArrowDown":
          e.preventDefault();
          setActiveIndex((prev) => (prev < items.length - 1 ? prev + 1 : 0));
          break;
        case "ArrowUp":
          e.preventDefault();
          setActiveIndex((prev) => (prev > 0 ? prev - 1 : items.length - 1));
          break;
        case "Enter":
        case " ":
          e.preventDefault();
          if (activeIndex >= 0) onSelect(items[activeIndex]);
          break;
        case "Escape":
          onClose();
          break;
      }
    },
    [items, activeIndex, onSelect, onClose],
  );

  return { activeIndex, setActiveIndex, handleKeyDown };
}
