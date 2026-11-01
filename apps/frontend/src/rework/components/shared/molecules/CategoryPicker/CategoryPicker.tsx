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

import { useTranslation } from "react-i18next";
import type { PromptCategory } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import styles from "./CategoryPicker.module.scss";

interface CategoryPickerProps {
  categories: PromptCategory[];
  value: string | null | undefined;
  disabled?: boolean;
  onChange: (categoryId: string | null) => void;
}

export function CategoryPicker({ categories, value, onChange, disabled }: CategoryPickerProps) {
  const { t } = useTranslation();

  return (
    <div className={styles.wrapper}>
      <span className={styles.title}>{t("rework.promptCategories.pickerTitle")}</span>

      <div className={styles.chips}>
        <button
          disabled={disabled}
          type="button"
          className={styles.chip}
          data-selected={!value}
          onClick={() => onChange(null)}
          aria-pressed={!value}
        >
          {t("rework.promptCategories.noCategory")}
        </button>
        {categories.map((cat) => {
          const selected = value === cat.id;
          return (
            <button
              key={cat.id}
              title={cat.name}
              disabled={disabled}
              type="button"
              className={styles.chip}
              data-selected={selected}
              onClick={() => onChange(cat.id)}
              aria-pressed={selected}
            >
              {cat.name}
            </button>
          );
        })}
      </div>
    </div>
  );
}
