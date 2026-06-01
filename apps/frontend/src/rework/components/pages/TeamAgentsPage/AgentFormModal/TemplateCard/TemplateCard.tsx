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
      <div className={styles.cardHeader}>
        {template.category && <span className={styles.categoryPill}>{template.category}</span>}
        <span className={styles.podLabel}>{template.source_runtime_id}</span>
      </div>
      <span className={styles.name}>{template.display_name}</span>
      {template.description && <span className={styles.description}>{template.description}</span>}
    </button>
  );
}
