import styles from "./Button.module.scss";
import { ButtonSize, ButtonVariant, Types } from "../../utils/Types.ts";
import React, { ComponentPropsWithoutRef } from "react";
import Icon, { IconProps } from "@shared/atoms/Icon/Icon.tsx";

interface ButtonProps extends ComponentPropsWithoutRef<"button"> {
  children: React.ReactNode;
  color: Types;
  variant: ButtonVariant;
  size: ButtonSize;
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
