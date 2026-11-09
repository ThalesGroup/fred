// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import type { ReactNode } from "react";
import styles from "./PromptCard.module.scss";

/** Shared library card surface; operational cards keep their actions as separate buttons. */
export default function ResourceCard({
  children,
  onOpen,
  hasFavorite = false,
}: {
  children: ReactNode;
  onOpen?: () => void;
  hasFavorite?: boolean;
}) {
  const Element = onOpen ? "div" : "article";
  return (
    <Element
      className={styles.card}
      data-interactive={!!onOpen}
      data-has-favorite={hasFavorite}
      onClick={onOpen}
      role={onOpen ? "button" : undefined}
      tabIndex={onOpen ? 0 : undefined}
      onKeyDown={
        onOpen
          ? (event) => {
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                onOpen();
              }
            }
          : undefined
      }
    >
      {children}
    </Element>
  );
}
