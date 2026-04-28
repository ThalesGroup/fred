import { useTranslation } from "react-i18next";
import type { AgentTemplateSummary } from "../../../../../../slices/controlPlane/controlPlaneOpenApi.ts";
import { TemplateCard } from "../TemplateCard/TemplateCard.tsx";
import styles from "./TemplateBrowser.module.css";

type TemplateBrowserProps = {
  templates: AgentTemplateSummary[];
  selectedId: string;
  onSelect: (id: string) => void;
};

export function TemplateBrowser({ templates, selectedId, onSelect }: TemplateBrowserProps) {
  const { t } = useTranslation();

  if (templates.length === 0) {
    return <p className={styles.emptyNotice}>{t("rework.teams.formAgent.noTemplates")}</p>;
  }

  return (
    <div className={styles.grid}>
      {templates.map((tpl) => (
        <TemplateCard
          key={tpl.template_id}
          template={tpl}
          selected={tpl.template_id === selectedId}
          onSelect={() => onSelect(tpl.template_id)}
        />
      ))}
    </div>
  );
}
