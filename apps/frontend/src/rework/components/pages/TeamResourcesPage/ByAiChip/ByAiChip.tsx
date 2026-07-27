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
import Icon from "@shared/atoms/Icon/Icon.tsx";
import styles from "./ByAiChip.module.css";

interface ByAiChipProps {
  /** True only for the `origin === "agent_generated"` provenance signal
   *  (`provenance.py`) — Espace perso/partagé/Agents only. Corpus documents
   *  never carry this signal today (ingestion is never agent-driven), so
   *  callers on that tab should never pass true here. */
  visible: boolean;
}

export function ByAiChip({ visible }: ByAiChipProps) {
  const { t } = useTranslation();
  if (!visible) return null;

  return (
    <span className={styles.chip}>
      <Icon category="outlined" type="auto_awesome" />
      {t("rework.resources.byAi")}
    </span>
  );
}
