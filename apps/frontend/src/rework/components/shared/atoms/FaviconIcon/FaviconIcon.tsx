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

import { useState } from "react";
import styles from "./FaviconIcon.module.css";

interface FaviconIconProps {
  /** Full URL of the page — favicon is fetched from {origin}/favicon.ico as a fallback heuristic. */
  pageUrl?: string;
  /** Direct favicon URL — takes precedence over pageUrl-derived heuristic. */
  faviconUrl?: string;
  alt?: string;
  size?: number;
}

function deriveFaviconUrl(pageUrl: string): string {
  try {
    const { origin } = new URL(pageUrl);
    return `${origin}/favicon.ico`;
  } catch {
    return "";
  }
}

export function FaviconIcon({ pageUrl, faviconUrl, alt = "", size = 16 }: FaviconIconProps) {
  const src = faviconUrl ?? (pageUrl ? deriveFaviconUrl(pageUrl) : "");
  const [failed, setFailed] = useState(false);

  if (!src || failed) {
    return (
      <span className={`${styles.fallback} material-symbols-outlined`} style={{ fontSize: size }} aria-hidden>
        description
      </span>
    );
  }

  return (
    <img src={src} alt={alt} width={size} height={size} className={styles.favicon} onError={() => setFailed(true)} />
  );
}
