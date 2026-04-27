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

import { ReactNode, useEffect, useRef } from "react";
import styles from "./ChatMessagesArea.module.css";

interface ChatMessagesAreaProps {
  children: ReactNode;
  isEmpty: boolean;
  isLoading: boolean;
  /** Bumped by parent whenever messages change, to trigger auto-scroll */
  scrollVersion: number;
}

export function ChatMessagesArea({ children, isEmpty, isLoading, scrollVersion }: ChatMessagesAreaProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [scrollVersion]);

  return (
    <div className={styles.area} role="log" aria-live="polite" aria-label="Conversation">
      {isLoading && <p className={styles.hint}>Loading conversation history…</p>}
      {!isLoading && isEmpty && <p className={styles.empty}>Send a message to start the conversation.</p>}
      {children}
      <div ref={bottomRef} />
    </div>
  );
}
