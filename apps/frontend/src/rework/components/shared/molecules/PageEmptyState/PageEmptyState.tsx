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

import Button from "@shared/atoms/Button/Button.tsx";
import Icon from "@shared/atoms/Icon/Icon.tsx";
import { IconType } from "@shared/utils/Type.ts";
import styles from "./PageEmptyState.module.scss";

interface PageEmptyStateAction {
  label: string;
  onClick: () => void;
  disabled?: boolean;
}

interface PageEmptyStateProps {
  /** Material symbol name for the large centred icon. */
  icon: IconType;
  /** Primary message shown below the icon. */
  message: string;
  /** Optional primary action button rendered below the message. */
  action?: PageEmptyStateAction;
}

/**
 * Shared full-page empty state for pages that have no content yet.
 *
 * Why this component exists:
 * - agents, prompts, and knowledge pages all need the same centred
 *   icon + message + optional create button layout when nothing exists yet
 * - a single molecule ensures visual and behavioural consistency
 *
 * How to use it:
 * - render as the sole child when the page has no content
 * - pass `action` only when the current user can create content
 *
 * Example:
 * - `<PageEmptyState icon="description" message={t("...")} action={{ label: t("..."), onClick: openCreate }} />`
 */
export default function PageEmptyState({ icon, message, action }: PageEmptyStateProps) {
  return (
    <div className={styles.pageEmptyState}>
      <div className={styles.presentation}>
        <span className={styles.icon}>
          <Icon category="outlined" type={icon} filled />
        </span>
        <span>{message}</span>
      </div>
      {action && (
        <Button
          color="primary"
          variant="filled"
          size="medium"
          icon={{ category: "outlined", type: "add" }}
          onClick={action.onClick}
          disabled={action.disabled}
        >
          {action.label}
        </Button>
      )}
    </div>
  );
}
