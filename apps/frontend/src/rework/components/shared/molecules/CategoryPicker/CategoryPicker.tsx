import { useTranslation } from "react-i18next";
import type { PromptCategorySummary } from "../../../../../slices/controlPlane/controlPlaneOpenApi.ts";
import styles from "./CategoryPicker.module.scss";

interface CategoryPickerProps {
  categories: PromptCategorySummary[];
  value: string | null | undefined;
  onChange: (categoryId: string | null) => void;
}

export function CategoryPicker({ categories, value, onChange }: CategoryPickerProps) {
  const { t } = useTranslation();

  return (
    <div className={styles.wrapper}>
      <span className={styles.title}>{t("rework.promptCategories.pickerTitle")}</span>

      <div className={styles.chips}>
        <button
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
