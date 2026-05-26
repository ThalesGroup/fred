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

import { KeyboardEvent, useEffect, useRef, useState } from "react";
import Button from "@shared/atoms/Button/Button";
import TextInput from "@shared/atoms/TextInput/TextInput";
import styles from "./SessionTitleEditor.module.css";

interface SessionTitleEditorProps {
  title: string;
  onCommit: (title: string) => void;
  maxLength?: number;
  placeholder?: string;
}

export function SessionTitleEditor({
  title,
  onCommit,
  maxLength = 120,
  placeholder = "Untitled conversation",
}: SessionTitleEditorProps) {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState("");
  const wrapperRef = useRef<HTMLDivElement>(null);

  const openPopup = () => {
    setDraft(title);
    setOpen(true);
  };

  const commit = () => {
    const trimmed = draft.trim();
    setOpen(false);
    if (trimmed && trimmed !== title) onCommit(trimmed);
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") {
      e.preventDefault();
      commit();
    }
    if (e.key === "Escape") {
      e.preventDefault();
      setOpen(false);
    }
  };

  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  return (
    <div className={styles.wrapper} ref={wrapperRef}>
      <button
        type="button"
        className={styles.display}
        onClick={openPopup}
        aria-label={`Rename: ${title || placeholder}`}
        aria-expanded={open}
      >
        <span className={styles.text}>{title || placeholder}</span>
        <span className={`${styles.editIcon} material-symbols-outlined`} aria-hidden>
          edit
        </span>
      </button>

      {open && (
        <div className={styles.popup} role="dialog" aria-label="Rename conversation">
          <p className={styles.popupLabel}>Rename conversation</p>
          <TextInput
            value={draft}
            maxLength={maxLength}
            autoFocus
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={handleKeyDown}
            aria-label="New conversation name"
          />
          <div className={styles.popupActions}>
            <Button color="on-surface" variant="text" size="small" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button color="primary" variant="filled" size="small" onClick={commit}>
              Save
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
