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

import { MaterialIcon as Icon } from "../../atoms/Icon/Icon.tsx";
import type { MaterialIconType } from "../../utils/Type.ts";
import type { ReactNode } from "react";
import styles from "./ServiceNotice.module.scss";

export interface ServiceNoticeProps {
  icon?: MaterialIconType;
  title: string;
  description?: string;
  /** Wraps the notice in a flex-1 centred container — use when the notice is
   *  the only content in the available area (e.g. service not running, nothing
   *  to show). Omit for inline banners rendered alongside other content. */
  centered?: boolean;
  /** Semantic container/on-container pair. Use `error` for a blocked action;
   *  expected service-unavailable states keep the neutral default. */
  color?: "neutral" | "info" | "error";
  /** A control shown at the end of the notice, e.g. a link to where the
   *  reader can act on it. */
  action?: ReactNode;
}

/**
 * Inline notice for service availability and blocked actions.
 *
 * Why this component exists:
 * - several pages show a "not running" state when an optional backend service
 *   (runtime pod, knowledge-flow) is not started
 * - expected unavailable states use the neutral default
 * - blocked actions opt into the error treatment and alert semantics
 *
 * How to use it:
 * - pass a translated title and optional description
 * - pick an icon that fits the absent service (e.g. "cloud_off", "dns")
 * - add `centered` when the notice is the sole content in the available space
 *
 * Example:
 * - `<ServiceNotice icon="cloud_off" title={t("...")} description={t("...")} centered />`
 */
export default function ServiceNotice({
  icon,
  title,
  description,
  centered,
  color = "neutral",
  action,
}: ServiceNoticeProps) {
  const notice = (
    <div className={styles.serviceNotice} data-color={color} role={color === "error" ? "alert" : undefined}>
      <span className={styles.icon} aria-hidden="true">
        <Icon type={icon ?? (color === "error" ? "error" : "info")} />
      </span>
      <div className={styles.text}>
        <span className={styles.title}>{title}</span>
        {description && <span className={styles.description}>{description}</span>}
      </div>
      {action && <div className={styles.action}>{action}</div>}
    </div>
  );

  if (centered) {
    return <div className={styles.centered}>{notice}</div>;
  }
  return notice;
}
