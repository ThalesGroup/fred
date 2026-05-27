// Copyright Thales 2025
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

import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import IconButton from "@shared/atoms/IconButton/IconButton";
import { Portal } from "@shared/utils/Portal.tsx";
import styles from "./CodenameModal.module.css";

const FOCUSABLE_SELECTORS = 'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])';

interface CodenameContent {
  description: string;
  interpretation: string;
  hint: string;
}

export interface CodenameData {
  codename: string;
  version: string;
  image: string;
  en: CodenameContent;
  fr: CodenameContent;
}

interface Props {
  open: boolean;
  onClose: () => void;
  data: CodenameData;
}

export default function CodenameModal({ open, onClose, data }: Props) {
  const { t, i18n } = useTranslation();
  const lang = i18n.language?.startsWith("fr") ? "fr" : "en";
  const content = data[lang];
  const base = (import.meta.env?.BASE_URL as string | undefined)?.replace(/\/$/, "") ?? "";

  const dialogRef = useRef<HTMLDivElement>(null);
  const previousFocusRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (open) {
      previousFocusRef.current = document.activeElement as HTMLElement;
      dialogRef.current?.focus();
    } else {
      previousFocusRef.current?.focus();
    }
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
        return;
      }
      if (e.key === "Tab" && dialogRef.current) {
        const focusable = Array.from(dialogRef.current.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTORS));
        if (!focusable.length) return;
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <Portal id="modal-portal">
      <div className={styles.overlay} onClick={onClose}>
        <div
          ref={dialogRef}
          className={styles.dialog}
          role="dialog"
          aria-modal="true"
          aria-labelledby="codename-modal-title"
          tabIndex={-1}
          onClick={(e) => e.stopPropagation()}
        >
          <div className={styles.imageWrapper}>
            <img src={`${base}${data.image}`} alt={data.codename} className={styles.image} />
            <div className={styles.closeButton}>
              <IconButton
                color="on-surface"
                variant="filled"
                size="xs"
                icon={{ category: "outlined", type: "close" }}
                onClick={onClose}
                aria-label={t("common.close")}
              />
            </div>
          </div>
          <div className={styles.content}>
            <span id="codename-modal-title" className={styles.badge}>
              {data.codename} · {data.version}
            </span>
            <p className={styles.description}>{content.description}</p>
            <p className={styles.interpretation}>{content.interpretation}</p>
            <hr className={styles.divider} />
            <p className={styles.hint}>{content.hint}</p>
          </div>
        </div>
      </div>
    </Portal>
  );
}
