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

import styles from "./Button.module.scss";
import { ComponentSize, ButtonVariant, ColorTheme } from "../../utils/Type.ts";
import React, { ComponentPropsWithoutRef } from "react";
import Icon, { IconProps } from "@shared/atoms/Icon/Icon.tsx";

interface ButtonProps extends ComponentPropsWithoutRef<"button"> {
  children: React.ReactNode;
  color: ColorTheme;
  variant: ButtonVariant;
  size: ComponentSize;
  icon?: IconProps;
}
export default function Button({ children, color, variant, size, icon, className, ...props }: ButtonProps) {
  const buttonClasses = [styles.btn, styles[`btn-${color}`], styles[`btn-${size}`], styles[`btn-${variant}`]];
  if (className) buttonClasses.push(className);
  const layerClasses = [styles["state-layer"], styles[`icon-${icon ? "left" : "none"}`]];

  return (
    <button className={buttonClasses.join(" ")} {...props}>
      <div className={layerClasses.join(" ")}>
        {icon && (
          <span className={styles["btn-icon"]}>
            <Icon {...icon} />
          </span>
        )}
        {children}
      </div>
    </button>
  );
}
