// Copyright Thales 2025
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

/**
 * ArtifactCard
 * ------------
 * A compact, clickable in-chat reference to a side-pane artifact: an icon, a title, a hint,
 * and an optional trailing action (typically a download button). Clicking the main area
 * opens/focuses the artifact in its side pane.
 *
 * Shared by the writable-document chip and the PPT preview card so both get the same layout,
 * truncation, and chip styling. The *part* stays specific to each feature (rule of three) —
 * only the card is generic.
 *
 * Built with the rework design system (CSS modules + shared atoms), not MUI.
 */

import Icon from "@shared/atoms/Icon/Icon.tsx";
import type { IconType } from "@shared/utils/Type.ts";
import styles from "./ArtifactCard.module.css";

export default function ArtifactCard({
  icon = "description",
  title,
  hint,
  onOpen,
  action,
}: {
  /** Leading icon (design-system outlined icon name). */
  icon?: IconType;
  title: string;
  /** Sub-label under the title, e.g. "Open in editor" / "Open preview". */
  hint: string;
  /** Called when the user clicks the card body to open/focus the pane. */
  onOpen?: () => void;
  /** Optional trailing action node (e.g. a download button). */
  action?: React.ReactNode;
}) {
  return (
    <div className={styles.chip}>
      <button type="button" className={styles.open} onClick={() => onOpen?.()}>
        <span className={styles.icon}>
          <Icon category="outlined" type={icon} />
        </span>
        <span className={styles.text}>
          <span className={styles.title}>{title}</span>
          <span className={styles.hint}>{hint}</span>
        </span>
      </button>
      {action}
    </div>
  );
}
