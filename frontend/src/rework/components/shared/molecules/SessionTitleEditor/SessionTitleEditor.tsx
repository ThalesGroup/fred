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

import { KeyboardEvent, useRef, useState } from "react";
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
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const cancelRef = useRef(false);

  const startEdit = () => {
    setDraft(title);
    setEditing(true);
  };

  const commit = () => {
    if (cancelRef.current) {
      cancelRef.current = false;
      setEditing(false);
      return;
    }
    const trimmed = draft.trim();
    setEditing(false);
    if (trimmed && trimmed !== title) onCommit(trimmed);
  };

  const cancel = () => {
    cancelRef.current = true;
    setEditing(false);
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") { e.preventDefault(); commit(); }
    if (e.key === "Escape") { e.preventDefault(); cancel(); }
  };

  if (editing) {
    return (
      <input
        className={styles.input}
        value={draft}
        maxLength={maxLength}
        autoFocus
        onChange={(e) => setDraft(e.target.value)}
        onBlur={commit}
        onKeyDown={handleKeyDown}
        aria-label="Session title"
      />
    );
  }

  return (
    <button
      type="button"
      className={styles.display}
      onClick={startEdit}
      aria-label={`Rename conversation: ${title || placeholder}`}
    >
      <span className={styles.text}>{title || placeholder}</span>
      <span className={`${styles.editIcon} material-symbols-outlined`} aria-hidden>
        edit
      </span>
    </button>
  );
}
