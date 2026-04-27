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

import { KeyboardEvent } from "react";
import TextArea from "@shared/atoms/TextArea/TextArea";
import IconButton from "@shared/atoms/IconButton/IconButton";
import styles from "./ChatInputBar.module.css";

interface ChatInputBarProps {
  value: string;
  onChange: (value: string) => void;
  onSend: () => void;
  disabled: boolean;
}

export function ChatInputBar({ value, onChange, onSend, disabled }: ChatInputBarProps) {
  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      onSend();
    }
  };

  return (
    <div className={styles.bar}>
      <div className={styles.input}>
        <TextArea
          label="Message"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={disabled}
          rows={2}
          placeholder="Press Enter to send, Shift+Enter for newline"
        />
      </div>
      <IconButton
        color="primary"
        variant="filled"
        size="medium"
        icon={{ category: "outlined", type: "send" }}
        disabled={!value.trim() || disabled}
        onClick={onSend}
        aria-label="Send message"
      />
    </div>
  );
}
