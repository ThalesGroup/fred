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
import IconButton from "@shared/atoms/IconButton/IconButton.tsx";
import { Tooltip } from "@shared/atoms/Tooltip/Tooltip.tsx";
import IconButtonMenu from "@shared/molecules/IconButtonMenu/IconButtonMenu.tsx";
import { OptionModel } from "@models/Option.model.ts";
import type { PromptSummary } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import { useTranslation } from "react-i18next";
import Chip from "@shared/atoms/Chip/Chip";
import styles from "./PromptCard.module.scss";

export type PromptCardVariant = "team" | "marketplace";

type MoreAction = "edit" | "duplicate" | "publish" | "unpublish" | "delete" | "import" | "removeFromMarketplace";

export interface PromptCardProps {
  prompt: PromptSummary;
  unavailableReason?: string;
  /** "team" (library management) or "marketplace" (community discovery). Default "team". */
  variant?: PromptCardVariant;
  /** team variant: resolved category name, or null → "no category" fallback. */
  categoryName?: string | null;
  /** marketplace variant: author team display name, shown in place of the category. */
  teamName?: string | null;
  /** team variant: caller can edit this team → shows the more-menu. */
  canManage?: boolean;
  /** Library variant: the server authorizes publication to the selected marketplace. */
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
  /** Shows the favorite star; omitted where favorites do not apply (marketplace, `/` picker). */
  onToggleFavorite?: () => void;
}

export default function PromptCard({
  prompt,
  unavailableReason,
  variant = "team",
  categoryName,
  teamName,
  canManage = false,
  publishable = false,
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
  onToggleFavorite,
}: PromptCardProps) {
  const { t } = useTranslation();
  const name = prompt.display_name;
  const body = prompt.description && prompt.description !== name ? prompt.description : null;
  const preview = !body && prompt.text_preview ? prompt.text_preview : null;
  const isMarketplace = variant === "marketplace";
  const isFavorite = "is_favorite" in prompt && prompt.is_favorite === true;

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
      disabled: !onImport,
      tooltip: !onImport ? t("rework.promptPublication.importUnavailable") : undefined,
      icon: { category: "outlined", type: "download" },
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
    options.push({
      key: "delete",
      value: "delete",
      label: t("rework.teams.prompts.card.menu.delete"),
      icon: { category: "outlined", type: "delete" },
      destructive: true,
    });
  }

  if (!isMarketplace && publishable) {
    options.push({
      key: published ? "unpublish" : "publish",
      value: published ? "unpublish" : "publish",
      label: t(published ? "rework.teams.prompts.card.menu.unpublish" : "rework.teams.prompts.card.menu.publish"),
      icon: { category: "outlined", type: "storefront" },
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
      data-has-favorite={Boolean(onToggleFavorite || unavailableReason)}
      onClick={onView}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onView();
        }
      }}
    >
      {/* ── Favorite star + more menu (top-right) ── */}
      {(onToggleFavorite || unavailableReason || options.length > 0) && (
        // The card itself is a button; stop these clicks from opening the
        // read-only view behind it.
        <div className={styles.moreMenu} onClick={(e) => e.stopPropagation()} onKeyDown={(e) => e.stopPropagation()}>
          {(onToggleFavorite || unavailableReason) && (
            <Tooltip
              text={
                (!onToggleFavorite && unavailableReason) ||
                t(isFavorite ? "rework.teams.prompts.favorite.remove" : "rework.teams.prompts.favorite.add")
              }
            >
              <IconButton
                variant="icon"
                size="small"
                color={isFavorite ? "warning" : "on-surface-retreat"}
                icon={{ category: "outlined", type: "star", filled: isFavorite }}
                aria-label={t(
                  isFavorite ? "rework.teams.prompts.favorite.remove" : "rework.teams.prompts.favorite.add",
                )}
                aria-pressed={isFavorite}
                disabled={!onToggleFavorite}
                onClick={onToggleFavorite}
              />
            </Tooltip>
          )}
          {options.length > 0 && (
            <IconButtonMenu<MoreAction>
              iconButton={{
                color: "on-surface-retreat",
                variant: "icon",
                size: "small",
                icon: { category: "outlined", type: "more_vert" },
                "aria-label": t("rework.weaverPrompts.actions", { name }),
              }}
              options={options}
              onSelect={handleMoreSelect}
            />
          )}
        </div>
      )}

      {/* ── Header: category (team) or author team (marketplace) + name ── */}
      <div className={styles.header}>
        <span className={styles.category} data-uncategorized={!label} title={label ?? undefined}>
          {label ?? t("rework.promptCategories.noCategory")}
        </span>
        <span className={styles.name} title={name}>
          {name}
        </span>
        {"logical_name" in prompt && (
          <span className={styles.category} title={`/${prompt.logical_name}`}>
            /{prompt.logical_name}
          </span>
        )}
      </div>

      {/* ── Body ── */}
      <div className={styles.body}>
        {body && <p className={styles.description}>{body}</p>}
        {"tags" in prompt && prompt.tags.length > 0 && (
          <div className={styles.tags}>
            {prompt.tags.map((tag) => (
              <Chip key={tag} label={tag} />
            ))}
          </div>
        )}
        {preview && <p className={styles.preview}>"{preview}"</p>}
      </div>

      {/* ── Footer: usage count + optional "published" chip ── */}
      <div className={styles.footer}>
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
