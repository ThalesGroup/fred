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

import Icon from "@shared/atoms/Icon/Icon.tsx";
import React, { useRef, useState } from "react";
import styles from "./TagInput.module.scss";

export interface TagInputProps {
  tags: string[];
  onChange: (tags: string[]) => void;
  disabled?: boolean;
  placeholder?: string;
  error?: string;
  label?: string;
  /** Produces the aria-label for each tag's remove button. Defaults to "Remove <tag>". */
  removeTagAriaLabel?: (tag: string) => string;
}

export default function TagInput({
  tags,
  onChange,
  disabled,
  placeholder,
  error,
  label,
  removeTagAriaLabel,
}: TagInputProps) {
  const [input, setInput] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  const commit = () => {
    const trimmed = input.trim().replace(/,+$/, "");
    if (trimmed && !tags.includes(trimmed)) {
      onChange([...tags, trimmed]);
    }
    setInput("");
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" || e.key === ",") {
      e.preventDefault();
      commit();
    } else if (e.key === "Backspace" && input === "" && tags.length > 0) {
      onChange(tags.slice(0, -1));
    }
  };

  const removeTag = (index: number) => {
    onChange(tags.filter((_, i) => i !== index));
  };

  return (
    <div className={styles.field}>
      {label && <span className={styles.label}>{label}</span>}
      <div
        className={`${styles.chipField} ${error ? styles.chipFieldError : ""} ${disabled ? styles.disabled : ""}`}
        onClick={() => !disabled && inputRef.current?.focus()}
      >
        {tags.map((tag, i) => (
          <span key={i} className={styles.chip}>
            {tag}
            <button
              type="button"
              className={styles.chipRemove}
              onClick={() => removeTag(i)}
              disabled={disabled}
              aria-label={removeTagAriaLabel ? removeTagAriaLabel(tag) : `Remove ${tag}`}
            >
              <Icon category="outlined" type="close" />
            </button>
          </span>
        ))}
        <input
          ref={inputRef}
          className={styles.chipInput}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          onBlur={commit}
          disabled={disabled}
          placeholder={tags.length === 0 ? placeholder : undefined}
        />
      </div>
      {error && <p className={styles.error}>{error}</p>}
    </div>
  );
}
