import type { MaterialIconType } from "@shared/utils/Type.ts";
import type { PromptCategory } from "../../slices/controlPlane/controlPlaneOpenApi.ts";

export interface PromptCategoryDef {
  id: PromptCategory;
  /** i18n key under rework.promptCategories.<id> */
  labelKey: string;
  icon: MaterialIconType;
  /**
   * Icon pill background — must be a CSS custom property reference (`var(--...)`).
   * All values use semantic tokens from the design system; no hardcoded hex allowed.
   */
  pillBg: string;
  /**
   * Icon fill / text colour — same ramp family as pillBg.
   * Must be a CSS custom property reference (`var(--...)`).
   */
  pillFg: string;
}

export const PROMPT_CATEGORIES: PromptCategoryDef[] = [
  {
    id: "doc-assist",
    labelKey: "rework.promptCategories.doc-assist",
    icon: "find_in_page",
    pillBg: "var(--info-container)",
    pillFg: "var(--info)",
  },
  {
    id: "summary",
    labelKey: "rework.promptCategories.summary",
    icon: "summarize",
    pillBg: "var(--secondary-container)",
    pillFg: "var(--secondary)",
  },
  {
    id: "extraction",
    labelKey: "rework.promptCategories.extraction",
    icon: "table_chart",
    pillBg: "var(--success-container)",
    pillFg: "var(--success)",
  },
  {
    id: "writing",
    labelKey: "rework.promptCategories.writing",
    icon: "create",
    pillBg: "var(--success-container)",
    pillFg: "var(--on-success-container)",
  },
  {
    id: "analysis",
    labelKey: "rework.promptCategories.analysis",
    icon: "analytics",
    pillBg: "var(--warning-container)",
    pillFg: "var(--warning)",
  },
  {
    id: "monitoring",
    labelKey: "rework.promptCategories.monitoring",
    icon: "show_chart",
    pillBg: "var(--error-container)",
    pillFg: "var(--error)",
  },
  {
    // No pink token in the design system; primary (indigo) is the nearest distinct ramp.
    id: "migration",
    labelKey: "rework.promptCategories.migration",
    icon: "sync_alt",
    pillBg: "var(--primary-container)",
    pillFg: "var(--primary)",
  },
  {
    id: "conversational",
    labelKey: "rework.promptCategories.conversational",
    icon: "chat",
    pillBg: "var(--tertiary-container)",
    pillFg: "var(--tertiary)",
  },
  {
    id: "integration",
    labelKey: "rework.promptCategories.integration",
    icon: "hub",
    pillBg: "var(--surface-container-high)",
    pillFg: "var(--on-surface-retreat)",
  },
  {
    id: "other",
    labelKey: "rework.promptCategories.other",
    icon: "chat_bubble",
    pillBg: "var(--surface-container-highest)",
    pillFg: "var(--on-surface-retreat)",
  },
];

export const PROMPT_CATEGORY_MAP: Record<PromptCategory, PromptCategoryDef> = Object.fromEntries(
  PROMPT_CATEGORIES.map((c) => [c.id, c]),
) as Record<PromptCategory, PromptCategoryDef>;

/** Number of categories shown before the "show more" link. */
export const CATEGORY_INITIAL_VISIBLE = 6;
