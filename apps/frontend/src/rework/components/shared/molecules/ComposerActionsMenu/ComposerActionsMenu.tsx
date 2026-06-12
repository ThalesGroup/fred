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

import { ReactNode, useEffect, useRef, useState } from "react";
import IconButton from "@shared/atoms/IconButton/IconButton";
import styles from "./ComposerActionsMenu.module.css";

interface ComposerActionsMenuProps {
  disabled?: boolean;
  children?: ReactNode | ((controls: { closeMenu: () => void }) => ReactNode);
}

export function ComposerActionsMenu({ disabled = false, children }: ComposerActionsMenuProps) {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const closeMenu = () => setOpen(false);

  useEffect(() => {
    if (disabled && open) {
      setOpen(false);
    }
  }, [disabled, open]);

  useEffect(() => {
    if (!open) return;
    const handleMouseDown = (event: MouseEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", handleMouseDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handleMouseDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [open]);

  return (
    <div ref={containerRef} className={styles.container} data-open={open}>
      <IconButton
        color="on-surface"
        variant="icon"
        size="small"
        icon={{ category: "outlined", type: "add" }}
        aria-label="Open chat actions"
        disabled={disabled}
        onClick={() => setOpen((value) => !value)}
      />
      {open && (
        <div className={styles.menu} role="dialog" aria-label="Chat actions">
          {children ? (
            <div className={styles.menuBody}>{typeof children === "function" ? children({ closeMenu }) : children}</div>
          ) : null}
        </div>
      )}
    </div>
  );
}
