// Copyright Thales 2026
//
// Licensed under the Apache License, Version 2.0 (the "License");
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
import styles from "./OriginBadge.module.css";

/** Provenance origin values stamped by Knowledge Flow (FILES-04 G4). */
export type FileOrigin = "uploaded" | "agent_generated" | "shared_copy" | "ingested" | "system";

const ORIGIN_ICON: Record<string, IconType> = {
  uploaded: "attach_file",
  agent_generated: "auto_awesome",
  shared_copy: "groups",
  ingested: "database",
  system: "settings",
};

interface OriginBadgeProps {
  /** Server-derived origin; unknown values fall back to a neutral file icon. */
  origin: string;
  /** Localized label, e.g. "Déposé" / "Généré" / "Partagé" (caller passes t(...)). */
  label: string;
}

/**
 * Small provenance chip telling a human where a file came from (deposé / généré /
 * partagé). Presentational only: the caller supplies the localized label; this atom
 * owns the icon and the per-origin colour variant.
 */
export function OriginBadge({ origin, label }: OriginBadgeProps) {
  return (
    <span className={styles.badge} data-origin={origin} aria-label={label}>
      <Icon category="outlined" type={ORIGIN_ICON[origin] ?? ("description" as IconType)} />
      <span className={styles.label}>{label}</span>
    </span>
  );
}
