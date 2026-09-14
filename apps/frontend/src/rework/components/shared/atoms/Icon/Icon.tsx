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

import { IconCategory, IconType, isCustomIcon, MaterialIconType } from "../../utils/Type.ts";
import styles from "./Icon.module.scss";

export interface IconProps {
  category: IconCategory;
  type: IconType;
  filled?: boolean;
  /** Caller-owned accessible name. Omit for decorative icons. */
  accessibleName?: string;
}

export interface MaterialIconProps {
  type: MaterialIconType;
  filled?: boolean;
  /** Caller-owned accessible name. Omit for decorative icons. */
  accessibleName?: string;
}

export function MaterialIcon({ type, filled, accessibleName }: MaterialIconProps) {
  const classes = `material-symbols-outlined ${styles.icon} ${filled ? styles.filled : ""}`;
  return (
    <span
      className={classes}
      role={accessibleName ? "img" : undefined}
      aria-label={accessibleName}
      aria-hidden={accessibleName ? undefined : "true"}
    >
      {type}
    </span>
  );
}

export default function Icon({ category, type, filled, accessibleName }: IconProps) {
  if (isCustomIcon(type)) {
    const iconPath = `/images/icons/${type}.svg`;

    return (
      <span
        className={`${styles.icon} ${styles.customIcon}`}
        style={{
          maskImage: `url(${iconPath})`,
          WebkitMaskImage: `url(${iconPath})`,
        }}
        role={accessibleName ? "img" : undefined}
        aria-label={accessibleName}
        aria-hidden={accessibleName ? undefined : "true"}
      />
    );
  }

  if (category === "outlined") {
    return <MaterialIcon type={type} filled={filled} accessibleName={accessibleName} />;
  }

  const classes = `material-symbols-${category} ${styles.icon} ${filled ? styles.filled : ""}`;
  return (
    <span
      className={classes}
      role={accessibleName ? "img" : undefined}
      aria-label={accessibleName}
      aria-hidden={accessibleName ? undefined : "true"}
    >
      {type}
    </span>
  );
}
