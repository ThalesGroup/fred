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

import type { ContextPromptSummary } from "../../../../../slices/controlPlane/controlPlaneOpenApi.ts";
import styles from "./PromptPicker.module.css";

type PromptPickerProps = {
  prompts: ContextPromptSummary[];
  disabled?: boolean;
  onSelect: (id: string) => void;
};

export function PromptPicker({ prompts, disabled, onSelect }: PromptPickerProps) {
  return (
    <div className={styles.grid}>
      {prompts.map((p) => (
        <button key={p.id} type="button" className={styles.card} onClick={() => onSelect(p.id)} disabled={disabled}>
          <span className={styles.cardHeader}>
            <span className={styles.name}>{p.name}</span>
            <span className={styles.scopeBadge}>{p.scope}</span>
          </span>
          {p.description && <span className={styles.description}>{p.description}</span>}
        </button>
      ))}
    </div>
  );
}
