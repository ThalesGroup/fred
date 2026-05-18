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

import { PropsWithChildren, useId, useRef, useState, useEffect } from "react";
import styles from "./CollapsibleBlock.module.css";

interface CollapsibleBlockProps {
  summary: React.ReactNode;
  defaultOpen?: boolean;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
}

export function CollapsibleBlock({
  summary,
  defaultOpen = false,
  open: controlledOpen,
  onOpenChange,
  children,
}: PropsWithChildren<CollapsibleBlockProps>) {
  const contentId = useId();
  const [internalOpen, setInternalOpen] = useState(defaultOpen);
  const contentRef = useRef<HTMLDivElement>(null);

  const isOpen = controlledOpen !== undefined ? controlledOpen : internalOpen;

  useEffect(() => {
    const el = contentRef.current;
    if (!el) return;
    if (isOpen) {
      el.style.height = `${el.scrollHeight}px`;
    } else {
      el.style.height = `${el.scrollHeight}px`;
      requestAnimationFrame(() => {
        el.style.height = "0px";
      });
    }
  }, [isOpen]);

  const toggle = () => {
    const next = !isOpen;
    if (controlledOpen === undefined) setInternalOpen(next);
    onOpenChange?.(next);
  };

  return (
    <div className={styles.block} data-open={isOpen}>
      <button
        type="button"
        className={styles.trigger}
        aria-expanded={isOpen}
        aria-controls={contentId}
        onClick={toggle}
      >
        <span
          className={`${styles.chevron} material-symbols-outlined`}
          aria-hidden
        >
          chevron_right
        </span>
        <span className={styles.summary}>{summary}</span>
      </button>

      <div
        id={contentId}
        ref={contentRef}
        className={styles.content}
        aria-hidden={!isOpen}
      >
        <div className={styles.inner}>{children}</div>
      </div>
    </div>
  );
}
