import type { MaterialIconType } from "@shared/utils/Type.ts";
import type { PromptCategory } from "../../slices/controlPlane/controlPlaneOpenApi.ts";

export interface PromptCategoryDef {
  id: PromptCategory;
  /** i18n key under rework.promptCategories.<id> */
  labelKey: string;
  icon: MaterialIconType;
  /** Icon pill background — dark-theme safe */
  pillBg: string;
  /** Icon fill / text colour — same ramp family as pillBg */
  pillFg: string;
}

export const PROMPT_CATEGORIES: PromptCategoryDef[] = [
  {
    id: "doc-assist",
    labelKey: "rework.promptCategories.doc-assist",
    icon: "find_in_page",
    pillBg: "#1a3a5c",
    pillFg: "#60a5fa",
  },
  {
    id: "summary",
    labelKey: "rework.promptCategories.summary",
    icon: "summarize",
    pillBg: "#2d1a4a",
    pillFg: "#c084fc",
  },
  {
    id: "extraction",
    labelKey: "rework.promptCategories.extraction",
    icon: "table_chart",
    pillBg: "#1a3d2b",
    pillFg: "#4ade80",
  },
  {
    id: "writing",
    labelKey: "rework.promptCategories.writing",
    icon: "create",
    pillBg: "#1c3820",
    pillFg: "#86efac",
  },
  {
    id: "analysis",
    labelKey: "rework.promptCategories.analysis",
    icon: "analytics",
    pillBg: "#3d2a00",
    pillFg: "#fbbf24",
  },
  {
    id: "monitoring",
    labelKey: "rework.promptCategories.monitoring",
    icon: "show_chart",
    pillBg: "#3d1a1a",
    pillFg: "#f87171",
  },
  {
    id: "migration",
    labelKey: "rework.promptCategories.migration",
    icon: "sync_alt",
    pillBg: "#3d1a28",
    pillFg: "#f472b6",
  },
  {
    id: "conversational",
    labelKey: "rework.promptCategories.conversational",
    icon: "chat",
    pillBg: "#1a3a5c",
    pillFg: "#93c5fd",
  },
  {
    id: "integration",
    labelKey: "rework.promptCategories.integration",
    icon: "hub",
    pillBg: "#252525",
    pillFg: "#9ca3af",
  },
];

export const PROMPT_CATEGORY_MAP: Record<PromptCategory, PromptCategoryDef> = Object.fromEntries(
  PROMPT_CATEGORIES.map((c) => [c.id, c]),
) as Record<PromptCategory, PromptCategoryDef>;

/** Number of categories shown before the "show more" link. */
export const CATEGORY_INITIAL_VISIBLE = 6;
