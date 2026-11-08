// Copyright Thales 2026. Licensed under the Apache License, Version 2.0.

import type { TFunction } from "i18next";
import type { SkillSummary } from "../../slices/controlPlane/controlPlaneOpenApi";

export function skillTooltip(title: string, description?: string | null): string {
  const summary = description?.trim();
  return summary ? `${title}: ${summary}` : title;
}

/** Presentation never changes the canonical identity or the model's instructions. */
export function skillPresentation(
  t: TFunction,
  skill: Pick<SkillSummary, "name"> & Partial<Pick<SkillSummary, "description" | "builtin" | "space_name">>,
): { title: string; description: string } {
  const fallback = { title: skill.name, description: skill.description ?? "" };
  const localized = skill.builtin && /^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(skill.name);
  const key = `chatbot.skills.catalog.${skill.name}`;
  const title = localized ? t(`${key}.title`, { defaultValue: fallback.title }) : fallback.title;
  return {
    title: skill.space_name ? `${title} · ${skill.space_name}` : title,
    description: localized ? t(`${key}.description`, { defaultValue: fallback.description }) : fallback.description,
  };
}
