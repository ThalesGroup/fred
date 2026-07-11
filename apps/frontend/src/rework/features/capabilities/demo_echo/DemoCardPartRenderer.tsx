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

// The demo capability's chat-part card (#1977) — the known-good tracer proving
// a capability part flows backend manifest → generated types → inline card.

import { useTranslation } from "react-i18next";
import type { DemoCardPart } from "../../../../slices/runtime/runtimeOpenApi";
import Icon from "@shared/atoms/Icon/Icon";
import type { UiPartRendererProps } from "../types";
import styles from "./DemoCardPartRenderer.module.css";

export function DemoCardPartRenderer({ part }: UiPartRendererProps) {
  const { t } = useTranslation();
  const card = part as unknown as DemoCardPart;

  return (
    <div className={styles.card} role="note" aria-label={t("capability.demo_echo.cardAria")}>
      <div className={styles.header}>
        <span className={styles.icon} aria-hidden>
          <Icon category="outlined" type="graphic_eq" />
        </span>
        <span className={styles.title}>{card.title}</span>
      </div>
      {card.body ? <div className={styles.body}>{card.body}</div> : null}
    </div>
  );
}
