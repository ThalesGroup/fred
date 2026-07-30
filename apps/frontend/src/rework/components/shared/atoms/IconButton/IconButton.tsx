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
import { ComponentSize, IconButtonVariant, ColorTheme } from "../../utils/Type.ts";
import { ComponentPropsWithoutRef } from "react";
import Icon, { IconProps } from "@shared/atoms/Icon/Icon.tsx";
import { Spinner } from "@shared/atoms/Spinner/Spinner.tsx";

// Matches each size's `--icon-size` (IconButton.module.scss) so the spinner
// drops into the same visual footprint as the icon it replaces — no button
// resize when toggling `loading`.
const SPINNER_SIZE: Record<ComponentSize, number> = { xs: 16, small: 20, medium: 24 };

export interface IconButtonProps extends ComponentPropsWithoutRef<"button"> {
  /** Defaults to "on-surface-retreat" — the app's baseline icon-button color. */
  color?: ColorTheme;
  variant: IconButtonVariant;
  size: ComponentSize;
  icon: IconProps;
  /** Swaps the icon for a spinner and disables the button — for an action
   *  whose async work (e.g. a network fetch) isn't instant, so a click
   *  reads as "in progress" instead of dead/unresponsive. */
  loading?: boolean;
}

export default function IconButton({
  color = "on-surface-retreat",
  variant,
  size,
  icon,
  loading = false,
  disabled,
  ...props
}: IconButtonProps) {
  const buttonClasses = [styles.btn, styles[`btn-${color}`], styles[`btn-${size}`], styles[`btn-${variant}`]];

  return (
    <button className={buttonClasses.join(" ")} disabled={disabled || loading} aria-busy={loading} {...props}>
      <div className={`${styles["state-layer"]}`}>
        {loading ? <Spinner size={SPINNER_SIZE[size]} /> : <Icon {...icon} />}
      </div>
    </button>
  );
}
