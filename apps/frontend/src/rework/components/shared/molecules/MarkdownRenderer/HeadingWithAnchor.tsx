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

import React, { useState } from "react";
import { useTranslation } from "react-i18next";
import IconButton from "@shared/atoms/IconButton/IconButton.tsx";
import { Tooltip } from "@shared/atoms/Tooltip/Tooltip.tsx";
import styles from "./MarkdownRenderer.module.css";

/**
 * URL-fragment slug for a heading: lowercase, diacritics stripped, everything
 * non-alphanumeric collapsed to single dashes ("Créer un agent" → "creer-un-agent").
 * Deterministic from the heading text — links stay valid as long as the
 * heading's wording doesn't change (documented in the help-content README).
 */
export function slugifyHeading(text: string): string {
  return text
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

function nodeText(node: React.ReactNode): string {
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(nodeText).join("");
  if (React.isValidElement<{ children?: React.ReactNode }>(node)) return nodeText(node.props.children);
  return "";
}

interface HeadingWithAnchorProps {
  level: 2 | 3;
  children?: React.ReactNode;
}

/**
 * Heading with a shareable anchor: carries a slug `id` (deep links can target
 * it via `#fragment`) and reveals, on hover or keyboard focus, a button that
 * copies the full URL to this heading. Used by MarkdownRenderer when
 * `headingAnchors` is enabled (Help Center articles).
 */
export function HeadingWithAnchor({ level, children }: HeadingWithAnchorProps) {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);
  const slug = slugifyHeading(nodeText(children));
  const Tag = `h${level}` as const;

  const copyLink = () => {
    const url = `${window.location.origin}${window.location.pathname}#${slug}`;
    void navigator.clipboard.writeText(url).then(() => {
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    });
  };

  return (
    <Tag id={slug} className={styles.anchoredHeading}>
      {children}
      <span className={styles.anchorAction}>
        <Tooltip text={t("rework.helpCenter.copyHeadingLink")}>
          <IconButton
            variant="icon"
            size="xs"
            icon={{ category: "outlined", type: copied ? "check" : "link" }}
            aria-label={t("rework.helpCenter.copyHeadingLink")}
            onClick={copyLink}
          />
        </Tooltip>
      </span>
    </Tag>
  );
}
