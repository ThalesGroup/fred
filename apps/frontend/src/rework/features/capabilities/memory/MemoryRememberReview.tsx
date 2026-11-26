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

import { useTranslation } from "react-i18next";
import type { CapabilityHitlRendererProps } from "../types";
import styles from "./MemoryRememberReview.module.css";

/** The note's text out of the gate's argument preview (`{"text": ...}`). A
 * note is at most 500 characters, so the 1 200-character preview keeps it whole. */
function noteTextFrom(preview: string | undefined): string | null {
  if (!preview) return null;
  try {
    const args = JSON.parse(preview) as { text?: unknown };
    return typeof args.text === "string" ? args.text : null;
  } catch {
    return null;
  }
}

/** Shows the note to approve: the question alone does not say what it is. */
export function MemoryRememberReview({ call }: CapabilityHitlRendererProps) {
  const { t } = useTranslation();
  const text = noteTextFrom(call.args_preview);
  if (!text) return null;
  return <span className={styles.note}>{t("capability.memory.approval.note", { content: text })}</span>;
}
