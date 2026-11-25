// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import type { ReactNode } from "react";
import { Tooltip } from "@shared/atoms/Tooltip/Tooltip";
import Chip from "@shared/atoms/Chip/Chip";
import styles from "./PromptCard.module.scss";

/** Shared library card surface; operational cards keep their actions as separate buttons. */
export default function ResourceCard({
  children,
  onOpen,
  hasFavorite = false,
  title,
  label,
  command,
  description,
  notice,
  body,
}: {
  children?: ReactNode;
  onOpen?: () => void;
  hasFavorite?: boolean;
  title?: string;
  label?: string;
  command?: string;
  description?: string | null;
  notice?: string;
  body?: ReactNode;
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
      {title && (
        <>
          <div className={styles.header}>
            {label && (
              <span className={styles.category} title={label}>
                {label}
              </span>
            )}
            <Tooltip content={title} asChild>
              <span tabIndex={0} className={styles.name}>
                {title}
              </span>
            </Tooltip>
            {command && (
              <span className={styles.category} title={command}>
                {command}
              </span>
            )}
          </div>
          <div className={styles.body}>
            {description && (
              <p className={styles.description} title={description}>
                {description}
              </p>
            )}
            {body}
          </div>
          {notice && <Chip label={notice} />}
        </>
      )}
    </Element>
  );
}
