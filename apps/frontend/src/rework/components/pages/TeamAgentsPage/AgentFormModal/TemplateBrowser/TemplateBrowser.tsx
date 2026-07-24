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

import ButtonGroup from "@shared/atoms/ButtonGroup/ButtonGroup.tsx";
import { useMemo, useState } from "react";
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
  const [selectedPodId, setSelectedPodId] = useState<string | null>(null);

  const podIds = useMemo(() => [...new Set(templates.map((tpl) => tpl.source_runtime_id))], [templates]);

  const activePodId = podIds.includes(selectedPodId ?? "") ? selectedPodId : null;

  const filtered = activePodId ? templates.filter((tpl) => tpl.source_runtime_id === activePodId) : templates;

  if (templates.length === 0) {
    return <p className={styles.emptyNotice}>{t("rework.teams.formAgent.noTemplates")}</p>;
  }

  const podFilterItems = [{ label: t("rework.teams.agents.podFilter.all") }, ...podIds.map((id) => ({ label: id }))];

  return (
    <div className={styles.browser}>
      <div className={styles.header}>
        <div className={styles.title}>{t("rework.teams.formAgent.templateBrowser.title")}</div>
        <div className={styles.subtitle}>{t("rework.teams.formAgent.templateBrowser.subtitle")}</div>
      </div>

      {podIds.length > 1 && (
        <div className={styles.filter}>
          <ButtonGroup
            items={podFilterItems}
            size="small"
            color="primary"
            variant="radio"
            aria-label={t("rework.teams.agents.podFilter.aria")}
            selectedIndex={activePodId ? podIds.indexOf(activePodId) + 1 : 0}
            onSelectedIndexChange={(i) => setSelectedPodId(i === 0 ? null : podIds[i - 1])}
          />
        </div>
      )}
      <div className={styles.grid}>
        {filtered.map((tpl) => (
          <TemplateCard
            key={tpl.template_id}
            template={tpl}
            selected={tpl.template_id === selectedId}
            onSelect={() => onSelect(tpl.template_id)}
          />
        ))}
      </div>
    </div>
  );
}
