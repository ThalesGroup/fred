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
import { Spinner } from "../Spinner/Spinner.tsx";

// Matches each size's `--icon-size` (IconButton.module.scss) so the spinner
// drops into the same visual footprint as the icon it replaces — no button
// resize when toggling `loading`.
// Buttons intentionally expose only sizes backed by CSS. The shared `xs` tier
// remains available to other controls; `2xs` is the 24px button tier formerly
// named `xs`.
const SPINNER_SIZE: Record<ButtonSize, number> = { "2xs": 16, small: 20, medium: 24 };

export interface IconButtonProps extends ComponentPropsWithoutRef<"button"> {
  /** Defaults to "on-surface-retreat" — the app's baseline icon-button color. */
  color?: ColorTheme;
  variant: IconButtonVariant;
  size: ButtonSize;
  icon: IconProps;
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
  loading = false,
  badgeCount,
  disabled,
  className,
  "aria-busy": callerBusy,
  ...props
}: IconButtonProps) {
  const buttonClasses = [styles.btn, styles[`btn-${color}`], styles[`btn-${size}`], styles[`btn-${variant}`]];
  if (className) buttonClasses.push(className);

  const button = (
    <button
      className={buttonClasses.join(" ")}
      disabled={disabled || loading}
      aria-busy={loading ? true : (callerBusy ?? false)}
      {...props}
    >
      <div className={`${styles["state-layer"]}`}>
        {loading ? <Spinner size={SPINNER_SIZE[size]} /> : <Icon {...icon} />}
      </div>
    </button>
  );

  // The badge lives outside the button because `.btn` is `overflow: hidden` to
  // clip its state layer to the circle — a child badge would be cut off. The
  // wrapper only appears when there is a badge, so every other call site keeps
  // rendering a bare <button>.
  if (badgeCount === undefined || badgeCount < 1) return button;

  return (
    <span className={styles.badgeAnchor}>
      {button}
      <span className={styles.badge} aria-hidden="true">
        {badgeCount > BADGE_MAX ? `${BADGE_MAX}+` : badgeCount}
      </span>
    </span>
  );
}
