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

import styles from "./IconButton.module.scss";
import { ButtonSize, IconButtonVariant, ColorTheme } from "../../utils/Type.ts";
import { ComponentPropsWithoutRef } from "react";
import Icon, { IconProps } from "../Icon/Icon.tsx";
import { Tooltip } from "../Tooltip/Tooltip.tsx";
import { Spinner } from "../Spinner/Spinner.tsx";

// Matches each size's `--icon-size` (IconButton.module.scss) so the spinner
// drops into the same visual footprint as the icon it replaces — no button
// resize when toggling `loading`.
// Buttons intentionally expose only sizes backed by CSS. The shared `xs` tier
// remains available to other controls; `2xs` is the 24px button tier formerly
// named `xs`.
const SPINNER_SIZE: Record<ButtonSize, number> = { "2xs": 16, small: 20, medium: 20 };

export interface IconButtonProps extends ComponentPropsWithoutRef<"button"> {
  /** Rendered by the Fred Tooltip, never as a native browser title. */
  title?: string;
  /** Defaults to "on-surface-retreat" — the app's baseline icon-button color. */
  color?: ColorTheme;
  variant: IconButtonVariant;
  size: ButtonSize;
  icon: IconProps;
  /** Icon tier when it differs from the button's, e.g. a larger hit area around a
   *  smaller glyph. Defaults to `size`. */
  iconSize?: ButtonSize;
  /** Swaps the icon for a spinner and disables the button — for an action
   *  whose async work (e.g. a network fetch) isn't instant, so a click
   *  reads as "in progress" instead of dead/unresponsive. */
  loading?: boolean;
  /**
   * Count shown in a badge on the button's top-right corner (M3 large badge).
   * Nothing renders below 1 — a zero badge is noise, not information. The badge
   * is `aria-hidden`, so pass an `aria-label` that carries the count or a screen
   * reader announces the button without it.
   */
  badgeCount?: number;
}

/** M3 caps the label at three digits; past that the exact number stops mattering. */
const BADGE_MAX = 999;

export default function IconButton({
  color = "on-surface-retreat",
  variant,
  size,
  icon,
  iconSize,
  loading = false,
  badgeCount,
  disabled,
  className,
  title,
  "aria-busy": callerBusy,
  ...props
}: IconButtonProps) {
  const buttonClasses = [styles.btn, styles[`btn-${color}`], styles[`btn-${size}`], styles[`btn-${variant}`]];
  if (iconSize) buttonClasses.push(styles[`icon-${iconSize}`]);
  if (className) buttonClasses.push(className);

  const button = (
    <button
      type="button"
      className={buttonClasses.join(" ")}
      disabled={disabled || loading}
      aria-busy={loading ? true : (callerBusy ?? false)}
      {...props}
      aria-label={props["aria-label"] ?? title}
    >
      <div className={`${styles["state-layer"]}`}>
        {loading ? <Spinner size={SPINNER_SIZE[iconSize ?? size]} /> : <Icon {...icon} />}
      </div>
    </button>
  );

  const control = title ? (
    <Tooltip content={title} asChild>
      {disabled || loading ? (
        <span tabIndex={0} aria-label={props["aria-label"] ?? title}>
          {button}
        </span>
      ) : (
        button
      )}
    </Tooltip>
  ) : (
    button
  );

  // Keep the count outside the button's clipped state layer.
  return badgeCount !== undefined && badgeCount > 0 ? (
    <span className={styles.badgeAnchor}>
      {control}
      <span className={styles.badge} aria-hidden="true">
        {badgeCount > BADGE_MAX ? `${BADGE_MAX}+` : badgeCount}
      </span>
    </span>
  ) : (
    control
  );
}
