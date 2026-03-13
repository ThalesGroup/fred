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
