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

import Icon from "@shared/atoms/Icon/Icon.tsx";
import IconButtonMenu from "@shared/molecules/IconButtonMenu/IconButtonMenu.tsx";
import { OptionModel } from "@models/Option.model.ts";
import { type PromptSummary } from "../../../../../slices/controlPlane/controlPlaneOpenApi.ts";
import { useTranslation } from "react-i18next";
import styles from "./PromptCard.module.scss";

export type PromptCardVariant = "team" | "marketplace";

type MoreAction = "edit" | "duplicate" | "publish" | "unpublish" | "delete" | "import" | "removeFromMarketplace";

export interface PromptCardProps {
  prompt: PromptSummary;
  /** "team" (library management) or "marketplace" (community discovery). Default "team". */
  variant?: PromptCardVariant;
  /** team variant: resolved category name, or null → "no category" fallback. */
  categoryName?: string | null;
  /** marketplace variant: author team display name, shown in place of the category. */
  teamName?: string | null;
  /** team variant: caller can edit this team → shows the more-menu. */
  canManage?: boolean;
  /** team variant: prompt can be published to the marketplace (team prompts
   *  only — personal-space prompts stay private, so no publish action). */
  publishable?: boolean;
  /** team variant: prompt is published → storefront chip + "unpublish" action. */
  published?: boolean;
  /** marketplace variant: caller is an editor of the author team → can remove it. */
  canRemoveFromMarketplace?: boolean;
  onView: () => void;
  onEdit?: () => void;
  onDuplicate?: () => void;
  onPublish?: () => void;
  onUnpublish?: () => void;
  onDelete?: () => void;
  onImport?: () => void;
  onRemoveFromMarketplace?: () => void;
}

export default function PromptCard({
  prompt,
  variant = "team",
  categoryName,
  teamName,
  canManage = false,
  publishable = true,
  published = false,
  canRemoveFromMarketplace = false,
  onView,
  onEdit,
  onDuplicate,
  onPublish,
  onUnpublish,
  onDelete,
  onImport,
  onRemoveFromMarketplace,
}: PromptCardProps) {
  const { t } = useTranslation();
  const body = prompt.description && prompt.description !== prompt.name ? prompt.description : null;
  const preview = !body && prompt.text_preview ? prompt.text_preview : null;
  const isMarketplace = variant === "marketplace";

  // Header label: the author team on the marketplace (each team has its own
  // categories, so a category label is meaningless there), the category in the
  // team library.
  const label = isMarketplace ? (teamName ?? null) : (categoryName ?? null);

  const options: OptionModel<MoreAction>[] = [];
  if (isMarketplace) {
    options.push({
      key: "import",
      value: "import",
      label: t("rework.teams.prompts.card.menu.import"),
      icon: { category: "outlined", type: "content_copy" },
    });
    if (canRemoveFromMarketplace) {
      options.push({
        key: "removeFromMarketplace",
        value: "removeFromMarketplace",
        label: t("rework.teams.prompts.card.menu.removeFromMarketplace"),
        icon: { category: "outlined", type: "storefront" },
        destructive: true,
      });
    }
  } else if (canManage) {
    options.push(
      {
        key: "edit",
        value: "edit",
        label: t("rework.teams.prompts.card.menu.edit"),
        icon: { category: "outlined", type: "edit" },
      },
      {
        key: "duplicate",
        value: "duplicate",
        label: t("rework.teams.prompts.card.menu.duplicate"),
        icon: { category: "outlined", type: "content_copy" },
      },
    );
    // Personal-space prompts are not publishable — no publish/unpublish action.
    if (publishable) {
      options.push(
        published
          ? {
              key: "unpublish",
              value: "unpublish",
              label: t("rework.teams.prompts.card.menu.unpublish"),
              icon: { category: "outlined", type: "storefront" },
            }
          : {
              key: "publish",
              value: "publish",
              label: t("rework.teams.prompts.card.menu.publish"),
              icon: { category: "outlined", type: "storefront" },
            },
      );
    }
    options.push({
      key: "delete",
      value: "delete",
      label: t("rework.teams.prompts.card.menu.delete"),
      icon: { category: "outlined", type: "delete" },
      destructive: true,
    });
  }

  const handleMoreSelect = (action: MoreAction) => {
    if (action === "edit") onEdit?.();
    else if (action === "duplicate") onDuplicate?.();
    else if (action === "publish") onPublish?.();
    else if (action === "unpublish") onUnpublish?.();
    else if (action === "delete") onDelete?.();
    else if (action === "import") onImport?.();
    else if (action === "removeFromMarketplace") onRemoveFromMarketplace?.();
  };

  return (
    <div
      className={styles.card}
      onClick={onView}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => e.key === "Enter" && onView()}
    >
      {/* ── More menu (top-right) ── */}
      {options.length > 0 && (
        // The card itself is a button; stop the menu's clicks from opening the
        // read-only view behind it.
        <div className={styles.moreMenu} onClick={(e) => e.stopPropagation()} onKeyDown={(e) => e.stopPropagation()}>
          <IconButtonMenu<MoreAction>
            iconButton={{
              color: "on-surface-retreat",
              variant: "icon",
              size: "small",
              icon: { category: "outlined", type: "more_vert" },
            }}
            options={options}
            onSelect={handleMoreSelect}
          />
        </div>
      )}

      {/* ── Header: category (team) or author team (marketplace) + name ── */}
      <div className={styles.header}>
        <span className={styles.category} data-uncategorized={!label}>
          {label ?? t("rework.promptCategories.noCategory")}
        </span>
        <span className={styles.name}>{prompt.name}</span>
      </div>

      {/* ── Body ── */}
      {(body || preview) && (
        <div className={styles.body}>
          {body && <p className={styles.description}>{body}</p>}
          {preview && <p className={styles.preview}>"{preview}"</p>}
        </div>
      )}

      {/* ── Footer: usage count + optional "published" chip ── */}
      <div className={styles.footer}>
        <span className={styles.uses}>{t("rework.teams.prompts.card.uses", { count: prompt.session_count ?? 0 })}</span>
        {!isMarketplace && published && (
          <span className={styles.publishedChip}>
            <Icon category="outlined" type="storefront" />
            {t("rework.teams.prompts.card.publishedChip")}
          </span>
        )}
      </div>
    </div>
  );
}
