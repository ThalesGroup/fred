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
// `PatternOverride` model reads (it never travels through the capability's
// routes, so the generated client has no type for it).

import type { Pattern, TemplateInventory, Zone } from "./api/pptBuilderCapabilityOpenApi";

export type Intent = Pattern["intent"];
export type ZoneRole = Zone["role"];

export const INTENTS: readonly Intent[] = [
  "title",
  "section",
  "agenda",
  "content",
  "two_columns",
  "comparison",
  "image_text",
  "cards",
  "steps",
  "statement",
  "contact",
  "fixed",
];

export const ZONE_ROLES: readonly ZoneRole[] = [
  "title",
  "subtitle",
  "heading",
  "body",
  "caption",
  "number",
  "label",
  "image",
  "keep",
];

/** One pattern's author corrections; only set fields apply (backend `PatternOverride`). */
export interface PatternOverride {
  pattern_id: string;
  label?: string | null;
  intent?: Intent | null;
  included?: boolean | null;
  zone_roles?: Record<string, ZoneRole>;
}

export const OVERRIDES_KEY = "overrides";
export const INVENTORY_KEY = "inventory";
export const PATTERNS_PATH_KEY = "patterns_path";

export function readOverrides(configValues: Record<string, unknown>): PatternOverride[] {
  const raw = configValues[OVERRIDES_KEY];
  return Array.isArray(raw) ? (raw as PatternOverride[]) : [];
}

export function readInventory(configValues: Record<string, unknown>): TemplateInventory | null {
  const raw = configValues[INVENTORY_KEY];
  return raw && typeof raw === "object" && Array.isArray((raw as TemplateInventory).patterns)
    ? (raw as TemplateInventory)
    : null;
}

/** Merge a patch into the override of one pattern; an override left with no
 *  correction is dropped so the stored list stays minimal. */
export function upsertOverride(
  overrides: PatternOverride[],
  patternId: string,
  patch: Partial<Omit<PatternOverride, "pattern_id">>,
): PatternOverride[] {
  const current = overrides.find((o) => o.pattern_id === patternId) ?? { pattern_id: patternId };
  const next: PatternOverride = { ...current, ...patch };
  if (patch.zone_roles !== undefined) {
    next.zone_roles = { ...(current.zone_roles ?? {}), ...patch.zone_roles };
  }
  const empty =
    next.label == null &&
    next.intent == null &&
    next.included == null &&
    Object.keys(next.zone_roles ?? {}).length === 0;
  const others = overrides.filter((o) => o.pattern_id !== patternId);
  return empty ? others : [...others, next];
}

/** The inventory as the agent will see it: the analysis with the author's
 *  corrections applied (the backend's `apply_overrides`, for display). */
export function effectiveInventory(inventory: TemplateInventory, overrides: PatternOverride[]): TemplateInventory {
  const byId = new Map(overrides.map((o) => [o.pattern_id, o]));
  return {
    ...inventory,
    patterns: inventory.patterns.map((pattern) => {
      const override = byId.get(pattern.id);
      if (!override) return pattern;
      const roles = override.zone_roles ?? {};
      const applyRole = (zone: Zone): Zone => (roles[zone.key] ? { ...zone, role: roles[zone.key] } : zone);
      return {
        ...pattern,
        label: override.label?.trim() ? override.label.trim() : pattern.label,
        intent: override.intent ?? pattern.intent,
        included: override.included ?? pattern.included,
        exclusion_reason: override.included === false ? "author" : override.included ? null : pattern.exclusion_reason,
        zones: pattern.zones.map(applyRole),
        groups: pattern.groups.map((group) => {
          const items = group.items.map((item) => item.map(applyRole));
          return { ...group, items, item_zones: items[0] ? items[0].map((z) => z.role) : group.item_zones };
        }),
      };
    }),
  };
}

export interface InventorySummary {
  patterns: number;
  fixed: number;
  excluded: number;
}

export function summarize(inventory: TemplateInventory): InventorySummary {
  const included = inventory.patterns.filter((p) => p.included);
  return {
    patterns: included.filter((p) => p.intent !== "fixed").length,
    fixed: included.filter((p) => p.intent === "fixed").length,
    excluded: inventory.patterns.length - included.length,
  };
}

/** Every zone of a pattern, top-level ones then each group item's, with the
 *  item index for group zones so the detail view can name them. */
export function allZones(pattern: Pattern): { zone: Zone; item: number | null }[] {
  const out = pattern.zones.map((zone) => ({ zone, item: null as number | null }));
  pattern.groups.forEach((group) => {
    group.items.forEach((item, index) => item.forEach((zone) => out.push({ zone, item: index })));
  });
  return out;
}
