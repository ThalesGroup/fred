import type { AgentTemplateSummary } from "../../../../../../slices/controlPlane/controlPlaneOpenApi.ts";
import styles from "./TemplateCard.module.css";

type TemplateCardProps = {
  template: AgentTemplateSummary;
  selected: boolean;
  onSelect: () => void;
};

export function TemplateCard({ template, selected, onSelect }: TemplateCardProps) {
  const unavailable = template.status === "unavailable";
  return (
    <button
      type="button"
      className={styles.card}
      data-selected={selected}
      data-unavailable={unavailable}
      onClick={onSelect}
      disabled={unavailable}
    >
      {template.category && <span className={styles.categoryPill}>{template.category}</span>}
      <span className={styles.name}>{template.display_name}</span>
      {template.description && <span className={styles.description}>{template.description}</span>}
    </button>
  );
}
