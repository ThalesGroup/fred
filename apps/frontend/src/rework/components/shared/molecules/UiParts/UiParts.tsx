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
import type { RawUiPart } from "@rework/types/parts";
import { rendererForPartKind } from "../../../../features/capabilities/partRendererRegistry";
import styles from "./UiParts.module.css";

interface UiPartsProps {
  parts: RawUiPart[];
}

/**
 * Render a message's chat parts through the part-renderer registry (#1977).
 * Kinds with no registered renderer are silently skipped — the data stays on
 * `ThreadMessage`, only the visual is absent. Never a crash on unknown kinds.
 */
export function UiParts({ parts }: UiPartsProps) {
  const { t } = useTranslation();

  const renderable = parts
    .map((part, index) => ({ part, index, Renderer: rendererForPartKind(part.type) }))
    .filter((entry) => entry.Renderer !== undefined);
  if (renderable.length === 0) return null;

  return (
    <div className={styles.parts} aria-label={t("chatbot.uiParts.ariaLabel")}>
      {renderable.map(({ part, index, Renderer }) => {
        const PartRenderer = Renderer!;
        return <PartRenderer key={`${part.type}-${index}`} part={part} />;
      })}
    </div>
  );
}
