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

export interface IconButtonProps extends ComponentPropsWithoutRef<"button"> {
  color: ColorTheme;
  variant: IconButtonVariant;
  size: ComponentSize;
  icon: IconProps;
}

export default function IconButton({ color, variant, size, icon, ...props }: IconButtonProps) {
  const buttonClasses = [styles.btn, styles[`btn-${color}`], styles[`btn-${size}`], styles[`btn-${variant}`]];

  return (
    <button className={buttonClasses.join(" ")} {...props}>
      <div className={`${styles["state-layer"]}`}>
        <Icon {...icon} />
      </div>
    </button>
  );
}
