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

// The ppt_builder config widget's own types. The inventory comes from the
// generated client; the override is the stored-config shape the backend's
// `PatternOverride` reads (it never travels through a capability route).

import type { Pattern, TemplateInventory } from "./api/pptBuilderCapabilityOpenApi";

export type SlideKind = Pattern["kind"];

export const SLIDE_KINDS: readonly SlideKind[] = [
  "cover",
  "agenda",
  "section",
  "bullets",
  "two_columns",
  "comparison",
  "cards",
  "figures",
  "process",
  "timeline",
  "team",
  "quote",
  "image_text",
  "table",
  "closing",
  "other",
];

/** One pattern's author corrections; only set fields apply (backend `PatternOverride`). */
export interface PatternOverride {
  pattern_id: string;
  label?: string | null;
  kind?: SlideKind | null;
  included?: boolean | null;
}

export type OverridePatch = Partial<Omit<PatternOverride, "pattern_id">>;

export const TEMPLATE_SHA_KEY = "template_sha256";
export const OVERRIDES_KEY = "overrides";
export const USE_VISION_KEY = "use_vision";
export const LABELLING_MODEL_KEY = "labelling_model";

export function readOverrides(configValues: Record<string, unknown>): PatternOverride[] {
  const raw = configValues[OVERRIDES_KEY];
  return Array.isArray(raw) ? (raw as PatternOverride[]) : [];
}

export function readTemplateSha(configValues: Record<string, unknown>): string | null {
  const raw = configValues[TEMPLATE_SHA_KEY];
  return typeof raw === "string" && raw ? raw : null;
}

/** Merge a patch into one pattern's override; an override left with no
 *  correction is dropped so the stored list stays minimal. */
export function upsertOverride(
  overrides: PatternOverride[],
  patternId: string,
  patch: OverridePatch,
): PatternOverride[] {
  const current = overrides.find((o) => o.pattern_id === patternId) ?? { pattern_id: patternId };
  const next: PatternOverride = { ...current, ...patch };
  const empty = !next.label?.trim() && next.kind == null && next.included == null;
  const others = overrides.filter((o) => o.pattern_id !== patternId);
  return empty ? others : [...others, next];
}

/** The inventory as the agent will see it: the analysis with the author's
 *  corrections applied (the backend's `apply_overrides`, for display). */
export function effectiveInventory(inventory: TemplateInventory, overrides: PatternOverride[]): TemplateInventory {
  const byId = new Map(overrides.map((o) => [o.pattern_id, o]));
  return {
    ...inventory,
    patterns: (inventory.patterns ?? []).map((pattern) => {
      const override = byId.get(pattern.id);
      if (!override) return pattern;
      return {
        ...pattern,
        label: override.label?.trim() ? override.label.trim() : pattern.label,
        kind: override.kind ?? pattern.kind,
        included: override.included ?? pattern.included,
        exclusion_reason: override.included === false ? "author" : override.included ? null : pattern.exclusion_reason,
      };
    }),
  };
}

/** Overrides naming a pattern the analysed template no longer has (dropped on save). */
export function unmatchedOverrides(overrides: PatternOverride[], inventory: TemplateInventory): string[] {
  const ids = new Set((inventory.patterns ?? []).map((p) => p.id));
  return overrides.filter((o) => !ids.has(o.pattern_id)).map((o) => o.pattern_id);
}

export interface InventorySummary {
  patterns: number;
  excluded: number;
}

export function summarize(inventory: TemplateInventory): InventorySummary {
  const patterns = inventory.patterns ?? [];
  const included = patterns.filter((p) => p.included !== false).length;
  return { patterns: included, excluded: patterns.length - included };
}
