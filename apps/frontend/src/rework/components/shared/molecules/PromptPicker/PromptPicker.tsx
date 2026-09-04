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

import PromptCard from "@shared/organisms/PromptCard/PromptCard.tsx";
import FilterChips from "@shared/molecules/FilterChips/FilterChips.tsx";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import type {
  ContextPromptSummary,
  PromptCategorySummary,
} from "../../../../../slices/controlPlane/controlPlaneOpenApi.ts";
import { filterPrompts, NO_CATEGORY_FILTER_ID } from "@shared/utils/promptFilter.ts";
import styles from "./PromptPicker.module.css";

type PromptPickerProps = {
  prompts: ContextPromptSummary[];
  categories: PromptCategorySummary[];
  disabled?: boolean;
  onSelect: (id: string) => void;
};

export function PromptPicker({ prompts, categories, disabled, onSelect }: PromptPickerProps) {
  const { t } = useTranslation();
  const [activeCategory, setActiveCategory] = useState<string | null>(null);

  const categoryNameById = useMemo(() => new Map(categories.map((c) => [c.id, c.name])), [categories]);

  // A prompt's category_id may point at a category outside this list (e.g. a
  // personal-scope prompt's own category, since `prompts` pools personal +
  // team scope but `categories` is this team's only) — treated as
  // uncategorized for filtering purposes rather than crashing or mismatching.
  const categoryCounts = useMemo(() => {
    const byId = new Map<string, number>();
    let noCategory = 0;
    for (const p of prompts) {
      if (p.category_id && categoryNameById.has(p.category_id)) {
        byId.set(p.category_id, (byId.get(p.category_id) ?? 0) + 1);
      } else {
        noCategory += 1;
      }
    }
    return { byId, noCategory };
  }, [prompts, categoryNameById]);

  const filtered = useMemo(
    () =>
      filterPrompts(prompts, {
        search: "",
        categoryId: activeCategory,
        knownCategoryIds: new Set(categoryNameById.keys()),
      }),
    [prompts, activeCategory, categoryNameById],
  );

  return (
    <div className={styles.wrapper}>
      {categories.length > 0 && (
        <FilterChips
          options={[
            {
              id: NO_CATEGORY_FILTER_ID,
              label: t("rework.promptCategories.noCategory"),
              count: categoryCounts.noCategory,
            },
            ...categories.map((cat) => ({
              id: cat.id,
              label: cat.name,
              count: categoryCounts.byId.get(cat.id) ?? 0,
            })),
          ]}
          value={activeCategory}
          onChange={setActiveCategory}
          allLabel={t("rework.teams.agents.podFilter.all")}
          maxVisible={4}
          showMoreLabel={(count) => `+${count}`}
          showLessLabel="−"
        />
      )}
      <div className={styles.grid} data-disabled={disabled}>
        {filtered.map((p) => (
          <PromptCard
            key={p.id}
            prompt={p}
            categoryName={(p.category_id && categoryNameById.get(p.category_id)) || null}
            canManage={false}
            onView={() => !disabled && onSelect(p.id)}
            onEdit={() => {}}
          />
        ))}
      </div>
    </div>
  );
}
