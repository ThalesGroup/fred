import styles from "./Button.module.css";
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
  return (
    <button className={styles.btn} data-color={color} data-size={size} data-variant={variant} {...props}>
      <div className={styles.stateLayer} data-icon={icon ? "left" : "none"}>
        {icon && (
          <span className={styles.btnIcon}>
            <Icon {...icon} />
          </span>
        )}
        {children}
      </div>
    </button>
  );
}
