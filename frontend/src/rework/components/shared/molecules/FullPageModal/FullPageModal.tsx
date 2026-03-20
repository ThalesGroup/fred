import { useEffect, ReactNode } from "react";
import styles from "./FullPageModal.module.scss";
import { Portal } from "@shared/utils/Portal.tsx";

interface FullPageModalProps {
  isOpen: boolean;
  onClose: () => void;
  children: ReactNode;
  id: string;
}

export interface ModalInteractionProps {
  close: () => void;
}

export const FullPageModal = ({ isOpen, onClose, children, id }: FullPageModalProps) => {
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
        data-state={isOpen ? "open" : "closed"}
      >
        {children}
      </div>
    </Portal>
  );
};
