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

import { useTranslation } from "react-i18next";
import type { LinkPart } from "../../../../../slices/runtime/runtimeOpenApi";
import { ArtifactLinkChip } from "./ArtifactLinkChip";
import styles from "./ArtifactLinks.module.css";

interface ArtifactLinksProps {
  links: LinkPart[];
}

/**
 * Render agent-produced downloadable artifacts (LinkPart ui_parts) as download
 * chips. Per-chip behavior (authenticated download) lives in ArtifactLinkChip,
 * which the part-renderer registry (#1977) also dispatches to directly.
 */
export function ArtifactLinks({ links }: ArtifactLinksProps) {
  const { t } = useTranslation();

  const downloadable = links.filter((link) => Boolean(link.href));
  if (downloadable.length === 0) return null;

  return (
    <div className={styles.links} aria-label={t("chatbot.artifactLinks.ariaLabel")}>
      {downloadable.map((link, index) => (
        <ArtifactLinkChip key={`${link.href}-${index}`} link={link} />
      ))}
    </div>
  );
}
