import Icon from "@shared/atoms/Icon/Icon.tsx";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { PromptCategory } from "../../../../../slices/controlPlane/controlPlaneOpenApi.ts";
import { CATEGORY_INITIAL_VISIBLE, PROMPT_CATEGORIES } from "../../../../config/promptCategories.ts";
import styles from "./CategoryPicker.module.scss";

interface CategoryPickerProps {
  value: PromptCategory | null | undefined;
  onChange: (value: PromptCategory) => void;
}

export function CategoryPicker({ value, onChange }: CategoryPickerProps) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);

  const hidden = PROMPT_CATEGORIES.length - CATEGORY_INITIAL_VISIBLE;
  const visible = expanded ? PROMPT_CATEGORIES : PROMPT_CATEGORIES.slice(0, CATEGORY_INITIAL_VISIBLE);

  return (
    <div className={styles.wrapper}>
      <div className={styles.header}>
        <span className={styles.title}>{t("rework.promptCategories.pickerTitle")}</span>
        <span className={styles.subtitle}>{t("rework.promptCategories.pickerSubtitle")}</span>
      </div>

      <div className={styles.grid}>
        {visible.map((cat) => {
          const selected = value === cat.id;
          return (
            <button
              key={cat.id}
              type="button"
              className={styles.tile}
              data-selected={selected}
              style={
                selected
                  ? ({
                      borderColor: cat.pillFg,
                      backgroundColor: cat.pillBg, // container token is already the right tint
                    } as React.CSSProperties)
                  : undefined
              }
              onClick={() => onChange(cat.id)}
              aria-pressed={selected}
            >
              {/* Icon pill */}
              <span className={styles.pill} style={{ backgroundColor: cat.pillBg, color: cat.pillFg }}>
                <Icon category="outlined" type={cat.icon} />
              </span>

              {/* Label */}
              <span className={styles.label} style={selected ? { color: cat.pillFg } : undefined}>
                {t(cat.labelKey)}
              </span>

              {/* Checkmark — visible only when selected */}
              {selected && (
                <span className={styles.check} style={{ color: cat.pillFg }}>
                  <Icon category="outlined" type="check_circle" />
                </span>
              )}
            </button>
          );
        })}
      </div>

      {hidden > 0 && (
        <button type="button" className={styles.toggle} onClick={() => setExpanded((e) => !e)}>
          {expanded ? t("rework.promptCategories.showLess") : t("rework.promptCategories.showMore", { count: hidden })}
        </button>
      )}
    </div>
  );
}
