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

import { useEffect, ReactNode } from "react";
import styles from "./FullPageModal.module.scss";
import { Portal } from "@shared/utils/Portal.tsx";

interface FullPageModalProps {
  isOpen: boolean;
  onClose: () => void;
  children: ReactNode;
  id: string;
  /** Backdrop background token. Defaults to "main" (--surface-main). */
  background?: "main" | "container";
}

export interface ModalInteractionProps {
  close: () => void;
}

export const FullPageModal = ({ isOpen, onClose, children, id, background = "main" }: FullPageModalProps) => {
  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = "hidden";
    }
    return () => {
      document.body.style.overflow = "";
    };
  }, [isOpen]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && isOpen) onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return (
    <Portal id="modal-portal">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={`${id}-title`}
        className={styles.modal}
        data-state="open"
        data-background={background}
      >
        {children}
      </div>
    </Portal>
  );
};
