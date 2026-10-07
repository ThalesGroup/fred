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
import Icon from "@shared/atoms/Icon/Icon";
import { hostOf, safeHttpUrl } from "@rework/utils/externalUrl";
import styles from "./ArtifactLinks.module.css";

/**
 * A public source cited by the answer. Unlike ArtifactLinkChip it is a plain
 * anchor: the target is a third-party site, so no Fred token may reach it.
 */
export function CitationLinkChip({ link }: { link: LinkPart }) {
  const { t } = useTranslation();
  const href = link.href ? safeHttpUrl(link.href) : null;
  if (!href) return null;

  const host = hostOf(href);
  const name = link.title || host;
  return (
    <a
      className={styles.chip}
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      title={`${name} — ${host}`}
      aria-label={t("chatbot.artifactLinks.citationAria", { name, host })}
    >
      <span className={styles.icon} aria-hidden>
        <Icon category="outlined" type="travel_explore" />
      </span>
      <span className={styles.name}>{name}</span>
    </a>
  );
}
