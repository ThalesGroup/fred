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

import { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import IconButton from "@shared/atoms/IconButton/IconButton";
import { FullPageModal } from "../FullPageModal/FullPageModal";
import { MarkdownRenderer } from "../MarkdownRenderer/MarkdownRenderer";
import styles from "./MarkdownPreviewModal.module.css";

interface MarkdownPreviewModalProps {
  open: boolean;
  onClose: () => void;
  title: string;
  subtitle?: string | null;
  markdown?: string | null;
  emptyLabel?: string;
  meta?: ReactNode;
}

export function MarkdownPreviewModal({
  open,
  onClose,
  title,
  subtitle,
  markdown,
  emptyLabel,
  meta,
}: MarkdownPreviewModalProps) {
  const { t } = useTranslation();
  const resolvedEmptyLabel = emptyLabel ?? t("chatbot.markdownPreview.empty");

  return (
    <FullPageModal isOpen={open} onClose={onClose} id="markdown-preview-modal">
      <div className={styles.overlay} onClick={onClose} aria-hidden="true">
        <div className={styles.shell} onClick={(event) => event.stopPropagation()}>
          <header className={styles.header}>
            <div className={styles.headerText}>
              <h2 id="markdown-preview-modal-title" className={styles.title}>
                {title}
              </h2>
              {subtitle ? <p className={styles.subtitle}>{subtitle}</p> : null}
            </div>
            <IconButton
              color="on-surface"
              variant="icon"
              size="small"
              icon={{ category: "outlined", type: "close" }}
              aria-label={t("chatbot.markdownPreview.closeAria")}
              onClick={onClose}
            />
          </header>

          {meta ? <div className={styles.meta}>{meta}</div> : null}

          <div className={styles.body}>
            {markdown ? <MarkdownRenderer text={markdown} /> : <div className={styles.empty}>{resolvedEmptyLabel}</div>}
          </div>
        </div>
      </div>
    </FullPageModal>
  );
}
