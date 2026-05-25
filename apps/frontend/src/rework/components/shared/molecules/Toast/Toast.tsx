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

import React, { useEffect } from "react";
import Icon from "@shared/atoms/Icon/Icon.tsx";
import styles from "./Toast.module.css";

export type ToastSeverity = "success" | "error" | "warning" | "info";

export interface ToastData {
  id: number;
  severity: ToastSeverity;
  summary: string;
  detail?: string;
  duration?: number | null;
}

interface ToastProps extends ToastData {
  exiting: boolean;
  onClose: (id: number) => void;
  onExited: (id: number) => void;
}

function renderDetail(text: string) {
  const urlRegex = /(https?:\/\/[^\s]+)/g;
  return text
    .split(/\r?\n+/)
    .filter(Boolean)
    .map((line, i) => {
      const parts = line.split(urlRegex);
      return (
        <p key={i} className={styles.detailLine}>
          {parts.map((part, j) =>
            urlRegex.test(part) ? (
              <a key={j} href={part} target="_blank" rel="noopener noreferrer" className={styles.link}>
                {part}
              </a>
            ) : (
              <React.Fragment key={j}>{part}</React.Fragment>
            ),
          )}
        </p>
      );
    });
}

export function Toast({ id, severity, summary, detail, duration, exiting, onClose, onExited }: ToastProps) {
  useEffect(() => {
    if (!duration || exiting) return;
    const timer = setTimeout(() => onClose(id), duration);
    return () => clearTimeout(timer);
  }, [id, duration, exiting, onClose]);

  const handleAnimationEnd = (e: React.AnimationEvent) => {
    if (exiting && e.target === e.currentTarget) onExited(id);
  };

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText([summary, detail].filter(Boolean).join("\n"));
    } catch {}
  };

  return (
    <div
      className={`${styles.toast} ${exiting ? styles.toastExiting : styles.toastEntering}`}
      data-severity={severity}
      onAnimationEnd={handleAnimationEnd}
      role="alert"
      aria-live="assertive"
    >
      <div className={styles.header}>
        <span className={styles.summary}>{summary}</span>
        <div className={styles.actions}>
          {severity === "error" && (
            <button className={styles.actionBtn} onClick={handleCopy} aria-label="Copy error">
              <Icon category="outlined" type="content_copy" />
            </button>
          )}
          <button className={styles.actionBtn} onClick={() => onClose(id)} aria-label="Dismiss">
            <Icon category="outlined" type="close" />
          </button>
        </div>
      </div>
      {detail && <div className={styles.detail}>{renderDetail(detail)}</div>}
    </div>
  );
}

export function ToastContainer({ children }: { children: React.ReactNode }) {
  return <div className={styles.container}>{children}</div>;
}
