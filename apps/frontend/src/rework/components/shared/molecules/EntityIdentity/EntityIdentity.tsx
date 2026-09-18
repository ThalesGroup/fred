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

import Icon from "@shared/atoms/Icon/Icon.tsx";
import { IconType } from "@shared/utils/Type.ts";
import styles from "./EntityIdentity.module.css";

export interface EntityIdentityProps {
  /** Display name, already translated. */
  name: string;
  /** Material Symbols name for the leading icon. */
  icon: IconType;
  /** The identifier its author wrote, e.g. `fred.samples.assistant`. */
  sourceId?: string | null;
  /** The pod that serves it. Absent for kinds no pod hosts. */
  runtimeId?: string | null;
  /** Shown only when the kind actually has one. */
  version?: string | null;
  /** Renders the whole block muted, for rows that are present but inactive. */
  dimmed?: boolean;
}

/**
 * One row's identity, rendered the same way for every kind of thing Fred
 * catalogs — capability, agent, model, application, knowledge base.
 *
 * Why this exists: all five arrive as `CapabilityCatalogEntry`, but each page
 * had grown its own way of naming them, so the same agent read differently
 * depending on where you looked. The identity line is the fix — an id is only
 * useful next to the thing that serves it.
 *
 * `version` is deliberately omitted when absent rather than defaulted: a
 * version that is the same value on every row reads as information and is not.
 */
export function EntityIdentity({ name, icon, sourceId, runtimeId, version, dimmed = false }: EntityIdentityProps) {
  const identity = [sourceId, runtimeId].filter(Boolean) as string[];

  return (
    <div className={`${styles.root} ${dimmed ? styles.dimmed : ""}`}>
      <Icon category="outlined" type={icon} />
      <div className={styles.text}>
        <span className={styles.name} title={name}>
          {name}
        </span>
        {(identity.length > 0 || version) && (
          <span className={styles.identity} title={identity.join(" · ")}>
            {identity.map((part, index) => (
              <span key={part} className={index === 0 ? styles.sourceId : styles.runtimeId}>
                {part}
              </span>
            ))}
            {version && <span className={styles.version}>v{version}</span>}
          </span>
        )}
      </div>
    </div>
  );
}
