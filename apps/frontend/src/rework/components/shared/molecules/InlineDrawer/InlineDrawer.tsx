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

import { PropsWithChildren, useEffect, useId } from "react";
import IconButton from "@shared/atoms/IconButton/IconButton";
import styles from "./InlineDrawer.module.css";

interface InlineDrawerProps {
  open: boolean;
  onClose: () => void;
  title: string;
  /** Width in CSS units. Defaults to "480px". */
  width?: string;
}

export function InlineDrawer({
  open,
  onClose,
  title,
  width = "480px",
  children,
}: PropsWithChildren<InlineDrawerProps>) {
  const titleId = useId();

  useEffect(() => {
    if (!open) return;
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [open, onClose]);

  return (
    <aside
      className={styles.drawer}
      data-open={open}
      aria-hidden={!open}
      aria-labelledby={titleId}
      style={{ "--drawer-width": width } as React.CSSProperties}
    >
      <div className={styles.header}>
        <span id={titleId} className={styles.title}>
          {title}
        </span>
        <IconButton
          color="on-surface"
          variant="icon"
          size="small"
          icon={{ category: "outlined", type: "close" }}
          aria-label="Close panel"
          onClick={onClose}
        />
      </div>
      <div className={styles.body}>{children}</div>
    </aside>
  );
}
