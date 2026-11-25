// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { useTranslation } from "react-i18next";
import Checkbox from "@shared/atoms/Checkbox/Checkbox";
import Icon from "@shared/atoms/Icon/Icon";
import IconButton from "@shared/atoms/IconButton/IconButton";
import { Tooltip } from "@shared/atoms/Tooltip/Tooltip";
import { FOLDER_ICON, fileIconSpec } from "../../utils/fileIconSpec";
import type { WikiPageSummary } from "../../../slices/controlPlane/controlPlaneOpenApi";
import { buildWikiTree, visibleNodes, MAX_PAGE_DEPTH } from "./wikiTree";
import styles from "../../components/shared/molecules/DocumentLibraryScopePicker/DocumentLibraryScopePicker.module.css";

/** The same folder/file vocabulary as the resource picker; only pages are destinations. */
export function WikiDestinationPicker({
  pages,
  value,
  onChange,
  disabled,
  levelsBelow = 1,
}: {
  pages: WikiPageSummary[];
  value: string;
  onChange: (slug: string) => void;
  disabled: boolean;
  levelsBelow?: number;
}) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(new Set<string>());
  return (
    <ul className={styles.tree} aria-label={t("chatbot.sessionAttachments.share.destination")}>
      {visibleNodes(buildWikiTree(pages), expanded).map(({ page, depth, children }) => {
        const file = page.kind === "file";
        const icon = file ? fileIconSpec(page.title, page.mime) : FOLDER_ICON;
        return (
          <li key={page.page_id} style={{ marginLeft: `calc(${depth} * var(--spacing-l))` }}>
            <div className={file ? styles.documentItem : styles.nodeRow}>
              {!file && (
                <IconButton
                  size="small"
                  variant="icon"
                  icon={{ category: "outlined", type: expanded.has(page.page_id) ? "expand_more" : "chevron_right" }}
                  aria-label={`${t(expanded.has(page.page_id) ? "rework.collapse" : "rework.expand")} ${page.title}`}
                  disabled={!children.length}
                  onClick={() =>
                    setExpanded((previous) => {
                      const next = new Set(previous);
                      if (next.has(page.page_id)) next.delete(page.page_id);
                      else next.add(page.page_id);
                      return next;
                    })
                  }
                />
              )}
              {!file && (
                <Checkbox
                  aria-label={page.title}
                  checked={value === page.slug}
                  disabled={disabled || depth + levelsBelow > MAX_PAGE_DEPTH}
                  onChange={() => onChange(page.slug)}
                />
              )}
              <span className={styles.documentIcon} style={{ color: icon.color }}>
                <Icon category="outlined" type={icon.type} filled={icon.filled} />
              </span>
              <Tooltip content={page.title} asChild>
                <span tabIndex={0} className={styles.documentName}>
                  {page.title}
                </span>
              </Tooltip>
            </div>
          </li>
        );
      })}
    </ul>
  );
}
