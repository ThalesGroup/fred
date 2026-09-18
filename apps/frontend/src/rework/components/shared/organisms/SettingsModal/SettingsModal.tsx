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

import { FullPageModal } from "@shared/molecules/FullPageModal/FullPageModal.tsx";
import { useEffect, useRef, type ReactNode } from "react";
import styles from "./SettingsModal.module.css";

export interface SettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  /** Root for the dialog's DOM ids. The title carries `${id}-title`, which is
   *  what `FullPageModal` points `aria-labelledby` at. */
  id: string;
  title: string;
  subtitle?: string;
  /** Right-aligned header block — where Cancel/Save live. */
  actions?: ReactNode;
  /** Left-aligned block below a rule, for an action set apart from the rest
   *  (a delete, typically). Omit to render no footer at all. */
  footer?: ReactNode;
  children: ReactNode;
}

/**
 * The full-page settings surface: one card, a titled header with its actions,
 * the form below, an optional footer.
 *
 * The shell a settings form renders in — an agent's and a Knowledge Base's are
 * the same object on screen, and a second copy drifts the first time either is
 * touched. For a couple of questions rather than a form, that is
 * `molecules/Dialog`, not a narrow variant of this.
 */
export default function SettingsModal({
  isOpen,
  onClose,
  id,
  title,
  subtitle,
  actions,
  footer,
  children,
}: SettingsModalProps) {
  const card = useRef<HTMLDivElement>(null);

  // A dialog whose fields are all disabled autofocuses nothing, leaving focus
  // on the page behind an `aria-modal` overlay. Take it only in that case, so a
  // form with its own autofocused first field keeps it.
  useEffect(() => {
    if (!isOpen) return;
    if (document.activeElement === document.body) card.current?.focus();
  }, [isOpen]);

  return (
    <FullPageModal isOpen={isOpen} onClose={onClose} id={id} background="container">
      <div className={styles.card} ref={card} tabIndex={-1}>
        <div className={styles.header}>
          <div className={styles.titleBlock}>
            <div id={`${id}-title`} className={styles.title}>
              {title}
            </div>
            {subtitle && <div className={styles.subtitle}>{subtitle}</div>}
          </div>
          {actions && <div className={styles.actions}>{actions}</div>}
        </div>

        <div className={styles.content}>{children}</div>

        {footer && <div className={styles.footer}>{footer}</div>}
      </div>
    </FullPageModal>
  );
}
