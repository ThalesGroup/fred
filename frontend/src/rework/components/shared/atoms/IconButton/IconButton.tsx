import styles from "./IconButton.module.css";
import { ComponentSize, IconButtonVariant, ColorTheme } from "../../utils/Type.ts";
import { ComponentPropsWithoutRef } from "react";
import Icon, { IconProps } from "@shared/atoms/Icon/Icon.tsx";

export interface IconButtonProps extends ComponentPropsWithoutRef<"button"> {
  color: ColorTheme | "on-surface-retreat";
  variant: IconButtonVariant;
  size: ComponentSize;
  icon: IconProps;
}

export default function IconButton({ color, variant, size, icon, ...props }: IconButtonProps) {
  return (
    <button className={styles.btn} data-color={color} data-size={size} data-variant={variant} {...props}>
      <div className={`${styles.stateLayer}`}>
        <Icon {...icon} />
      </div>
    </button>
  );
}
