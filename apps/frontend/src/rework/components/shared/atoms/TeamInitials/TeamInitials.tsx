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

import { getInitials } from "../../../../../utils/getInitials.ts";
import { teamColor, type TeamColor } from "./teamColor.ts";
import styles from "./TeamInitials.module.scss";

export interface TeamInitialsProps {
  /** Drives the initials and (unless `color` is given) the deterministic colour. */
  name: string;
  size?: "small" | "medium";
  /** Square for teams, round for the personal space (the "this is you" signal). */
  shape?: "square" | "round";
  /** Override the name-derived colour, e.g. the personal-space brand accent. */
  color?: TeamColor;
  /** Sizing/position come from the consumer (it fills the passed box). */
  className?: string;
}

/**
 * Default avatar: coloured initials, used when there is no custom image. The box
 * dimensions and position come from the consumer via `className`; this atom owns
 * the tint, shape, centred initials and font scale.
 */
export default function TeamInitials({ name, size = "small", shape = "square", color, className }: TeamInitialsProps) {
  const resolved = color ?? teamColor(name);
  return (
    <div
      className={[styles.tile, className].filter(Boolean).join(" ")}
      data-size={size}
      data-shape={shape}
      style={{ background: resolved.solid, color: resolved.onSolid }}
      role="img"
      aria-label={name}
    >
      {getInitials(name)}
    </div>
  );
}
