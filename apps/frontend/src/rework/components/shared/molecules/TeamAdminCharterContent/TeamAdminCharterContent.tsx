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

import { useEffect, useRef } from "react";
import { MarkdownRenderer } from "@shared/molecules/MarkdownRenderer/MarkdownRenderer";
import { useLegalMarkdown } from "@hooks/useLegalMarkdown.ts";
import styles from "./TeamAdminCharterContent.module.css";

interface TeamAdminCharterContentProps {
  /** Called once the end of the charter is visible. Pass a stable callback; omit to only display it. */
  onEndReached?: () => void;
}

/** The team administrator charter markdown, overridable from the theme archive. */
export default function TeamAdminCharterContent({ onEndReached }: TeamAdminCharterContentProps) {
  const markdown = useLegalMarkdown("team-admin-charter");
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const end = endRef.current;
    if (!markdown || !end || !onEndReached) return;
    // Any overlap counts: Firefox's fractional positions never reach a full-visibility threshold.
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          onEndReached();
          observer.disconnect();
        }
      },
      { threshold: 0 },
    );
    observer.observe(end);
    return () => observer.disconnect();
  }, [markdown, onEndReached]);

  return (
    <div className={styles.content}>
      <MarkdownRenderer text={markdown} />
      <div ref={endRef} className={styles.end} data-testid="team-admin-charter-end" />
    </div>
  );
}
