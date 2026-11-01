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
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import type { PromptSummary, PromptCategory } from "../../../../../slices/controlPlane/controlPlaneOpenApi.ts";
import { filterPrompts, countPromptsByCategory, NO_CATEGORY_FILTER_ID } from "@shared/utils/promptFilter.ts";
import SearchInput from "@shared/molecules/SearchInput/SearchInput";
import FavoritesFilterChip from "@shared/molecules/FavoritesFilterChip/FavoritesFilterChip";
import styles from "./PromptPicker.module.css";

type PromptPickerProps = {
  prompts: PromptSummary[];
  categories: PromptCategory[];
  disabled?: boolean;
  onSelect: (id: string) => void;
};

export function PromptPicker({ prompts, categories, disabled, onSelect }: PromptPickerProps) {
  const { t } = useTranslation();
  const [activeCategory, setActiveCategory] = useState<string | null>(null);

  const categoryNameById = useMemo(() => new Map(categories.map((c) => [c.id, c.name])), [categories]);

  const categoryCounts = useMemo(() => countPromptsByCategory(prompts), [prompts]);
  const [search, setSearch] = useState("");
  const [favoritesOnly, setFavoritesOnly] = useState(false);
  useEffect(() => {
    if (activeCategory && activeCategory !== NO_CATEGORY_FILTER_ID && !categoryNameById.has(activeCategory))
      setActiveCategory(null);
  }, [activeCategory, categoryNameById]);

  const filtered = useMemo(
    () =>
      filterPrompts(prompts, {
        search,
        favoritesOnly,
        categoryId: activeCategory,
        knownCategoryIds: new Set(categoryNameById.keys()),
      }),
    [prompts, activeCategory, categoryNameById, search, favoritesOnly],
  );

  return (
    <div className={styles.wrapper}>
      <SearchInput
        value={search}
        onChange={setSearch}
        placeholder={t("rework.teams.prompts.searchPlaceholder")}
        clearAriaLabel={t("rework.teams.prompts.clearSearch")}
        size="xs"
      />
      <FavoritesFilterChip
        label={t("rework.teams.prompts.favorite.filter")}
        active={favoritesOnly}
        onToggle={() => setFavoritesOnly((value) => !value)}
      />
      {filtered.length === 0 && <p>{t("rework.teams.prompts.emptySearch")}</p>}
      {categories.length > 0 && (
        <FilterChips
          options={[
            {
              id: NO_CATEGORY_FILTER_ID,
              label: t("rework.promptCategories.noCategory"),
              count: categoryCounts.get(null) ?? 0,
            },
            ...categories.map((cat) => ({
              id: cat.id,
              label: cat.name,
              count: categoryCounts.get(cat.id) ?? 0,
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
            key={p.prompt_id}
            prompt={p}
            categoryName={(p.category_id && categoryNameById.get(p.category_id)) || null}
            canManage={false}
            onView={() => !disabled && onSelect(p.prompt_id)}
            onEdit={() => {}}
          />
        ))}
      </div>
    </div>
  );
}
