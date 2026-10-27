// Copyright Thales 2026. Licensed under the Apache License, Version 2.0.

import type { TFunction } from "i18next";
import type { SkillSummary } from "../../slices/controlPlane/controlPlaneOpenApi";

/** Presentation never changes the canonical identity or the model's instructions. */
export function skillPresentation(
  t: TFunction,
  skill: Pick<SkillSummary, "name"> & Partial<Pick<SkillSummary, "description" | "builtin">>,
): { title: string; description: string } {
  const fallback = { title: skill.name, description: skill.description ?? "" };
  if (!skill.builtin || !/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(skill.name)) return fallback;
  const key = `chatbot.skills.catalog.${skill.name}`;
  return {
    title: t(`${key}.title`, { defaultValue: fallback.title }),
    description: t(`${key}.description`, { defaultValue: fallback.description }),
  };
}
