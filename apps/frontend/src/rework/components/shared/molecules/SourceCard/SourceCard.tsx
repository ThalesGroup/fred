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

import { FaviconIcon } from "@shared/atoms/FaviconIcon/FaviconIcon.tsx";
import { RestrictedBadge } from "@shared/atoms/RestrictedBadge/RestrictedBadge.tsx";
import type { Source } from "@rework/types/conversation.ts";
import styles from "./SourceCard.module.css";

interface SourceCardProps {
  source: Source;
  index?: number;
  onClick?: (source: Source) => void;
}

export function SourceCard({ source, index, onClick }: SourceCardProps) {
  const inner = (
    <>
      <div className={styles.header}>
        <FaviconIcon faviconUrl={source.faviconUrl} pageUrl={source.url} size={14} />
        {index !== undefined && (
          <span className={styles.index}>{index}</span>
        )}
        {source.restricted && <RestrictedBadge />}
      </div>
      <p className={styles.title}>{source.title}</p>
      <p className={styles.domain}>{source.domain}</p>
    </>
  );

  if (onClick) {
    return (
      <button
        type="button"
        className={`${styles.card} ${styles.clickable}`}
        onClick={() => onClick(source)}
        aria-label={source.title}
      >
        {inner}
      </button>
    );
  }

  return <div className={styles.card}>{inner}</div>;
}
