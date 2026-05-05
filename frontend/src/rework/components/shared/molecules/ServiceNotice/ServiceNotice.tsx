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
import { IconType } from "@shared/utils/Type.ts";
import styles from "./ServiceNotice.module.scss";

interface ServiceNoticeProps {
  icon?: IconType;
  title: string;
  description?: string;
}

/**
 * Calm informational notice for expected service-unavailable states.
 *
 * Why this component exists:
 * - several pages show a "not running" state when an optional backend service
 *   (runtime pod, knowledge-flow) is not started
 * - this is not an error — it is the expected baseline for standalone mode
 * - a single, consistent, non-alarming component avoids ad-hoc red error text
 *
 * How to use it:
 * - pass a translated title and optional description
 * - pick an icon that fits the absent service (e.g. "cloud_off", "dns")
 *
 * Example:
 * - `<ServiceNotice icon="cloud_off" title={t("rework.serviceNotice.agentTemplates.title")} description={t("rework.serviceNotice.agentTemplates.description")} />`
 */
export default function ServiceNotice({ icon = "infos", title, description }: ServiceNoticeProps) {
  return (
    <div className={styles.serviceNotice}>
      <span className={styles.icon}>
        <Icon category="outlined" type={icon} />
      </span>
      <div className={styles.text}>
        <span className={styles.title}>{title}</span>
        {description && <span className={styles.description}>{description}</span>}
      </div>
    </div>
  );
}
