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

import Icon from "@shared/atoms/Icon/Icon.tsx";
import IconButton from "@shared/atoms/IconButton/IconButton.tsx";
import { type PromptSummary } from "../../../../../slices/controlPlane/controlPlaneOpenApi.ts";
import styles from "./PromptCard.module.scss";

export interface PromptCardProps {
  prompt: PromptSummary;
  canManage: boolean;
  onEdit: () => void;
}

export default function PromptCard({ prompt, canManage, onEdit }: PromptCardProps) {
  return (
    <div className={styles.promptCard}>
      <div className={styles.stateLayer}>
        <div className={styles.cardInfo}>
          <div className={styles.cardPresentation}>
            <div className={styles.cardIcon}>
              <Icon category="outlined" type="edit_note" />
            </div>
            <div className={styles.cardIdentity}>
              <div className={styles.cardName}>{prompt.name}</div>
              <div className={styles.cardAuthor}>{prompt.created_by ?? "—"}</div>
            </div>
          </div>
        </div>

        {canManage && (
          <div className={styles.actions}>
            <IconButton
              size="medium"
              color="on-surface"
              variant="icon"
              icon={{ category: "outlined", type: "edit" }}
              onClick={(e) => {
                e.preventDefault();
                e.stopPropagation();
                onEdit();
              }}
            />
          </div>
        )}
      </div>
    </div>
  );
}
